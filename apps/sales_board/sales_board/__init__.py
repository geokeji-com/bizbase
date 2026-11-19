__version__ = "0.0.1"


def can_access_app():
    import frappe

    return "System Manager" in frappe.get_roles()
