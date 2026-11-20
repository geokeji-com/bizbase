import frappe
from frappe.model.document import Document


class FileShareEntry(Document):
	def validate(self):
		# Frappe saves validated child rows through their parent using db_insert/update.
		frappe.throw("请在文件分享表单中修改发布入口", frappe.PermissionError)

	def on_trash(self):
		frappe.throw("请在文件分享表单中移除发布入口", frappe.PermissionError)
