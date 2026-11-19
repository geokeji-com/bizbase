"""Stable share wrapper, password gate, and scoped sandbox content."""

import hashlib
import hmac
import html
import mimetypes
import os
import re
import secrets
from datetime import UTC, datetime
from urllib.parse import quote

import frappe
from frappe.utils import cint
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

from static_share import core
from static_share.permissions import is_employee
from static_share.static_share.doctype.static_share.static_share import content_base

VIEW_TTL = 30 * 60
PASSWORD_TTL = 7 * 24 * 3600
PASSWORD_MAX_FAILURES = 10
PASSWORD_WINDOW = 15 * 60
SANDBOX = "allow-scripts"
CAP_COOKIE = "ss_asset"
CAP_PATTERN = re.compile(r"[A-Za-z0-9_-]{32}\Z")


class ShareRenderer(BaseRenderer):
	def can_render(self):
		return self.path == "s" or self.path.startswith("s/")

	def render(self):
		parts = frappe.request.path.strip("/").split("/")  # Website resolver strips .html
		if len(parts) < 2 or not parts[1]:
			return message(404, "链接不存在", "请检查链接是否完整。")
		share = load_share(parts[1])
		if not share:
			return message(404, "链接不存在或已停用", "请联系分享人确认链接。")
		if len(parts) >= 5 and parts[2] == "c":
			return serve_content(share, parts[3], parts[4], "/".join(parts[5:]))
		if len(parts) == 2:
			return serve_wrapper(share)
		return message(404, "链接不存在", "请检查链接是否完整。")


# ---------- 公共 ----------


def load_share(name: str):
	if not re.fullmatch(r"[A-Za-z0-9]{10}", name) or not frappe.db.exists("Static Share", name):
		return None
	share = frappe.get_doc("Static Share", name)
	return share if share.status == "Active" else None


def signing_key() -> bytes:
	from frappe.utils.password import get_encryption_key

	return hmac.new(get_encryption_key().encode(), b"static_share/v1", hashlib.sha256).digest()


def is_author(share, user: str, **identity) -> bool:
	return share.owner == user and is_employee(user, **identity)


def staff_can_view(share, user, **identity):
	if not is_employee(user, **identity):
		return False
	if share.access_level == "Internal" or share.owner == user:
		return True
	if share.access_level != "Specified":
		return False
	return user in {r.user for r in share.allowed_users} or bool(
		{r.role for r in share.allowed_roles} & set(frappe.get_roles(user))
	)


def viewer_decision(share, user: str) -> str:
	if share.access_level == "Public":
		return "view"
	if share.access_level == "Password":
		if is_author(share, user):
			return "view"
		token = frappe.request.cookies.get(password_cookie(share.name), "")
		return "view" if core.verify(signing_key(), token, "pwd", share.name, share.access_salt) else "password"
	if user == "Guest":
		return "login"
	return "view" if staff_can_view(share, user) else "denied"


def grant_key(token):
	return "static_share:grant:" + token


def asset_grant(share, version):
	if share.access_level == "Public" and version == share.current_version:
		return core.sign(signing_key(), "public", share.name, f"{share.access_salt}:{version}", VIEW_TTL), None

	# A path alone cannot replay a private asset. Store only the independent cookie's digest.
	token = secrets.token_urlsafe(24)
	cookie = secrets.token_urlsafe(24)
	grant = dict(share=share.name, version=version, salt=share.access_salt,
		digest=hashlib.sha256(cookie.encode()).hexdigest())
	user = frappe.session.user
	if version != share.current_version or share.access_level != "Password" or is_author(share, user):
		grant.update(user=user, sid=frappe.session.sid)
	frappe.cache.set_value(grant_key(token), grant, expires_in_sec=VIEW_TTL)
	return token, cookie


def live_session_data(user, sid):
	from frappe.sessions import get_expiry_in_seconds
	from frappe.utils import get_datetime, now_datetime

	if not sid or sid == "Guest":
		return None
	# Sessions is a framework table, not a DocType. This lookup does not extend the session.
	table = frappe.qb.DocType("Sessions")
	record = (frappe.qb.from_(table).select(table.lastupdate, table.sessiondata)
		.where((table.sid == sid) & (table.user == user) & (table.status == "Active")).run())
	if not record:
		return None
	lastupdate, data = record[0]
	data = frappe.parse_json(data or "{}")
	if (end := data.get("session_end")) and datetime.now(UTC) >= datetime.fromisoformat(end):
		return None
	if (now_datetime() - get_datetime(lastupdate)).total_seconds() > get_expiry_in_seconds(data.get("session_expiry")):
		return None
	return data


