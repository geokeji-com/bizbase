"""GEO Question Group：问句分组（01 §4.7 line 786–788），看板侧的服务问句聚合视图。

group_name 同一服务内唯一。items 中同一 service_question 只能出现一次。
follow_replacements=1 的 item，换词后自动切换到新服务问句（由 geo_question_replacement._apply 回调）。
"""

import frappe
from frappe import _
from frappe.model.document import Document


class GEOQuestionGroup(Document):
	def validate(self):
		self._validate_service()
		self._validate_group_name()
		self._validate_items()

	def _validate_service(self):
		"""服务存在且未结束。"""
		status = frappe.db.get_value("GEO Service", self.service, "status")
		if not status:
			frappe.throw(_("服务 {0} 不存在").format(self.service))
		if status == "Ended":
			frappe.throw(_("服务已结束，不能新建或修改问句分组"))

	def _validate_group_name(self):
		"""同服务 group_name 唯一（01 line 786）。"""
		existing = frappe.db.get_value(
			self.doctype,
			{"service": self.service, "group_name": self.group_name, "name": ("!=", self.name or "")},
			"name",
		)
		if existing:
			frappe.throw(_("该服务已有同名分组 {0}").format(existing))

	def _validate_items(self):
		"""items 中 service_question 同服务、唯一、存在（01 line 788）。"""
		if not self.items:
			return
		seen = set()
		for row in self.items:
			if not row.service_question:
				continue
			sq = frappe.db.get_value("GEO Service Question", row.service_question, ["service", "status"], as_dict=True)
			if not sq:
				frappe.throw(_("服务问句 {0} 不存在").format(row.service_question))
			if sq.service != self.service:
				frappe.throw(_("服务问句 {0} 不属于本服务").format(row.service_question))
			if row.service_question in seen:
				frappe.throw(_("服务问句 {0} 在分组中重复").format(row.service_question))
			seen.add(row.service_question)
