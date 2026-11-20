"""Install the site's editable account email defaults with bench execute."""

from pathlib import Path

import frappe


ACCOUNT_MAIL = (
	("welcome_email_template", "BizBase · 新用户欢迎", "欢迎使用 BizBase", "new_user"),
	("reset_password_template", "BizBase · 重置密码", "重置您的 BizBase 密码", "password_reset"),
)


def install():
	settings = frappe.get_single("System Settings")
	for field, name, subject, filename in ACCOUNT_MAIL:
		if settings.get(field) not in (None, "", name):
			raise ValueError(f"已有其他默认模板，请核对 {field}")
		if not frappe.db.exists("Email Template", name):
			path = Path(__file__).parent / "templates" / "emails" / (filename + ".html")
			frappe.get_doc({
				"doctype": "Email Template",
				"name": name,
				"subject": subject,
				"use_html": 1,
				"response_html": path.read_text(encoding="utf-8"),
			}).insert()
	# Only update mail settings. get_footer reads the global default, while User
	# reads the Single, so keep both stores in sync as SystemSettings.save does.
	values = {field: name for field, name, _, _ in ACCOUNT_MAIL}
	values["disable_standard_email_footer"] = 1
	if any(settings.get(field) != value for field, value in values.items()):
		frappe.db.set_single_value("System Settings", values.copy())
		for field, value in values.items():
			frappe.db.set_default(field, value)
		from frappe.core.doctype.system_settings.system_settings import clear_system_settings_cache

		clear_system_settings_cache()
		frappe.local.system_settings = None
