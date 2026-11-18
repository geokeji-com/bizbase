import frappe
from frappe import _
from frappe.model.document import Document

from yishan_id_login.oidc import YID_UID_PATTERN

RESERVED_USERS = ("Administrator", "Guest")


class YishanIDBinding(Document):
	def validate(self):
		self.yishan_uid = (self.yishan_uid or "").strip().lower()
		if not YID_UID_PATTERN.match(self.yishan_uid):
			frappe.throw(_("Yishan UID must be a lowercase UUID issued by Yishan ID."))
		if self.user in RESERVED_USERS:
			frappe.throw(_("{0} cannot be linked to a Yishan ID.").format(self.user))
		if self.enabled and not self.user:
			frappe.throw(_("Select a user before enabling this binding."))

	def on_update(self):
		# 停用、换绑或改用户时，立即撤销此前以该移山 ID 建立的会话。
		before = self.get_doc_before_save()
		if before and before.enabled and (not self.enabled or before.user != self.user):
			from yishan_id_login.auth import get_valid_settings, revoke_sessions

			settings = get_valid_settings()
			if settings:
				revoke_sessions(settings.issuer, uid=self.yishan_uid)

	def on_trash(self):
		from yishan_id_login.auth import get_valid_settings, revoke_sessions

		settings = get_valid_settings()
		if settings:
			revoke_sessions(settings.issuer, uid=self.yishan_uid)
