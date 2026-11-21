"""GEO Question Replacement：换词，1 换 1（02 §2.5–2.7；04 UC-10）。

草稿：Ops 录新文本，服务端建 Draft 新服务问句（origin=Replacement）。
提交：Owner 或 Admin；effective_date 为今天时立即生效，否则由每日作业 apply_due_replacements 生效。
已提交待生效与已生效都是 docstatus=1，用 applied_at 区分；已生效的换词不能作废。
采集点与监测计划的连带调整属于 S2，届时在 _on_submit_slots / _swap_plan_rows 接入。
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime

from geo_service.geo_service.doctype.geo_question.geo_question import get_or_create_question
from geo_service.permissions import assert_service_access

SQ = "GEO Service Question"


class GEOQuestionReplacement(Document):
	def validate(self):
		self._validate_service()
		old = self._validate_old()
		self._sync_new_service_question(old)
		self._validate_new(old)
		if not (self.confirmed_by_user or self.confirmed_by_contact):
			frappe.throw(_("确认人必填：内部确认人或客户联系人至少填一个"))
		if self.effective_date and old.effective_from and getdate(self.effective_date) <= getdate(old.effective_from):
			frappe.throw(_("生效日必须晚于旧问句的监测起始日 {0}").format(old.effective_from))

	def before_submit(self):
		assert_service_access(frappe.session.user, self.service, "owner")
		if getdate(self.effective_date) < getdate():
			frappe.throw(_("生效日不能早于今天"))

	def on_submit(self):
		if getdate(self.effective_date) <= getdate():
			_apply(self.name)

	def before_cancel(self):
		assert_service_access(frappe.session.user, self.service, "owner")
		if frappe.db.get_value(self.doctype, self.name, "applied_at"):
			frappe.throw(_("已生效的换词不能作废；要换回请再建一条反向换词"))

	def on_cancel(self):
		_delete_draft_sq(self.new_service_question)

	def on_trash(self):
		if self.docstatus == 0:
			_delete_draft_sq(self.new_service_question)

	def _validate_service(self):
		status = frappe.db.get_value("GEO Service", self.service, "status")
		if not status:
			frappe.throw(_("服务 {0} 不存在").format(self.service))
		if status == "Ended":
			frappe.throw(_("服务已结束，不能换词"))

	def _validate_old(self):
		old = frappe.db.get_value(
			SQ, self.old_service_question,
			["name", "service", "status", "question", "question_text", "quota_slot", "primary_target", "effective_from"],
			as_dict=True,
		)
		if not old or old.service != self.service:
			frappe.throw(_("旧服务问句不属于本服务"))
		if old.status != "Active":
			frappe.throw(_("只能替换执行中的服务问句"))
		other = frappe.db.get_value(
			self.doctype,
			{"old_service_question": old.name, "docstatus": ("!=", 2), "name": ("!=", self.name or "")},
			"name",
		)
		if other:
			frappe.throw(_("旧服务问句已有换词记录 {0}，一条问句只能换一次").format(other))
		self.old_question_text = old.question_text
		return old

	def _sync_new_service_question(self, old):
		"""按新文本建或重建 Draft 新服务问句。文本改了就删掉旧草稿重建，问句关联不可改。"""
		text = (self.new_question_text or "").strip()
		if not text:
			frappe.throw(_("新问句文本必填"))
		self.new_question_text = text
		question = get_or_create_question(text)
		if question == old.question:
			frappe.throw(_("新问句与旧问句相同"))

		if self.new_service_question:
			current = frappe.db.get_value(SQ, self.new_service_question, ["question", "status", "origin"], as_dict=True)
			if current and current.question == question:
				return
			if current:
				if current.status != "Draft" or current.origin != "Replacement":
					frappe.throw(_("新服务问句已不是换词草稿，不能更换文本"))
				# 先断开链接再删，避免 Link 校验拦截
				old_new = self.new_service_question
				self.new_service_question = None
				if not self.is_new():
					frappe.db.set_value(self.doctype, self.name, "new_service_question", None, update_modified=False)
				_delete_draft_sq(old_new)

		self._check_not_in_service(question)
		sq = frappe.get_doc({
			"doctype": SQ,
			"service": self.service,
			"question_text": text,
			"origin": "Replacement",
			"quota_slot": old.quota_slot,
			"primary_target": old.primary_target,
		})
		sq.insert(ignore_permissions=True)
		self.new_service_question = sq.name

	def _check_not_in_service(self, question, exclude=None):
		"""新问句不能与本服务其他有效服务问句相同（Draft、Active，或生效日仍在期内的 Stopped）。"""
		day = getdate(self.effective_date) if self.effective_date else getdate()
		dup = frappe.db.sql(
			"""
			SELECT name FROM "tabGEO Service Question"
			WHERE service = %s AND question = %s AND name != %s
				AND (status IN ('Draft', 'Active') OR (status = 'Stopped' AND effective_to >= %s))
			LIMIT 1
			""",
			(self.service, question, exclude or "", day),
		)
		if dup:
			frappe.throw(_("本服务已在监测该问句：{0}").format(dup[0][0]))

	def _validate_new(self, old):
		new = frappe.db.get_value(SQ, self.new_service_question, ["service", "status", "origin", "question"], as_dict=True)
		if not new or new.service != self.service or new.status != "Draft" or new.origin != "Replacement":
			frappe.throw(_("新服务问句必须是本服务尚未启用的换词草稿"))
		self._check_not_in_service(new.question, exclude=self.new_service_question)


def _delete_draft_sq(name):
	if name and frappe.db.get_value(SQ, name, "status") == "Draft":
		frappe.delete_doc(SQ, name, ignore_permissions=True, force=True)


def _apply(name):
	"""生效：旧端 Stopped/Replaced，新端 Active，写 applied_at。全部是条件更新（02 §0.2、§2.6）。"""
	rep = frappe.db.get_value(
		"GEO Question Replacement", name,
		["name", "service", "old_service_question", "new_service_question", "effective_date", "docstatus", "applied_at"],
		as_dict=True,
	)
	if rep.docstatus != 1 or rep.applied_at:
		return False
	day = getdate(rep.effective_date)
	now = now_datetime()
	user = frappe.session.user

	old = frappe.db.sql(
		"""
		UPDATE "tabGEO Service Question"
		SET status = 'Stopped', stop_reason = 'Replaced', effective_to = %s, modified = %s, modified_by = %s
		WHERE name = %s AND status = 'Active'
		RETURNING quota_slot
		""",
		(add_days(day, -1), now, user, rep.old_service_question),
	)
	if not old:
		frappe.throw(_("旧服务问句状态已被他人改变，请刷新后重试"))

	new = frappe.db.sql(
		"""
		UPDATE "tabGEO Service Question"
		SET status = 'Active', effective_from = %s, quota_slot = %s, modified = %s, modified_by = %s
		WHERE name = %s AND status = 'Draft'
		RETURNING name
		""",
		(day, old[0][0], now, user, rep.new_service_question),
	)
	if not new:
		frappe.throw(_("新服务问句状态已被他人改变，请刷新后重试"))

	done = frappe.db.sql(
		"""
		UPDATE "tabGEO Question Replacement"
		SET applied_at = %s, modified = %s, modified_by = %s
		WHERE name = %s AND docstatus = 1 AND applied_at IS NULL
		RETURNING name
		""",
		(now, now, user, name),
	)
	if not done:
		frappe.throw(_("换词已被他人执行，请刷新后重试"))

	# 问句分组跟随（01 line 788）：将标记 follow_replacements=1 的旧问句 item 改为新问句
	_swap_in_groups(rep.service, rep.old_service_question, rep.new_service_question)
	return True


def _swap_in_groups(service, old_sq, new_sq):
	"""换词后自动更新问句分组：将 follow_replacements=1 的 item 从旧问句改为新问句。

	单个分组失败不拦截换词：回滚到该分组的保存点后记日志。
	PostgreSQL 在语句报错后整个事务失效，不回滚到保存点就无法继续。
	"""
	groups = frappe.get_all(
		"GEO Question Group Item",
		filters={"parenttype": "GEO Question Group", "service_question": old_sq, "follow_replacements": 1},
		pluck="parent",
		distinct=True,
	)
	new_text = frappe.db.get_value(SQ, new_sq, "question_text")
	for group_name in groups:
		if frappe.db.get_value("GEO Question Group", group_name, "service") != service:
			continue
		frappe.db.savepoint("geo_group_swap")
		try:
			group = frappe.get_doc("GEO Question Group", group_name)
			for item in group.items:
				if item.service_question == old_sq and item.follow_replacements:
					item.service_question = new_sq
					item.question_text = new_text
			group.save(ignore_permissions=True)
		except Exception:
			frappe.db.rollback(save_point="geo_group_swap")
			frappe.log_error(title=f"问句分组 {group_name} 换词跟随失败")
		else:
			frappe.db.release_savepoint("geo_group_swap")


def apply_due_replacements():
	"""每日 00:05 作业（03 §1.4 作业 D）：执行生效日已到的待生效换词。逐条提交，一条失败不影响其他。"""
	names = frappe.get_all(
		"GEO Question Replacement",
		filters={"docstatus": 1, "applied_at": ("is", "not set"), "effective_date": ("<=", getdate())},
		order_by="effective_date asc",
		pluck="name",
	)
	for name in names:
		try:
			_apply(name)
			frappe.db.commit()  # nosemgrep: 后台作业逐条提交
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"换词生效失败 {name}")
