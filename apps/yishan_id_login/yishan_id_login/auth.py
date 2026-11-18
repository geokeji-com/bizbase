"""移山 ID 登录入口、回调与后端通知退出。"""

import hashlib
import os
import pickle
import secrets
import time
from datetime import UTC, datetime
from urllib.parse import quote, urlparse

import frappe
from frappe import _
from frappe.utils.password import encrypt
from yishan_id_login import managed

from yishan_id_login.oidc import (
	DEFAULT_DIRECT_SIGN_IN,
	DEFAULT_MAX_AUTH_AGE_SECONDS,
	DEFAULT_SCOPES,
	OIDCError,
	Provider,
	Settings,
	authorization_url,
	exchange_code,
	new_pkce,
	random_token,
	validate_settings,
	verify_logout_token,
)

BINDING_DOCTYPE = "Yishan ID Binding"
TRANSACTION_TTL_SECONDS = 600
BROWSER_COOKIE = "yid_login"
START_PATH = "/api/method/yishan_id_login.auth.start"
RESERVED_USERS = ("Administrator", "Guest")

provider = Provider()


def get_settings() -> Settings | None:
	"""读取站点配置；缺少必填项时返回 None（不显示按钮）。"""
	conf = frappe.conf
	if not (conf.get("yishan_id_issuer") and conf.get("yishan_id_client_id") and conf.get("yishan_id_redirect_uri")):
		return None
	return Settings(
		issuer=conf.yishan_id_issuer,
		client_id=conf.yishan_id_client_id,
		redirect_uri=conf.yishan_id_redirect_uri,
		client_secret=conf.get("yishan_id_client_secret") or None,
		audience=conf.get("yishan_id_audience") or None,
		status_url=conf.get("yishan_id_status_url") or None,
		scopes=conf.get("yishan_id_scopes") or DEFAULT_SCOPES,
		direct_sign_in=conf.get("yishan_id_direct_sign_in", DEFAULT_DIRECT_SIGN_IN) or None,
		max_auth_age_seconds=int(conf.get("yishan_id_max_auth_age_seconds") or DEFAULT_MAX_AUTH_AGE_SECONDS),
	)


def get_valid_settings(*, require_verified=False) -> Settings | None:
	if path := os.environ.get('BIZBASE_YISHAN_ID_CONFIG'):
		return managed.load(path, require_verified=require_verified)
	settings = get_settings()
	if not settings:
		return None
	try:
		validate_settings(settings)
	except OIDCError:
		frappe.log_error(title="Yishan ID settings invalid")
		return None
	return settings


def safe_redirect(value: str | None, default: str = "/desk") -> str:
	"""只允许站内相对路径，防止开放重定向。"""
	if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
		return default
	parsed = urlparse(value)
	if parsed.scheme or parsed.netloc:
		return default
	return value


def start_url(redirect_to: str | None) -> str:
	return f"{START_PATH}?redirect_to={quote(safe_redirect(redirect_to), safe='')}"


def login_page_context(context):
	"""update_website_context 钩子：在 /login 页增加移山 ID 按钮。"""
	if context.get("for_test") != "login.html" or frappe.session.user != "Guest":
		return
	if not get_valid_settings(require_verified=True):
		return
	providers = list(context.get("provider_logins") or [])
	providers.insert(
		0,
		{
			"name": "yishan_id",
			"provider_name": _("Yishan ID"),
			"auth_url": start_url(frappe.local.request.args.get("redirect-to")),
			"icon": '<img src="/assets/yishan_id_login/yishan-id.svg" alt="">',
		},
	)
	return {"provider_logins": providers, "social_login": True}


@frappe.whitelist(allow_guest=True)
def hrms_oauth_providers():
	"""覆盖 HR 移动端登录页的第三方登录列表，在原列表前加入移山 ID。"""
	from hrms.api.oauth import oauth_providers

	out = oauth_providers()
	if get_valid_settings(require_verified=True):
		out.insert(
			0,
			{
				"name": "yishan_id",
				"provider_name": _("Yishan ID"),
				"auth_url": start_url("/hrms"),
				"icon": "/assets/yishan_id_login/yishan-id.svg",
			},
		)
	return out


def _hash(value: str) -> str:
	return hashlib.sha256(value.encode()).hexdigest()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def start(redirect_to: str | None = None):
	settings = get_valid_settings(require_verified=True)
	if not settings:
		return error_page(_("Yishan ID login is not configured."), 503)

	state, nonce, browser_binding = random_token(), random_token(), random_token()
	verifier, _challenge = new_pkce()
	frappe.cache.set_value(
		f"yishan_id_login:txn:{_hash(state)}",
		{
			"nonce": nonce,
			"verifier": verifier,
			"browser": _hash(browser_binding),
			"redirect_to": safe_redirect(redirect_to),
		},
		expires_in_sec=TRANSACTION_TTL_SECONDS,
	)
	frappe.local.cookie_manager.set_cookie(
		BROWSER_COOKIE, browser_binding, max_age=TRANSACTION_TTL_SECONDS, httponly=True
	)
	try:
		location = authorization_url(provider, settings, state, nonce, verifier)
	except OIDCError:
		frappe.log_error(title="Yishan ID start failed")
		return error_page(_("Yishan ID is temporarily unavailable. Please try again later."), 503)
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = location


def _pop_transaction(state: str) -> dict | None:
	"""原子地取出并删除登录事务，保证 state 只能使用一次。"""
	raw = frappe.cache.getdel(frappe.cache.make_key(f"yishan_id_login:txn:{_hash(state)}"))
	return pickle.loads(raw) if raw else None


