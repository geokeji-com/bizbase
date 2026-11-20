"""发布人须是启用的 Desk 用户，且有在职 Employee 绑定。"""

import posixpath
import time
from urllib.parse import unquote

import frappe


def is_employee(user=None, *, session_data=None):
	user = user or frappe.session.user
	if user == "Guest" or not frappe.db.exists("User", {"name": user, "enabled": 1, "user_type": "System User"}):
		return False
	if frappe.db.exists("Employee", {"user_id": user, "status": "Active"}):
		return True
	# Trust only the SSO session that actually completed identity verification. A binding
	# by itself, a local login or a role is not evidence of current employment.
	if session_data is None:
		if user != frappe.session.user:
			return False
		session_data = frappe.session.data or {}
	now = time.time()
	uid = session_data.get("yid_uid")
	return bool(
		uid and session_data.get("user") == user
		and 0 < session_data.get("yid_verified_at", 0) <= now
		and now < min(session_data.get("yid_token_exp", 0), session_data.get("yid_lease_until", 0))
		and frappe.db.exists("Yishan ID Binding", {"name": uid, "user": user, "enabled": 1})
	)


@frappe.whitelist()
def can_upload_report():
	return is_employee()


def is_manager(user):
	return user == "Administrator" or (
		user != "Guest"
		and frappe.db.exists("User", {"name": user, "enabled": 1, "user_type": "System User"})
		and "System Manager" in frappe.get_roles(user)
	)


def can_open_desk():
	return is_employee() or is_manager(frappe.session.user)


def _owner_query(user, doctype, field):
	user = user or frappe.session.user
	if is_manager(user):
		return ""
	if not is_employee(user):
		return "1 = 0"
	return f"`tab{doctype}`.`{field}` = {frappe.db.escape(user)}"


def share_query(user=None):
	return _owner_query(user, "File Share", "owner")


def share_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if ptype == "create" or doc.is_new():
		return is_employee(user)
	return is_manager(user) or (is_employee(user) and doc.owner == user)


def access_log_query(user=None):
	return _owner_query(user, "File Share Access Log", "share_owner")


def access_log_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	return is_manager(user) or (ptype in ("read", "select") and is_employee(user) and doc.share_owner == user)


def validate_file(doc, method=None):
	# Extracted assets have no File rows. Reserve their namespace, including the download_file API.
	url = doc.file_url or ""
	if url.startswith("/private/files/.static_share/"):
		frappe.throw(frappe._("Reserved share content path"), frappe.PermissionError)
	before = doc.get_doc_before_save()
	if before and before.is_private and not doc.is_private and frappe.db.exists(
		"File Share Version", {"source_file": before.file_url}
	):
		frappe.throw(frappe._("Published source files must stay private"), frappe.PermissionError)
	if doc.attached_to_doctype == "File Share" and (not doc.is_private or not is_employee()):
		frappe.throw(frappe._("Share uploads must be private and uploaded by an active employee"), frappe.PermissionError)


def reject_direct_child_save(doc, method=None):
	# A parent save persists validated rows directly. Child REST endpoints call validate separately.
	frappe.throw(frappe._("Edit access through the share form"), frappe.PermissionError)


class ShareFileGuard:
	def before_insert(self):
		# File.before_insert can read and copy an existing blob before the document's validate event.
		url = posixpath.normpath(unquote(self.file_url or ""))
		if url.startswith("/private/files/.static_share/"):
			frappe.throw(frappe._("Reserved share content path"), frappe.PermissionError)
		if self.attached_to_doctype == "File Share" and (not frappe.utils.cint(self.is_private) or not is_employee()):
			frappe.throw(frappe._("Share uploads must be private and uploaded by an active employee"), frappe.PermissionError)
		super().before_insert()
