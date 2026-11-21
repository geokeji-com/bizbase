"""Read-only terminal inventory. Issuance and revocation are server-managed."""
import frappe
from frappe.model.document import Document

from file_share.permissions import _owner_query, is_employee, is_manager


class FileShareGrant(Document):
	def validate(self):
		frappe.throw("请通过员工授权页签发，或使用「禁用此终端」撤销", frappe.PermissionError)


def grant_query(user=None):
	return _owner_query(user, "File Share Grant", "employee")


def grant_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	return ptype in (None, "select", "read") and (is_manager(user) or (doc.employee == user and is_employee(user)))
