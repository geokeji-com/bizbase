"""公开只读方法；故意不用类型转换，全部参数由服务严格验证。"""

import frappe

from bizbase.directory.service import read_directory


@frappe.whitelist(methods=["GET", "POST"])
def list_customers(query=None, **kwargs):
    return read_directory("list_customers", query=query, extra=kwargs)


@frappe.whitelist(methods=["GET", "POST"])
def list_subjects(source_system=None, customer_id=None, query=None, **kwargs):
    return read_directory("list_subjects", source_system=source_system, customer_id=customer_id,
                          query=query, extra=kwargs)
