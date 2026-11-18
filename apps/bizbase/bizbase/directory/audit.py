"""原生 Integration Request 只保存最少安全字段。"""

import logging

import frappe
from frappe.integrations.utils import create_request_log

from bizbase.directory.errors import DirectoryError


def rollback_safely():
    try:
        frappe.db.rollback()
    except Exception:
        # 断连时 rollback 自身也可能失败；不能让基础设施异常越过受控错误边界。
        pass


def persist(*, actor, action, outcome, request_id, version=None, count=0, commit=True):
    data = {"actor": actor, "action": action, "outcome": outcome,
            "request_id": request_id, "version": version, "count": count}
    status = "Completed" if outcome in ("success", "empty", "enabled", "disabled", "activated") else "Failed"
    try:
        if commit:
            # Frappe 16.56.0 的该函数会 commit 整个事务，只供只读 RPC / 已回滚的失败使用。
            create_request_log(data, service_name="BizBase Directory", request_id=request_id, status=status)
        else:
            # 管理切换必须与状态指针处于同一个事务，不能提前 commit。
            frappe.get_doc({"doctype": "Integration Request", "integration_request_service": "BizBase Directory",
                            "request_id": request_id, "status": status, "data": frappe.as_json(data)}).insert(ignore_permissions=True)
    except Exception:
        rollback_safely()
        logging.getLogger("bizbase.directory").error("directory_audit_unavailable request_id=%s", request_id)
        raise DirectoryError("AUDIT_UNAVAILABLE") from None