def asset_allowed(share, version, token):
	if share.access_level == "Public" and version == share.current_version:
		return core.verify(signing_key(), token, "public", share.name, f"{share.access_salt}:{version}")
	cookie = frappe.request.cookies.get(CAP_COOKIE, "")
	if not CAP_PATTERN.fullmatch(token) or not CAP_PATTERN.fullmatch(cookie):
		return False
	grant = frappe.cache.get_value(grant_key(token))
	if not grant or (grant["share"], grant["version"], grant["salt"]) != (share.name, version, share.access_salt):
		return False
	if not hmac.compare_digest(grant["digest"], hashlib.sha256(cookie.encode()).hexdigest()):
		return False
	if user := grant.get("user"):
		data = live_session_data(user, grant["sid"])
		if data is None:
			return False
		if version != share.current_version:
			return is_author(share, user, session_data=data)
		return staff_can_view(share, user, session_data=data)
	return share.access_level == "Password" and version == share.current_version


def log(share, result: str, version: int | None = None):
	try:
		frappe.get_doc(
			{
				"doctype": "Static Share Access Log",
				"share": share.name,
				"share_owner": share.owner,
				"version": version or share.current_version,
				"result": result,
				"viewer": frappe.session.user,
				"ip_address": frappe.local.request_ip,
			}
		).insert(ignore_permissions=True)
		frappe.local.flags.commit = True  # GET 请求默认回滚，访问记录需要落库
	except Exception:
		frappe.log_error("static_share access log failed")


def password_cookie(name: str) -> str:
	return f"ss_{name}"


# ---------- 外壳页 ----------


def serve_wrapper(share):
	user = frappe.session.user
	request = frappe.request

	if share.access_level == "Password" and request.method == "POST":
		return check_password(share)
	if request.method not in ("GET", "HEAD"):
		return message(405, "不支持的请求", "")

	decision = viewer_decision(share, user)
	if decision == "login":
		return redirect(f"/login?redirect-to={quote('/s/' + share.name)}")
	if decision == "password":
		return password_page(share)
	if decision == "denied":
		log(share, "Denied")
		return message(403, "没有查看权限", "这份内容只对指定人员开放，请联系分享人。")

	version = share.current_version
	requested = cint(request.args.get("v"))
	if requested and requested != version and is_author(share, user):
		version = requested  # 分享人可预览历史版本
	entry = next((v.entry for v in share.versions if v.version == version), None)
	if not entry:
		return message(404, "内容不存在", "这个版本已不可用。")

	log(share, "Viewed", version)
	token, cookie = asset_grant(share, version)
	src = f"/s/{share.name}/c/{version}/{token}/{quote(entry)}"
	title = html.escape(share.title)
	body = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
