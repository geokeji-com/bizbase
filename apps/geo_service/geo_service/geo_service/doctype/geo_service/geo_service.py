"""GEO Service：服务生命周期（02 §1）。

状态字段只经本模块的白名单方法改变：条件更新（WHERE 当前状态）防并发，
同一请求内一个事务，不在请求里 commit。暂停记录的状态联动见 geo_service_pause.py。
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime

from geo_service.permissions import OPERATIONS, SALES, assert_service_access, is_admin

# 任何人都不能经表单直接改的字段。
STATE_FIELDS = ("status", "is_paused", "actual_end_date", "reopen_reason")
# 离开草稿后只能经延期等方法改的字段。
LOCKED_AFTER_DRAFT = ("start_date", "planned_end_date", "served_customer")


def _norm(value):
	return "" if value in (None, "", 0) else str(value)


def _active_on(row, day, start="from_date", end="to_date"):
	return getdate(row.get(start)) <= day and (not row.get(end) or getdate(row.get(end)) >= day)


def _holds_operations(user):
	return bool(user) and frappe.db.exists("User", {"name": user, "enabled": 1}) and OPERATIONS in frappe.get_roles(user)


class GEOService(Document):
	def before_insert(self):
		self.status = "Draft"
		self.is_paused = 0
		self.actual_end_date = None
		self.reopen_reason = None
		self._auto_add_creator_as_sales()

	def validate(self):
		self._protect_fields()
		self._validate_dates()
		self._validate_contract_rows()
		self._validate_members()
		if self.is_new():
			self._require_owner()
		if self.status == "Draft":
			self._default_planned_end_date()

	def on_trash(self):
		"""只能删除没有下属记录的草稿服务。"""
		if self.status != "Draft":
			frappe.throw(_("只能删除草稿服务"))
		sq_count = frappe.db.count("GEO Service Question", {"service": self.name})
		if sq_count:
			frappe.throw(_("该服务已有 {0} 个问句，无法删除").format(sq_count))

	def _protect_fields(self):
		"""状态字段和离开草稿后锁定的字段，只能经白名单方法改（02 §0.2）。"""
		if self.is_new():
			return
		old = self.get_doc_before_save()
		if not old:
			return
		for field in STATE_FIELDS:
			if _norm(self.get(field)) != _norm(old.get(field)):
				frappe.throw(_("不能直接修改 {0}，请用相应的操作方法").format(frappe.get_meta("GEO Service").get_field(field).label))
		if old.status != "Draft":
			for field in LOCKED_AFTER_DRAFT:
				if _norm(self.get(field)) != _norm(old.get(field)):
					frappe.throw(_("服务启动后不能修改 {0}").format(frappe.get_meta("GEO Service").get_field(field).label))

	def _validate_dates(self):
		"""开始日与计划结束日不能倒挂。"""
		if self.start_date and self.planned_end_date and getdate(self.start_date) > getdate(self.planned_end_date):
			frappe.throw(_("开始日不能晚于计划结束日"))

	def _validate_contract_rows(self):
		"""合同行的合同必须是提交状态的 Contract（02 §1.3 activate 检查）。"""
		for row in self.contracts:
			if not row.contract:
				continue
			contract = frappe.get_doc("Contract", row.contract)
			if contract.docstatus != 1:
				frappe.throw(_("合同 {0} 未提交，不能关联").format(row.contract))

	def _validate_members(self):
		"""成员行：同一用户期间不重叠，每日至多一个 Owner（02 §1.3）。"""
		if not self.members:
			return
		by_user = {}
		for row in self.members:
			if not row.user or not row.from_date:
				continue
			if row.user not in by_user:
				by_user[row.user] = []
			by_user[row.user].append(row)

		for user, rows in by_user.items():
			rows = sorted(rows, key=lambda r: getdate(r.from_date))
			for i in range(len(rows) - 1):
				a, b = rows[i], rows[i + 1]
				if a.to_date and getdate(a.to_date) >= getdate(b.from_date):
					frappe.throw(_("成员 {0} 的期间重叠：{1} 至 {2} 与 {3} 至 {4}").format(
						user, a.from_date, a.to_date or "（无结束日）", b.from_date, b.to_date or "（无结束日）"
					))

		owner_rows = [r for r in self.members if r.member_role == "Owner"]
		if len(owner_rows) > 1:
			owner_rows = sorted(owner_rows, key=lambda r: getdate(r.from_date))
			for i in range(len(owner_rows) - 1):
				a, b = owner_rows[i], owner_rows[i + 1]
				a_end = getdate(a.to_date) if a.to_date else None
				b_start = getdate(b.from_date)
				if a_end is None or a_end >= b_start:
					frappe.throw(_("每日至多一个负责人：{0} 与 {1} 的负责人期间重叠").format(a.user, b.user))

	def _require_owner(self):
		"""新建服务时必须指定一个 Owner，且该 Owner 持有 GEO Operations（04 line 185）。"""
		owner_rows = [m for m in self.members if m.member_role == "Owner"]
		if not owner_rows:
			frappe.throw(_("新建服务时必须指定一个负责人"))
		if len(owner_rows) > 1:
			frappe.throw(_("新建服务时只能指定一个负责人"))
		owner = owner_rows[0].user
		if not _holds_operations(owner):
			frappe.throw(_("负责人 {0} 不持有 GEO Operations 角色").format(owner))

	def _default_planned_end_date(self):
		"""默认计划结束日为最晚合同结束日（02 §1.3）。"""
		if self.planned_end_date or not self.contracts:
			return
		valid_to_dates = [getdate(c.valid_to) for c in self.contracts if c.valid_to]
		if valid_to_dates:
			self.planned_end_date = max(valid_to_dates)

	def _auto_add_creator_as_sales(self):
		"""新建服务时，创建人自动成为 Sales 成员（04 line 185）。"""
		user = frappe.session.user
		if user in ("Administrator", "Guest"):
			return
		roles = frappe.get_roles(user)
		if SALES not in roles:
			return
		existing = [m for m in self.members if m.user == user]
		if existing:
			return
		self.append("members", {
			"user": user,
			"member_role": "Sales",
			"from_date": getdate(),
		})


TRANSITION_FIELDS = {"status", "is_paused", "actual_end_date", "reopen_reason"}


def _transition(service, from_status, updates):
	"""条件更新：WHERE name=%s AND status=%s，0 行表示已被他人抢先（02 §0.2）。"""
	if "status" not in updates or not set(updates) <= TRANSITION_FIELDS:
		raise ValueError(updates)
	set_clause = ", ".join(f'"{k}" = %s' for k in updates)
	values = (*updates.values(), now_datetime(), frappe.session.user, service, from_status)
	rows = frappe.db.sql(
		f'UPDATE "tabGEO Service" SET {set_clause}, "modified" = %s, "modified_by" = %s '
		'WHERE "name" = %s AND "status" = %s RETURNING "name"',
		values,
	)
	if not rows:
		frappe.throw(_("服务状态已被他人改变，请刷新后重试"))


def _open_pause(service):
	return frappe.db.get_value(
		"GEO Service Pause", {"service": service, "docstatus": 1, "resumed_at": ("is", "not set")}, "name"
	)


def _set_paused(service, from_value, to_value):
	"""is_paused 的条件更新：只在进行中且当前值符合预期时改（02 §0.2）。"""
	rows = frappe.db.sql(
		'UPDATE "tabGEO Service" SET "is_paused" = %s, "modified" = %s, "modified_by" = %s '
		'WHERE "name" = %s AND "status" = %s AND "is_paused" = %s RETURNING "name"',
		(to_value, now_datetime(), frappe.session.user, service, "Active", from_value),
	)
	if not rows:
		frappe.throw(_("服务状态已被他人改变，请刷新后重试"))


def activation_gaps(doc, today=None):
	"""启动前缺什么：返回缺项列表，空列表表示可以启动（02 §1.3）。"""
	today = today or getdate()
	missing = []
	if not doc.start_date:
		missing.append(_("开始日期"))
	if not doc.served_customer:
		missing.append(_("被服务组织"))
	if not doc.targets:
		missing.append(_("优化标的"))
	if not doc.contracts:
		missing.append(_("关联合同"))

	submitted = []
	for row in doc.contracts:
		if frappe.db.get_value("Contract", row.contract, "docstatus") == 1:
			submitted.append(row.contract)
		else:
			missing.append(_("合同 {0} 未提交").format(row.contract))

	owner_rows = [m for m in doc.members if m.member_role == "Owner" and _active_on(m, today)]
	if not owner_rows:
		missing.append(_("当前有效的负责人"))
	elif len(owner_rows) > 1:
		missing.append(_("当前有效的负责人超过一个"))
	elif not _holds_operations(owner_rows[0].user):
		missing.append(_("负责人 {0} 不持有 GEO Operations 角色").format(owner_rows[0].user))

	if submitted and doc.served_customer:
		covered = frappe.get_all(
			"GEO Contract Served Customer",
			filters={"parent": ("in", submitted), "parenttype": "Contract", "customer": doc.served_customer},
			pluck="name",
		)
		if not covered:
			missing.append(_("被服务组织不在任何已提交合同的覆盖范围内"))
	return missing


@frappe.whitelist()
def activate(service):
	"""启动服务：Draft → Active（02 §1.3、1.4）。"""
	assert_service_access(frappe.session.user, service, "owner")
	doc = frappe.get_doc("GEO Service", service)
	if doc.status != "Draft":
		frappe.throw(_("只能启动草稿服务"))
	missing = activation_gaps(doc)
	if missing:
		frappe.throw(_("启动服务前需要补全：{0}").format("、".join(missing)))
	_transition(service, "Draft", {"status": "Active"})
	return {"status": "Active"}


@frappe.whitelist()
def pause(service, paused_from, reason):
	"""记录暂停：新建并提交一条 GEO Service Pause（02 §1.3）。不改任何日期。"""
	assert_service_access(frappe.session.user, service, "owner")
	doc = frappe.get_doc("GEO Service", service)
	if doc.status != "Active":
		frappe.throw(_("只能暂停进行中的服务"))
	if doc.is_paused or _open_pause(service):
		frappe.throw(_("服务已处于暂停状态"))

	pause_doc = frappe.get_doc({
		"doctype": "GEO Service Pause",
		"service": service,
		"paused_from": paused_from,
		"reason": reason,
	})
	pause_doc.insert(ignore_permissions=True)
	pause_doc.submit()
	_set_paused(service, 0, 1)
	return {"pause": pause_doc.name}


@frappe.whitelist()
def resume(service):
	"""记录恢复：给未关闭的暂停写入 resumed_at（只写一次）。不改任何日期。"""
	assert_service_access(frappe.session.user, service, "owner")
	doc = frappe.get_doc("GEO Service", service)
	if doc.status != "Active":
		frappe.throw(_("只能恢复进行中的服务"))
	open_pause = _open_pause(service)
	if not doc.is_paused or not open_pause:
		frappe.throw(_("服务未暂停"))

	now = now_datetime()
	_close_pause(open_pause, now)
	_set_paused(service, 1, 0)
	return {"pause": open_pause, "resumed_at": str(now)}


def _close_pause(pause_name, resumed_at, note_suffix=None):
	"""条件写 resumed_at：已有值时视为并发冲突。"""
	values = [resumed_at, frappe.session.user]
	note_sql = ""
	if note_suffix:
		note_sql = ', "note" = CASE WHEN COALESCE("note", \'\') = \'\' THEN %s ELSE "note" || E\'\\n\' || %s END'
		values += [note_suffix, note_suffix]
	values += [now_datetime(), frappe.session.user, pause_name]
	rows = frappe.db.sql(
		f'UPDATE "tabGEO Service Pause" SET "resumed_at" = %s, "resume_recorded_by" = %s{note_sql}, '
		'"modified" = %s, "modified_by" = %s '
		'WHERE "name" = %s AND "docstatus" = 1 AND "resumed_at" IS NULL RETURNING "name"',
		tuple(values),
	)
	if not rows:
		frappe.throw(_("暂停记录已被他人关闭，请刷新后重试"))


@frappe.whitelist()
def extend(service, new_planned_end_date, reason=None):
	"""延期：只能推后计划结束日（02 §1.3）。"""
	assert_service_access(frappe.session.user, service, "owner")
	doc = frappe.get_doc("GEO Service", service)
	if doc.status != "Active":
		frappe.throw(_("只能延期进行中的服务"))
	if not new_planned_end_date:
		frappe.throw(_("新计划结束日必填"))

	new_date = getdate(new_planned_end_date)
	old_date = getdate(doc.planned_end_date) if doc.planned_end_date else None
	if old_date and new_date <= old_date:
		frappe.throw(_("新计划结束日必须晚于当前计划结束日 {0}").format(old_date))

	rows = frappe.db.sql(
		'UPDATE "tabGEO Service" SET "planned_end_date" = %s, "modified" = %s, "modified_by" = %s '
		'WHERE "name" = %s AND "status" = %s AND "planned_end_date" IS NOT DISTINCT FROM %s RETURNING "name"',
		(new_date, now_datetime(), frappe.session.user, service, "Active", old_date),
	)
	if not rows:
		frappe.throw(_("服务状态已被他人改变，请刷新后重试"))
	doc.add_comment("Comment", _("计划结束日 {0} → {1}{2}").format(
		old_date or _("（未设）"), new_date, f"：{reason}" if reason else ""))
	return {"planned_end_date": str(new_date)}


@frappe.whitelist()
def end_service(service, actual_end_date):
	"""结束服务：Active → Ended，同一事务内连带处理下属对象（02 §1.4）。"""
	assert_service_access(frappe.session.user, service, "owner")
	doc = frappe.get_doc("GEO Service", service)
	if doc.status != "Active":
		frappe.throw(_("只能结束进行中的服务"))
	if not actual_end_date:
		frappe.throw(_("实际结束日必填"))

	end_date = getdate(actual_end_date)
	if doc.start_date and end_date < getdate(doc.start_date):
		frappe.throw(_("实际结束日不能早于开始日 {0}").format(doc.start_date))

	# 1. 已提交、未切换的换词：撤销（撤销时连带删除其 Draft 新问句）
	for name in frappe.get_all("GEO Question Replacement",
			filters={"service": service, "docstatus": 1, "applied_at": ("is", "not set")}, pluck="name"):
		rep = frappe.get_doc("GEO Question Replacement", name)
		rep.flags.ignore_permissions = True
		rep.cancel()

	# 2. 草稿换词：连同其 Draft 新问句一起删除
	for name in frappe.get_all("GEO Question Replacement", filters={"service": service, "docstatus": 0}, pluck="name"):
		new_sq = frappe.db.get_value("GEO Question Replacement", name, "new_service_question")
		frappe.delete_doc("GEO Question Replacement", name, ignore_permissions=True, force=True)
		# 换词 on_trash 已删草稿新端；仍存在时再删
		if new_sq and frappe.db.exists("GEO Service Question", new_sq):
			frappe.delete_doc("GEO Service Question", new_sq, ignore_permissions=True, force=True)

	# 3. 执行中的服务问句停止，最后监测日 = 实际结束日
	for name in frappe.get_all("GEO Service Question", filters={"service": service, "status": "Active"}, pluck="name"):
		frappe.db.set_value("GEO Service Question", name, {
			"status": "Stopped",
			"stop_reason": "Service Ended",
			"effective_to": end_date,
		})

	# 4. 草稿服务问句删除
	for name in frappe.get_all("GEO Service Question", filters={"service": service, "status": "Draft"}, pluck="name"):
		frappe.delete_doc("GEO Service Question", name, ignore_permissions=True, force=True)

	# 5. 未关闭的暂停随服务结束关闭
	open_pause = _open_pause(service)
	if open_pause:
		_close_pause(open_pause, get_datetime(f"{end_date} 23:59:59"), note_suffix="随服务结束关闭")

	# 6. 服务本身
	_transition(service, "Active", {"status": "Ended", "actual_end_date": end_date, "is_paused": 0})
	return {"status": "Ended", "actual_end_date": str(end_date)}


@frappe.whitelist()
def undo_end(service, reopen_reason):
	"""撤销结束：Ended → Active，仅管理员（ST-02）。已停止的服务问句不恢复。"""
	if not is_admin(frappe.session.user):
		frappe.throw(_("只有管理员可以撤销服务结束"), frappe.PermissionError)
	if not (reopen_reason or "").strip():
		frappe.throw(_("撤销原因必填"))
	assert_service_access(frappe.session.user, service, "read")
	_transition(service, "Ended", {"status": "Active", "actual_end_date": None, "reopen_reason": reopen_reason.strip()})
	return {"status": "Active"}
