__version__ = "0.1.0"


def can_manage_bindings():
	import frappe

	return "System Manager" in frappe.get_roles() and frappe.has_permission("Yishan ID Binding", "read")
