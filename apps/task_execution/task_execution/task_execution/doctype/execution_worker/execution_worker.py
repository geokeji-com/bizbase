import frappe
from frappe.model.document import Document


class ExecutionWorker(Document):
    def validate(self):
        if self.worker_user in ('Administrator', 'Guest') or 'System Manager' in frappe.get_roles(self.worker_user):
            frappe.throw('请使用没有系统管理权限的专用执行用户')
        if len({row.capability for row in self.capabilities}) != len(self.capabilities):
            frappe.throw('Worker 的能力版本重复')
        prior = self.get_doc_before_save()
        if prior and prior.worker_user != self.worker_user:
            frappe.throw('执行用户不能更换，请登记新 Worker')
