"""Service-scoped operations for authenticated callers. Native master data is admin-only."""

import frappe
from frappe.utils import getdate


def require_manager():
    frappe.only_for('System Manager')


def require_service(service):
    user = frappe.session.user
    if not isinstance(service, str) or not service or user == 'Guest':
        frappe.throw('无权查看该服务', frappe.PermissionError)
    responsible = frappe.db.get_value('GEO Service', service, 'responsible_user')
    if responsible and (responsible == user or 'System Manager' in frappe.get_roles(user)):
        return service
    membership = frappe.db.get_value('GEO Service Member', {
        'parenttype': 'GEO Service', 'parentfield': 'members', 'parent': service, 'user': user,
    }, ['active_from', 'active_until'], as_dict=True)
    today = getdate()
    if membership and (not membership.active_from or membership.active_from <= today) and (
        not membership.active_until or membership.active_until >= today
    ):
        return service
    frappe.throw('无权查看该服务', frappe.PermissionError)
