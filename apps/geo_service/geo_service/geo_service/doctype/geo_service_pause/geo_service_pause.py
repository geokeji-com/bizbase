"""GEO Service Pause：暂停记录，可提交（02 §1）。

只经 geo_service.pause / resume / end_service 新建和关闭；误录由管理员撤销后重录（ST-04）。
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate


class GEOServicePause(Document):
	def validate(self):
		if self.is_new():
			self.recorded_by = frappe.session.user
		self._validate_service()
		self._validate_resumed_once()
		self._validate_no_overlap()

	def on_cancel(self):
		_sync_is_paused(self.service)

	def _validate_service(self):
		"""服务须进行中；暂停起点不早于服务开始日。"""
		status, start_date = frappe.db.get_value("GEO Service", self.service, ["status", "start_date"])
		if status != "Active":
			frappe.throw(_("只能给进行中的服务记录暂停"))
		if start_date and self.paused_from and getdate(self.paused_from) < getdate(start_date):
			frappe.throw(_("暂停起点不能早于服务开始日 {0}").format(start_date))
		if self.resumed_at and get_datetime(self.resumed_at) <= get_datetime(self.paused_from):
			frappe.throw(_("恢复时间必须晚于暂停起点"))

	def _validate_resumed_once(self):
		"""resumed_at 一经写入不可再改。"""
		old = None if self.is_new() else self.get_doc_before_save()
		if old and old.resumed_at and get_datetime(self.resumed_at) != get_datetime(old.resumed_at):
			frappe.throw(_("恢复时间只能写一次，误录请由管理员撤销后重录"))

	def _validate_no_overlap(self):
		"""同一服务的暂停期间不重叠（02 §1.5）。未关闭的记录视为一直延续。"""
		if not self.paused_from:
			return
		others = frappe.get_all(
			"GEO Service Pause",
			filters={"service": self.service, "docstatus": ("!=", 2), "name": ("!=", self.name or "")},
			fields=["name", "paused_from", "resumed_at"],
		)
		from_a = get_datetime(self.paused_from)
		to_a = get_datetime(self.resumed_at) if self.resumed_at else None
		for row in others:
			from_b = get_datetime(row.paused_from)
			to_b = get_datetime(row.resumed_at) if row.resumed_at else None
			if (to_b is None or from_a < to_b) and (to_a is None or from_b < to_a):
				frappe.throw(_("与暂停记录 {0} 的期间重叠").format(row.name))


def _sync_is_paused(service):
	"""按是否还有未关闭的已提交暂停，重算服务的 is_paused。"""
	open_pause = frappe.db.get_value(
		"GEO Service Pause", {"service": service, "docstatus": 1, "resumed_at": ("is", "not set")}, "name"
	)
	frappe.db.sql(
		'UPDATE "tabGEO Service" SET "is_paused" = %s WHERE "name" = %s AND "status" = %s',
		(1 if open_pause else 0, service, "Active"),
	)
