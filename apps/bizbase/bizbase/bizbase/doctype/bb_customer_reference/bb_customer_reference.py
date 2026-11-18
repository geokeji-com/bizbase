import frappe
from frappe import _
from frappe.model.document import Document


class BBCustomerReference(Document):
    def validate(self):
        for field in ("source_system", "source_customer_id", "display_name"):
            value = self.get(field)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                frappe.throw(_("来源身份和名称须为非空且无首尾空白的文本"))
        previous = self.get_doc_before_save()
        if previous and any(previous.get(k) != self.get(k) for k in ("source_system", "source_customer_id")):
            frappe.throw(_("已有客户引用的来源身份不能修改"))

    def validate_share(self, share_doc=None):
        frappe.throw(_("客户引用不允许分享，请配置明确的客户读取授权"), frappe.PermissionError)
