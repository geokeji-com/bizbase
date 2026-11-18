import json

import frappe


def ensure_model():
    """仅初始化本 App 的模型、角色和关闭状态；不导入数据或授予客户。"""
    if not frappe.db.exists("Role", "BB Directory Reader"):
        frappe.get_doc({"doctype": "Role", "role_name": "BB Directory Reader", "desk_access": 1}).insert(ignore_permissions=True)
    frappe.db.add_unique("BB Customer Reference", ["source_system", "source_customer_id"], "uniq_bb_customer_source")
    if not frappe.db.exists("DefaultValue", {"parent": "__global", "defkey": "bizbase_directory_state"}):
        frappe.db.set_global("bizbase_directory_state", json.dumps({"enabled": False, "active": None}))
