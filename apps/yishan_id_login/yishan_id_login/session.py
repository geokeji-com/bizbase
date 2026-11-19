"""移山 ID 会话的在职复查。

移山 ID 要求：正结果最多缓存 60 秒；控制面故障时最近一次确认最多沿用 5 分钟，之后拒绝访问。
before_request 钩子对每个请求执行 enforce()；非移山 ID 会话直接跳过。
"""

import time

import frappe
from frappe.utils.password import decrypt

from yishan_id_login import auth
from yishan_id_login.auth import BINDING_DOCTYPE, get_valid_settings
from yishan_id_login.oidc import (
	POSITIVE_TTL_SECONDS,
	IdentityInactiveError,
	IdentityStatusUnavailableError,
	check_identity_status,
)

MAXIMUM_STALE_SECONDS = 300
SKIP_PATH_PREFIX = "/api/method/yishan_id_login."


def enforce():
	session = getattr(frappe.local, "session", None)
	if not session or session.user == "Guest" or not session.data.get("yid_uid"):
		return
	if frappe.request and frappe.request.path.startswith(SKIP_PATH_PREFIX):
		return
	data = session.data
	now = time.time()
	token_expiry = data.get("yid_token_exp") or 0
	if now < min(data.get("yid_lease_until") or 0, token_expiry):
		return

	reason = evaluate(data, now)
	if not reason and time.time() >= token_expiry:
		reason = "Yishan ID token expired"
	if reason:
		terminate(reason)
		return
	frappe.local.session_obj.update(force=True)


def evaluate(data: dict, now: float) -> str | None:
	"""复查一次；返回 None 表示放行（并更新 data 中的租约），否则返回拒绝原因。"""
	settings = get_valid_settings()
	if not settings or settings.issuer != data.get("yid_iss"):
		return "Yishan ID configuration changed"
	if now >= data.get("yid_token_exp", 0):
		return "Yishan ID token expired"
	if not still_bound(data["yid_uid"], frappe.session.user):
		return "Yishan ID binding disabled"
	try:
		lease = check_identity_status(
			auth.provider, settings, data["yid_uid"], data["yid_version"], decrypt(data["yid_token"]), now=now
		)
	except IdentityInactiveError:
		return "Yishan ID identity inactive"
	except IdentityStatusUnavailableError:
		now = time.time()
		stale_until = (data.get("yid_verified_at") or 0) + MAXIMUM_STALE_SECONDS
		if now < stale_until:
			# 沿用上一次确认；不延长 verified_at，最近一次确认 5 分钟后仍失败就拒绝。
			data["yid_lease_until"] = min(now + POSITIVE_TTL_SECONDS, stale_until)
			frappe.log_error(title="Yishan ID status unavailable, using recent result")
			return None
		return "Yishan ID status unavailable"
	data["yid_verified_at"] = lease.verified_at
	data["yid_lease_until"] = lease.expires_at
	return None


def still_bound(uid: str, user: str) -> bool:
	binding = frappe.db.get_value(BINDING_DOCTYPE, uid, ["enabled", "user"], as_dict=True)
	return bool(
		binding
		and binding.enabled
		and binding.user == user
		and frappe.db.get_value("User", user, "enabled")
	)


def terminate(reason: str):
	"""按 Frappe 原生退出流程删除当前会话，本次请求降为访客。"""
	frappe.logger("yishan_id_login").info({"event": "session_terminated", "reason": reason, "user": frappe.session.user})
	frappe.local.login_manager.logout()
	frappe.db.commit()
