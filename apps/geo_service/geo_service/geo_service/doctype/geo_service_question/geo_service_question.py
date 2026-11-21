"""GEO Service Question：服务问句（02 §2.3–2.4；01 §4.7）。

Draft 由 Ops 或 Admin 创建；activate 批量激活；stop 停止单个。
状态改变只经白名单方法：条件 UPDATE … RETURNING 防并发（02 §0.2）。
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from geo_service.geo_service.doctype.geo_question.geo_question import get_or_create_question
from geo_service.permissions import assert_service_access


class GEOServiceQuestion(Document):
	def before_validate(self):
		"""新建时从 question_text 解析 question，规范化文本（01 §4.7）。"""
		if self.is_new():
			if not self.question_text:
				frappe.throw(_("问句文本必填"))
			self.question = get_or_create_question(self.question_text)
			# 规范化：与全局问句一致
			self.question_text = frappe.db.get_value("GEO Question", self.question, "question_text")
			# 草稿状态
			self.status = "Draft"
			self.effective_from = None
			self.effective_to = None
			self.stop_reason = None

	def validate(self):
		self._validate_service()
		self._validate_quota_slot()
		self._validate_editable_fields()
		self._validate_primary_target()
		self._validate_contract()

	def on_trash(self):
		"""只能删除草稿（02 §2.4）。"""
		if self.status != "Draft":
			frappe.throw(_("只能删除草稿服务问句"))

	def _validate_service(self):
		"""服务存在且未结束（02 §2.4）。"""
		status = frappe.db.get_value("GEO Service", self.service, "status")
		if not status:
			frappe.throw(_("服务 {0} 不存在").format(self.service))
		if status == "Ended":
			frappe.throw(_("服务已结束，不能新增或修改问句"))

	def _validate_quota_slot(self):
		"""名额位范围：1 到合同名额（02 §2.4）。"""
		if not self.quota_slot or self.quota_slot < 1:
			frappe.throw(_("名额位必须至少为 1"))
		# 草稿还没有生效日：取已提交合同中的最大名额；激活时再按生效日当天的合同复核
		quota = frappe.db.sql(
			"""
			SELECT MAX(c.geo_question_quota)
			FROM "tabGEO Service Contract" sc
			INNER JOIN "tabContract" c ON sc.contract = c.name
			WHERE sc.parent = %s AND sc.parenttype = 'GEO Service' AND c.docstatus = 1
			""",
			(self.service,),
		)[0][0]
		if quota and self.quota_slot > quota:
			frappe.throw(_("名额位不能超过合同名额 {0}").format(quota))

	def _validate_editable_fields(self):
		"""草稿可编辑有限字段；非草稿只能经方法改（02 §2.4）。"""
		if self.is_new():
			return
		old = self.get_doc_before_save()
		if not old:
			return

		# question_text 和 question 不可变
		if self.question_text != old.question_text:
			frappe.throw(_("问句文本不可修改；需要换问句请走换词"))
		if self.question != old.question:
			frappe.throw(_("问句链接不可修改"))

		if old.status == "Draft":
			# 草稿可改有限字段
			DRAFT_EDITABLE = {"display_no", "quota_slot", "primary_target", "original_text_note", "note"}
			for field in self.meta.fields:
				if field.fieldname in DRAFT_EDITABLE or field.fieldname in ("modified", "modified_by", "owner", "creation"):
					continue
				old_val = old.get(field.fieldname)
				new_val = self.get(field.fieldname)
				if str(old_val or "") != str(new_val or ""):
					frappe.throw(_("草稿服务问句只能修改：编号、名额位、主要标的、原始文本和备注"))
		else:
			# 非草稿：一律拒绝
			frappe.throw(_("执行中或已停止的服务问句不能修改，只能经操作方法改变"))

	def _validate_primary_target(self):
		"""主要标的属于服务标的（02 §2.4）。"""
		if not self.primary_target:
			return
		exists = frappe.db.exists("GEO Service Target", {"parent": self.service, "parenttype": "GEO Service", "entity": self.primary_target})
		if not exists:
			frappe.throw(_("主要标的 {0} 不在服务标的中").format(self.primary_target))

	def _validate_contract(self):
		"""签约来源时，合同在服务合同中（02 §2.4）。"""
		if self.origin != "Contract Signing" or not self.contract:
			return
		exists = frappe.db.exists("GEO Service Contract", {"parent": self.service, "parenttype": "GEO Service", "contract": self.contract})
		if not exists:
			frappe.throw(_("合同 {0} 不在服务合同中").format(self.contract))


@frappe.whitelist()
def activate_questions(names, effective_from):
	"""批量激活服务问句（02 §2.4）。

	检查：
	- Owner 或 Admin
	- 服务 Draft 或 Active，非 Ended
	- effective_from 在服务期间内
	- 同一问句无重叠区间
	- 同一 quota_slot 当天无其他 Active 行
	- quota_slot 在名额内，Active 计数不超名额
	"""
	if not names:
		frappe.throw(_("未选择任何服务问句"))
	if not effective_from:
		frappe.throw(_("生效日必填"))

	names = frappe.parse_json(names) if isinstance(names, str) else names
	effective_date = getdate(effective_from)

	# 读第一个问句的服务，检查权限和状态
	first = frappe.db.get_value("GEO Service Question", names[0], ["service", "status"], as_dict=True)
	if not first:
		frappe.throw(_("服务问句 {0} 不存在").format(names[0]))

	service = first.service
	assert_service_access(frappe.session.user, service, "owner")

	svc = frappe.get_doc("GEO Service", service)
	if svc.status not in ("Draft", "Active"):
		frappe.throw(_("只能在草稿或进行中的服务激活问句"))

	# 检查生效日在服务期间内
	if svc.start_date and effective_date < getdate(svc.start_date):
		frappe.throw(_("生效日不能早于服务开始日 {0}").format(svc.start_date))
	if svc.planned_end_date and effective_date > getdate(svc.planned_end_date):
		frappe.throw(_("生效日不能晚于计划结束日 {0}").format(svc.planned_end_date))

	# 读名额：使用生效日当天有效的合同
	quota = None
	contracts = frappe.db.sql(
		"""
		SELECT c.name, c.geo_question_quota
		FROM "tabGEO Service Contract" sc
		INNER JOIN "tabContract" c ON sc.contract = c.name
		WHERE sc.parent = %s AND sc.parenttype = 'GEO Service' AND c.docstatus = 1
			AND sc.valid_from <= %s
			AND (sc.valid_to IS NULL OR sc.valid_to >= %s)
		ORDER BY sc.valid_from DESC
		LIMIT 1
		""",
		(service, effective_date, effective_date),
		as_dict=True,
	)
	if contracts:
		quota = contracts[0].geo_question_quota

	# 批量读待激活行
	docs = []
	for name in names:
		doc = frappe.get_doc("GEO Service Question", name)
		if doc.service != service:
			frappe.throw(_("服务问句 {0} 不属于服务 {1}").format(name, service))
		if doc.status != "Draft":
			frappe.throw(_("服务问句 {0} 不是草稿，无法激活").format(name))
		if quota and doc.quota_slot > quota:
			frappe.throw(_("服务问句 {0} 的名额位 {1} 超过合同名额 {2}").format(name, doc.quota_slot, quota))
		docs.append(doc)

	# 检查同一问句无重叠区间：包括 Active 和 Stopped 行，以及本批其他 Draft 行
	for doc in docs:
		existing = frappe.db.sql(
			"""
			SELECT name, effective_from, effective_to, status
			FROM "tabGEO Service Question"
			WHERE service = %s AND question = %s AND name != %s
				AND (status = 'Active' OR (status = 'Stopped' AND (effective_to IS NULL OR effective_to >= %s)))
			""",
			(service, doc.question, doc.name, effective_date),
			as_dict=True,
		)
		for row in existing:
			if not row.effective_to or getdate(row.effective_to) >= effective_date:
				frappe.throw(_("问句 {0} 在服务中已有重叠的执行期间：{1}（{2} 至 {3}）").format(
					doc.question_text, row.name, row.effective_from, row.effective_to or "未设结束日"
				))
		# 检查本批其他待激活行
		for other in docs:
			if other.name != doc.name and other.question == doc.question:
				frappe.throw(_("批量激活中问句 {0} 重复").format(doc.question_text))

	# 检查同一 quota_slot 生效日当天无其他占用行（含本批）
	seen_slots = {}
	for doc in docs:
		if doc.quota_slot in seen_slots:
			frappe.throw(_("批量激活中名额位 {0} 重复：{1} 与 {2}").format(
				doc.quota_slot, seen_slots[doc.quota_slot], doc.name
			))
		seen_slots[doc.quota_slot] = doc.name
		conflict = frappe.db.sql(
			"""
			SELECT name, question_text
			FROM "tabGEO Service Question"
			WHERE service = %s AND quota_slot = %s AND status IN ('Active', 'Stopped')
				AND name != %s
				AND effective_from <= %s
				AND (effective_to IS NULL OR effective_to >= %s)
			""",
			(service, doc.quota_slot, doc.name, effective_date, effective_date),
			as_dict=True,
		)
		if conflict:
			frappe.throw(_("名额位 {0} 在 {1} 已被占用：{2}（{3}）").format(
				doc.quota_slot, effective_date, conflict[0].name, conflict[0].question_text
			))

	# 名额检查（04 UC-06 第 4 步）：生效日占名额的行 + 其他 Draft + 本批，不超过合同名额。
	# 占名额的行：Active 且未结束，或 Stopped 但最后监测日不早于生效日。
	# 换词新端（origin=Replacement）继承旧端名额位，不额外占名额。
	if quota:
		occupied = frappe.db.sql(
			"""
			SELECT COUNT(*)
			FROM "tabGEO Service Question"
			WHERE service = %s AND name NOT IN %s
				AND (
					(status IN ('Active', 'Stopped') AND (effective_to IS NULL OR effective_to >= %s))
					OR (status = 'Draft' AND COALESCE(origin, '') != 'Replacement')
				)
			""",
			(service, tuple(names), effective_date),
		)[0][0]
		total = occupied + len(docs)
		if total > quota:
			frappe.throw(_("激活后问句数 {0} 超过合同名额 {1}，超出 {2} 条").format(total, quota, total - quota))

	# 批量激活：条件 UPDATE
	now = now_datetime()
	activated = []
	for doc in docs:
		rows = frappe.db.sql(
			"""
			UPDATE "tabGEO Service Question"
			SET status = 'Active', effective_from = %s, modified = %s, modified_by = %s
			WHERE name = %s AND status = 'Draft'
			RETURNING name
			""",
			(effective_date, now, frappe.session.user, doc.name),
		)
		if not rows:
			frappe.throw(_("服务问句 {0} 状态已被他人改变，请刷新后重试").format(doc.name))
		activated.append(doc.name)

	return {"activated": activated, "count": len(activated)}


@frappe.whitelist()
def stop(name, effective_to=None, reason=None):
	"""停止服务问句（02 §2.4）。

	Owner 或 Admin。Active → Stopped/Disabled。
	stop_reason 固定为 "Disabled"，reason 参数记为注释。
	拒绝停止有待生效换词的服务问句。
	"""
	doc = frappe.get_doc("GEO Service Question", name)
	assert_service_access(frappe.session.user, doc.service, "owner")

	if doc.status != "Active":
		frappe.throw(_("只能停止执行中的服务问句"))

	# 检查是否有待生效的换词
	pending = frappe.db.exists("GEO Question Replacement", {
		"service": doc.service,
		"old_service_question": name,
		"docstatus": 1,
		"applied_at": ("is", "not set"),
	})
	if pending:
		frappe.throw(_("该服务问句有待生效的换词，不能直接停用"))

	to_date = getdate(effective_to) if effective_to else getdate()
	if doc.effective_from and to_date < getdate(doc.effective_from):
		frappe.throw(_("最后监测日不能早于监测起始日 {0}").format(doc.effective_from))

	rows = frappe.db.sql(
		"""
		UPDATE "tabGEO Service Question"
		SET status = 'Stopped', stop_reason = 'Disabled', effective_to = %s, modified = %s, modified_by = %s
		WHERE name = %s AND status = 'Active'
		RETURNING name
		""",
		(to_date, now_datetime(), frappe.session.user, name),
	)
	if not rows:
		frappe.throw(_("服务问句状态已被他人改变，请刷新后重试"))

	if reason:
		frappe.get_doc("GEO Service Question", name).add_comment("Comment", _("停用原因：{0}").format(reason))

	return {"status": "Stopped", "stop_reason": "Disabled", "effective_to": str(to_date)}