@frappe.whitelist(allow_guest=True, methods=["GET"])
def callback(code: str | None = None, state: str | None = None, error: str | None = None, **kwargs):
	settings = get_valid_settings(require_verified=True)
	if not settings:
		return error_page(_("Yishan ID login is not configured."), 503)
	if not state:
		return error_page(_("The login request is invalid. Please try again."))
	txn = _pop_transaction(state)
	browser_binding = frappe.request.cookies.get(BROWSER_COOKIE) or ""
	frappe.local.cookie_manager.delete_cookie(BROWSER_COOKIE)
	if not txn or not secrets.compare_digest(txn["browser"], _hash(browser_binding)):
		return error_page(_("The login request is invalid or has expired. Please try again."))
	if error:
		return error_page(_("Yishan ID did not complete the login. Please try again."))
	if not code:
		return error_page(_("The login request is invalid. Please try again."))

	try:
		principal = exchange_code(provider, settings, code, txn["verifier"], txn["nonce"])
	except OIDCError as e:
		frappe.log_error(title="Yishan ID callback rejected", message=str(e))
		return error_page(_("Yishan ID login failed. Please try again."))

	user = bound_user(principal)
	if not user:
		return error_page(
			_(
				"Your Yishan ID ({0}) is not linked to a BizBase account yet. Please ask an administrator to link it."
			).format(principal.yishan_uid),
			403,
		)

	session_end = datetime.fromtimestamp(principal.expires_at, UTC).isoformat()
	frappe.local.login_manager.login_as(user, session_end=session_end)
	now = time.time()
	frappe.local.session_obj.data.data.update(
		{
			"yid_uid": principal.yishan_uid,
			"yid_version": principal.identity_version,
			"yid_iss": principal.issuer,
			"yid_sub": principal.subject,
			"yid_sid": principal.sid,
			"yid_token": encrypt(principal.access_token),
			"yid_token_exp": principal.expires_at,
			# 回调前移山 ID 已在签发令牌时确认在职；下一次请求开始复查。
			"yid_verified_at": now,
			"yid_lease_until": 0,
		}
	)
	frappe.local.session_obj.update(force=True)
	frappe.db.set_value(BINDING_DOCTYPE, principal.yishan_uid, "last_login", frappe.utils.now(), update_modified=False)
	frappe.db.commit()

	from frappe.utils.oauth import redirect_post_login

	redirect_post_login(
		desk_user=frappe.db.get_value("User", user, "user_type") == "System User",
		redirect_to=txn["redirect_to"],
	)


def bound_user(principal) -> str | None:
	"""按 yishan.uid 找已启用的绑定；没有记录时登记一条待确认绑定。"""
	binding = frappe.db.get_value(
		BINDING_DOCTYPE, principal.yishan_uid, ["enabled", "user"], as_dict=True
	)
	if not binding:
		try:
			frappe.get_doc(
				{
					"doctype": BINDING_DOCTYPE,
					"yishan_uid": principal.yishan_uid,
					"display_name": principal.name,
					"enabled": 0,
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()
		except frappe.DuplicateEntryError:
			# 并发的首次登录已经登记过。
			frappe.db.rollback()
		return None
	if not binding.enabled or not binding.user or binding.user in RESERVED_USERS:
		return None
	if not frappe.db.get_value("User", binding.user, "enabled"):
		return None
	return binding.user


@frappe.whitelist(allow_guest=True, methods=["POST"])
def backchannel_logout(logout_token: str | None = None, **kwargs):
	"""OIDC Back-Channel Logout：撤销对应移山 ID 会话的全部 BizBase 会话。"""
	settings = get_valid_settings()
	if not settings or not logout_token:
		frappe.local.response["http_status_code"] = 400
		return {"error": "invalid_request"}
	try:
		claims = verify_logout_token(provider, settings, logout_token)
	except OIDCError as e:
		frappe.log_error(title="Yishan ID back-channel logout rejected", message=str(e))
		frappe.local.response["http_status_code"] = 400
		return {"error": "invalid_request"}
	revoke_sessions(settings.issuer, claims.get("sub"), claims.get("sid"))
	frappe.local.response.pop("message", None)
	return None


def revoke_sessions(issuer: str, sub: str | None = None, sid: str | None = None, uid: str | None = None) -> int:
	"""删除匹配的移山 ID 会话；重复调用是幂等的。"""
	from frappe.sessions import delete_session

	Sessions = frappe.qb.DocType("Sessions")
	rows = (
		frappe.qb.from_(Sessions)
		.select(Sessions.sid, Sessions.sessiondata)
		.where(Sessions.sessiondata.like('%"yid_uid"%'))
		.run(as_dict=True)
	)
	count = 0
	for row in rows:
		data = frappe.parse_json(row.sessiondata or "{}")
		if data.get("yid_iss") != issuer:
			continue
		if sub and data.get("yid_sub") != sub:
			continue
		if sid and data.get("yid_sid") != sid:
			continue
		if uid and data.get("yid_uid") != uid:
			continue
		delete_session(row.sid, reason="Yishan ID logout")
		count += 1
	frappe.db.commit()
	return count


def error_page(message: str, http_status_code: int = 400):
	frappe.respond_as_web_page(
		_("Yishan ID Login"),
		message,
		http_status_code=http_status_code,
		indicator_color="red",
		primary_action="/login",
		primary_label=_("Back to Login"),
	)
