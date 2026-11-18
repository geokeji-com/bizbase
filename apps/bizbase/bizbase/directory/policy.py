"""每请求直接查询提交后的权限事实；不使用角色、用户权限缓存。"""

import frappe

from bizbase.directory.errors import DirectoryError

REFERENCE = "BB Customer Reference"


def actor():
    return frappe.session.user


def has_enabled_role(user, role):
    return bool(frappe.db.sql(
        """SELECT 1 FROM `tabHas Role` hr
           INNER JOIN `tabRole` r ON r.name = hr.role
           INNER JOIN `tabUser` u ON u.name = hr.parent
           WHERE hr.parent = %s AND hr.parenttype = 'User' AND hr.parentfield = 'roles'
             AND hr.role = %s AND r.disabled = 0 AND u.enabled = 1 LIMIT 1""",
        (user, role),
    ))


def require_reader():
    user = actor()
    if user == "Guest" or not has_enabled_role(user, "BB Directory Reader"):
        raise DirectoryError("FORBIDDEN")
    return user


def allowed_references(user):
    """显式授权只匹配引用自身；忽略父客户、默认和任意其他 DocType 的授权。"""
    return frappe.db.sql(
        """SELECT DISTINCT ref.name, ref.source_system, ref.source_customer_id
           FROM `tabUser Permission` permission
           INNER JOIN `tabBB Customer Reference` ref ON ref.name = permission.for_value
           WHERE permission.user = %s AND permission.allow = %s
             AND (permission.apply_to_all_doctypes = 1 OR permission.applicable_for = %s)""",
        (user, REFERENCE, REFERENCE), as_dict=True,
    )


def require_manager():
    user = actor()
    # Administrator 仅允许 bench 内部调用；HTTP 不能借管理函数形成业务旁路。
    is_bench = not getattr(frappe.local, "request", None)
    if user == "Administrator" and is_bench:
        enabled = frappe.db.sql("SELECT enabled FROM `tabUser` WHERE name = %s", (user,))
        if enabled and enabled[0][0]:
            return user
    if user == "Guest" or not has_enabled_role(user, "System Manager"):
        raise DirectoryError("FORBIDDEN")
    return user
