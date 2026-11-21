import frappe
from frappe.model.document import Document
from task_execution.validation import canonical, schema


class ExecutionCapability(Document):
    def validate(self):
        try:
            self.parameter_schema = canonical(schema(self.parameter_schema))
        except ValueError as exc:
            frappe.throw(str(exc))
        prior = self.get_doc_before_save()
        keys = ('capability_key', 'operation', 'platform', 'channel', 'version_tag', 'parameter_schema')
        if prior and any(prior.get(key) != self.get(key) for key in keys):
            frappe.throw('能力版本内容固定。变更请新建版本并按需停用旧版本。')
