from urllib.parse import quote

import frappe
from frappe.sessions import get_csrf_token

from file_share.cli_auth import pending_device
from file_share.permissions import is_employee

no_cache = True
sitemap = False


def get_context(context):
	frappe.local.response_headers.update({
		"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer",
		"Content-Security-Policy": "frame-ancestors 'none'", "X-Frame-Options": "DENY",
	})
	challenge = frappe.request.args.get("challenge", "")
	label = pending_device(challenge)
	if frappe.session.user == "Guest":
		path = "/file-share-authorize?challenge=" + challenge
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(path, safe="")
		raise frappe.Redirect
	if not is_employee():
		frappe.throw("请使用在职员工账号", frappe.PermissionError)
	return {"device_label": label, "challenge": challenge, "match_code": challenge[:8].upper(), "account": frappe.session.user,
		"approval_csrf": get_csrf_token(), "no_cache": True}
