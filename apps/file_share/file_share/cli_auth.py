"""Short-lived employee delegation for explicit file-share RPCs only."""

import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import timedelta
from functools import wraps

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import get_datetime, now_datetime

from file_share.permissions import is_employee, is_manager
from file_share.serve import live_session_data

DEVICE_TTL = 300
TOKEN_TTL = 8 * 3600
HEADER = "X-BizBase-Share-Token"
CHALLENGE = re.compile(r"[0-9a-f]{64}\Z")
SECRET = re.compile(r"[A-Za-z0-9_-]{43}\Z")
RPC_METHODS = frozenset({"whoami", "domains", "list_reports", "get_report", "upload", "publish", "close"})


def digest(value):
	return hashlib.sha256(value.encode("ascii")).hexdigest()


def key(kind, value):
	return frappe.cache.make_key(f"file-share-cli:{kind}:{value}")


def _deny():
	frappe.throw("需要有效的员工文件分享授权，请重新运行 bizbase login", frappe.PermissionError)


def _challenge_key(challenge):
	if not isinstance(challenge, str) or not CHALLENGE.fullmatch(challenge):
		frappe.throw("授权请求无效或已过期", frappe.PermissionError)
	return key("device", challenge)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=300)
def begin(challenge, device_label=None):
	label = device_label or "员工终端"
	if not isinstance(label, str) or not label.strip() or len(label) > 100 or not label.isprintable():
		frappe.throw("请提供 1 到 100 个可显示字符作为终端名称")
	if not frappe.cache.set(_challenge_key(challenge), "pending:" + label.strip(), nx=True, ex=DEVICE_TTL):
		frappe.throw("请从终端重新开始授权")
	return {"expires_in": DEVICE_TTL}


def pending_device(challenge):
	value = frappe.cache.get(_challenge_key(challenge)) or b""
	if not value.startswith(b"pending:"):
		frappe.throw("授权请求已结束，请从终端重新开始", frappe.PermissionError)
	return value[8:].decode()


@frappe.whitelist(methods=["POST"])
def approve(challenge):
	device_key = _challenge_key(challenge)
	sid = frappe.request.cookies.get("sid")
	csrf = frappe.request.headers.get("X-Frappe-CSRF-Token", "")
	if not (sid and sid == frappe.session.sid and frappe.session.data.get("csrf_token")
		and hmac.compare_digest(csrf.encode(), frappe.session.data.csrf_token.encode())
		and is_employee() and live_session_data(frappe.session.user, sid) is not None):
		_deny()
	# Keep the original device deadline. Only the first explicit approval wins.
	label = pending_device(challenge)
	grant = json.dumps({"user": frappe.session.user, "sid": sid, "label": label})
	approved = frappe.cache.eval("""
		if redis.call('GET', KEYS[1]) ~= ARGV[2] then return 0 end
		redis.call('SET', KEYS[1], ARGV[1], 'KEEPTTL')
		return 1
	""", 1, device_key, grant, "pending:" + label)
	if not approved:
		frappe.throw("授权请求已过期或已被使用", frappe.PermissionError)
	return {"approved": True}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=300, seconds=60)
def exchange(verifier):
	if not isinstance(verifier, str) or not SECRET.fullmatch(verifier):
		_deny()
	# Consume an approved request once, atomically; an early poll leaves it pending.
	grant = frappe.cache.eval("""
		local value = redis.call('GET', KEYS[1])
		if value and string.sub(value,1,8) ~= 'pending:' then redis.call('DEL', KEYS[1]) end
		return value
	""", 1, _challenge_key(digest(verifier)))
	if grant and grant.startswith(b"pending:"):
		return {"state": "pending"}
	if not grant or grant == b"pending":
		_deny()
	grant = json.loads(grant)
	if "label" not in grant or live_session_data(grant["user"], grant["sid"]) is None:
		_deny()
	now = now_datetime()
	# Intentionally no user-writable document path, SID, token or token digest in Desk.
	doc = frappe.get_doc({"doctype": "File Share Grant", "name": secrets.token_hex(16),
		"owner": grant["user"], "employee": grant["user"], "device_label": grant.pop("label"),
		"issued_at": now, "expires_at": now + timedelta(seconds=TOKEN_TTL)})
	doc.db_insert()
	grant["record"] = doc.name
	token = secrets.token_urlsafe(32)
	frappe.cache.set(key("grant", digest(token)), json.dumps(grant), ex=TOKEN_TTL)
	frappe.local.response_headers["Cache-Control"] = "no-store"
	return {"token": token, "expires_in": TOKEN_TTL}