<style>html,body{{margin:0;height:100%;overflow:hidden}}iframe{{border:0;width:100%;height:100%;display:block}}</style>
</head><body>
<iframe src="{html.escape(src)}" title="{title}" sandbox="{SANDBOX}"></iframe>
</body></html>"""
	resp = Response(body, content_type="text/html; charset=utf-8")
	if cookie:
		resp.set_cookie(CAP_COOKIE, cookie, max_age=VIEW_TTL, path=f"/s/{share.name}/c/{version}/{token}/",
			secure=True, httponly=True, samesite="None")
	resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
	resp.headers["Referrer-Policy"] = "no-referrer"
	resp.headers["Cache-Control"] = "no-store"
	resp.headers["X-Robots-Tag"] = "noindex"
	return resp


# ---------- 内容 ----------


def serve_content(share, version_str: str, token: str, rel: str):
	if frappe.request.method not in ("GET", "HEAD"):
		return message(405, "不支持的请求", "")
	if not re.fullmatch(r"[1-9][0-9]{0,8}", version_str):
		return message(404, "内容不存在", "")
	version = int(version_str)
	if not version or not any(v.version == version for v in share.versions):
		return message(404, "内容不存在", "")
	if not asset_allowed(share, version, token):
		return message(403, "链接已过期", "请重新打开分享链接。")

	root = os.path.join(content_base(), share.name, str(version))
	kind, target = core.resolve_request(root, rel)
	if kind == "redirect":
		return redirect(f"/s/{share.name}/c/{version}/{token}/{quote(target)}")
	if kind != "file":
		return message(404, "文件不存在", "")

	mimetype = mimetypes.guess_type(target)[0] or "application/octet-stream"
	if mimetype.startswith("text/") or mimetype in ("application/javascript", "application/json", "image/svg+xml"):
		mimetype += "; charset=utf-8"
	with open(target, "rb") as f:
		data = f.read()
	resp = Response(data, content_type=mimetype)
	# 'self' on a sandboxed document can be opaque. Allow resources only under this
	# exact absolute content prefix, never the entire Frappe origin or other shares.
	scheme = "https" if frappe.request.is_secure or frappe.get_request_header("X-Forwarded-Proto") == "https" else "http"
	assets = f"{scheme}://{frappe.request.host}/s/{share.name}/c/{version}/{token}/"
	resp.headers["Content-Security-Policy"] = (
		f"sandbox {SANDBOX}; default-src 'none'; script-src 'unsafe-inline' {assets}; "
		f"style-src 'unsafe-inline' {assets}; img-src data: {assets}; font-src data: {assets}; "
		f"media-src {assets}; connect-src 'none'; object-src 'none'; frame-src 'none'; "
		"base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
	)
	resp.headers["Referrer-Policy"] = "no-referrer"
	resp.headers["X-Content-Type-Options"] = "nosniff"
	if share.access_level == "Public" and version == share.current_version:
		resp.headers["Access-Control-Allow-Origin"] = "*"
	resp.headers["Cache-Control"] = "private, no-store"
	resp.headers["X-Robots-Tag"] = "noindex"
	return resp


# ---------- 密码 ----------


def check_password(share):
	key = frappe.cache.make_key(f"static_share:pwd:{share.name}:{frappe.local.request_ip}")
	failures = cint(frappe.cache.get(key))
	if failures >= PASSWORD_MAX_FAILURES:
		log(share, "Rate Limited")
		return password_page(share, "尝试次数过多，请 15 分钟后再试。", 429)

	from frappe.utils.password import get_decrypted_password

	expected = get_decrypted_password("Static Share", share.name, "password", raise_exception=False) or ""
	given = frappe.request.form.get("password", "")
	if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
		n = frappe.cache.incr(key)
		if n == 1:
			frappe.cache.expire(key, PASSWORD_WINDOW)
		log(share, "Wrong Password")
		return password_page(share, "密码不正确。", 401)

	frappe.cache.delete(key)
	token = core.sign(signing_key(), "pwd", share.name, share.access_salt, PASSWORD_TTL)
	resp = redirect(f"/s/{share.name}", 303)
	resp.set_cookie(
		password_cookie(share.name),
		token,
		max_age=PASSWORD_TTL,
		path=f"/s/{share.name}",
		httponly=True,
		samesite="Lax",
		secure=frappe.request.is_secure or frappe.get_request_header("X-Forwarded-Proto") == "https",
	)
	return resp


def password_page(share, error: str = "", status: int = 200):
	csrf = ""
	if frappe.session.user != "Guest":
		from frappe.sessions import get_csrf_token

		csrf = f'<input type="hidden" name="csrf_token" value="{html.escape(get_csrf_token())}">'
	err = f'<p class="err">{html.escape(error)}</p>' if error else ""
	body = f"""<form method="post" action="/s/{share.name}">
{csrf}
<label for="pw">访问密码</label>
<input id="pw" name="password" type="password" autocomplete="current-password" required autofocus>
{err}
<button type="submit">查看</button>
</form>"""
	return page(status, html.escape(share.title), "这份内容需要密码才能查看。", body)


# ---------- 页面工具 ----------


def redirect(location: str, status: int = 302):
	resp = Response("", status=status)
	resp.headers["Location"] = location
	resp.headers["Cache-Control"] = "no-store"
	return resp


def message(status: int, title: str, text: str):
	return page(status, html.escape(title), html.escape(text), "")


def page(status: int, title: str, text: str, body: str):
	doc = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
<style>
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f4f5f6;
font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#1f272e}}
main{{background:#fff;padding:32px;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.08);width:min(360px,90vw)}}
h1{{font-size:18px;margin:0 0 8px}}p{{color:#525f6b;font-size:14px;margin:0 0 16px}}
label{{display:block;font-size:13px;margin-bottom:6px}}
input[type=password]{{width:100%;box-sizing:border-box;padding:10px;border:1px solid #d0d5da;border-radius:8px;font-size:15px}}
button{{margin-top:12px;width:100%;padding:10px;border:0;border-radius:8px;background:#234E52;color:#fff;font-size:15px;cursor:pointer}}
.err{{color:#c0392b;margin:8px 0 0}}
</style></head>
<body><main><h1>{title}</h1><p>{text}</p>{body}</main></body></html>"""
	resp = Response(doc, status=status, content_type="text/html; charset=utf-8")
	resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
	resp.headers["Referrer-Policy"] = "no-referrer"
	resp.headers["Cache-Control"] = "no-store"
	resp.headers["X-Robots-Tag"] = "noindex"
	return resp
