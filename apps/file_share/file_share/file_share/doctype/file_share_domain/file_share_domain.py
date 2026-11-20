import frappe
from frappe.model.document import Document

from file_share.publication import ENTRY, epoch, parse_origin


class FileShareDomain(Document):
	def autoname(self):
		self.name, self.origin = self._origin()

	def _origin(self):
		try:
			return parse_origin(self.origin)
		except ValueError as exc:
			frappe.throw(str(exc))

	def validate(self):
		name, self.origin = self._origin()
		before = self.get_doc_before_save()
		if name != self.name or before and self.origin != before.origin:
			frappe.throw("已登记域名的访问地址不能修改，请另外登记新域名")
		if self.status not in {"Pending", "Enabled", "Disabled"}:
			frappe.throw("无效的域名状态")
		self.domain_epoch = before.domain_epoch if before and before.status == self.status else epoch()

	def before_rename(self, old, new, merge=False):
		frappe.throw("分享域名不能更名或合并")

	def on_trash(self):
		if frappe.db.exists(ENTRY, {"domain": self.name}):
			frappe.throw("已有报告使用此域名，请停用而不是删除")

	@frappe.whitelist()
	def impact_count(self):
		self.check_permission("write")
		return frappe.db.count(ENTRY, {"domain": self.name, "enabled": 1})