def _header_digest():
	token = frappe.request.headers.get(HEADER, "")
	if not SECRET.fullmatch(token):
		_deny()
	return digest(token)


RECORD = "File Share Grant"


def _record(name, *, lock=False):
	if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{32}", name):
		_deny()
	row = frappe.db.get_value(RECORD, name, ["employee", "revoked_at", "expires_at"], as_dict=True, for_update=lock)
	if not row:
		_deny()
	return row


def _mark_revoked(name, row, actor):
	if not row.revoked_at:
		frappe.db.set_value(RECORD, name, {"revoked_at": now_datetime(), "revoked_by": actor})
	return {"revoked": True}


@frappe.whitelist(methods=["POST"])
def disable_grant(name):
	row = _record(name, lock=True)
	user = frappe.session.user
	if not (is_manager(user) or (row.employee == user and is_employee(user))):
		_deny()
	return _mark_revoked(name, row, user)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def revoke():
	cache_key = key("grant", _header_digest())
	raw = frappe.cache.get(cache_key)
	if raw:
		grant = json.loads(raw)
		if grant.get("record"):
			row = _record(grant["record"], lock=True)
			_mark_revoked(grant["record"], row, grant["user"])
		frappe.cache.delete(cache_key)
	return {"revoked": True}


def _delegate(grant):
	user = grant["user"]
	data = live_session_data(user, grant["sid"])
	if data is None:
		_deny()
	from frappe.auth import validate_ip_address

	frappe.set_user(user)
	validate_ip_address(user)
	# Re-evaluate SSO lease even if the account also has a local Employee record.
	if data.get("yid_uid"):
		from yishan_id.session import evaluate, still_bound

		now = time.time()
		if not still_bound(data["yid_uid"], user) or now >= (data.get("yid_token_exp") or 0):
			_deny()
		if now >= (data.get("yid_lease_until") or 0) and evaluate(data, now):
			_deny()
	# Pass employee proofs only. Never expose the browser SID, CSRF or IdP token to an RPC.
	for field in ("user", "yid_uid", "yid_verified_at", "yid_token_exp", "yid_lease_until"):
		if field in data:
			frappe.session.data[field] = data[field]
	if not is_employee(user):
		_deny()


def share_rpc(fn):
	"""No global auth hook. The delegated principal exists only inside this RPC body."""
	if fn.__module__ != "file_share.api" or fn.__name__ not in RPC_METHODS:
		raise ValueError("Unknown file-share RPC")

	@wraps(fn)
	def wrapped(*args, **kwargs):
		if frappe.request.method != "POST" or frappe.request.path != f"/api/method/file_share.api.{fn.__name__}":
			_deny()
		if HEADER not in frappe.request.headers:
			if not is_employee():
				_deny()
			return fn(*args, **kwargs)
		if frappe.session.user != "Guest":
			_deny()
		fingerprint = _header_digest()
		grant = frappe.cache.get(key("grant", fingerprint))
		if not grant:
			_deny()
		grant = json.loads(grant)
		# Old Redis-only tokens intentionally require fresh consent. Lock against Desk revocation
		# so a request starting after a completed disable cannot use the previous grant.
		row = _record(grant.get("record"), lock=True)
		if row.revoked_at or row.employee != grant.get("user") or get_datetime(row.expires_at) <= now_datetime():
			_deny()
		count = frappe.cache.eval("""
			local n = redis.call('INCR', KEYS[1])
			if n == 1 then redis.call('EXPIRE', KEYS[1], 60) end
			return n
		""", 1, key("rate", fingerprint))
		if count > 120:
			frappe.throw("调用过于频繁，请稍后再试", frappe.RateLimitExceededError)
		form = frappe.local.form_dict
		session = dict(frappe.local.session)
		try:
			_delegate(grant)
			frappe.local.form_dict = form
			result = fn(*args, **kwargs)
			frappe.db.set_value(RECORD, grant["record"], "last_used_at", now_datetime(), update_modified=False)
			return result
		finally:
			frappe.set_user(session["user"])
			frappe.local.session.update(session)
			frappe.local.form_dict = form

	return frappe.whitelist(allow_guest=True, xss_safe=True, methods=["POST"])(wrapped)
