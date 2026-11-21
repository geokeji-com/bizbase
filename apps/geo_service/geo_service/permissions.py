"""服务访问范围（设计 04 §4.2–4.4、§5.3–5.4）。

范围只来自当天有效的服务成员行，不看组织层级、客户负责人和单据所有人。
GEO Admin 与 Administrator 不受范围限制。权限钩子只能拒绝，不能授予 DocPerm 之外的权限。
"""

import frappe
from frappe.utils import getdate

ADMIN = "GEO Admin"
OPERATIONS = "GEO Operations"
SALES = "GEO Sales"
COLLECTOR = "GEO Collector"
REPORT_AGENT = "GEO Report Agent"
PERSON_ROLES = (ADMIN, OPERATIONS, SALES)
MACHINE_ROLES = (COLLECTOR, REPORT_AGENT)

# 持有这些角色的用户维持 ERPNext 原生的客户、合同可见范围（04 §5.4 第 3 条）。
ERP_MANAGER_ROLES = {
	"System Manager", "Sales Manager", "Sales Master Manager", "Purchase Manager",
	"Accounts Manager", "Stock Manager", "HR Manager",
}

# 只读分工：即使用户持有 GEO Operations，也不能在该服务内写入或提交（04 §5.4 第 4 条）。
READ_ONLY_MEMBER_ROLES = {"Sales", "Other", "Report Agent"}
WRITE_PTYPES = {"write", "create", "submit", "cancel", "amend", "delete"}

DENIED = "无权访问该记录，或记录不存在"


def _today(on_date=None):
	return getdate(on_date) if on_date else getdate()


def is_admin(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or (
		user != "Guest" and _enabled_system_user(user) and ADMIN in frappe.get_roles(user)
	)


def _enabled_system_user(user):
	return bool(frappe.db.exists("User", {"name": user, "enabled": 1, "user_type": "System User"}))


def has_person_role(user=None):
	user = user or frappe.session.user
	return user != "Guest" and bool(set(PERSON_ROLES) & set(frappe.get_roles(user)))


def _member_rows(user, service=None, on_date=None):
	if not user or user == "Guest":
		return []
	day = _today(on_date)
	filters = {"parenttype": "GEO Service", "parentfield": "members", "user": user, "from_date": ("<=", day)}
	if service:
		filters["parent"] = service
	rows = frappe.get_all(
		"GEO Service Member", filters=filters, fields=["parent", "member_role", "to_date"],
		ignore_permissions=True,
	)
	return [row for row in rows if not row.to_date or getdate(row.to_date) >= day]


def services_of(user=None, on_date=None):
	"""用户当天有有效成员行的服务集合 S(u)。管理员同样只返回自己的成员行，用于「我的服务」。"""
	return {row.parent for row in _member_rows(user or frappe.session.user, on_date=on_date)}


def is_service_owner(user, service, on_date=None):
	return any(row.member_role == "Owner" for row in _member_rows(user, service, on_date))


def _can_write_in(user, service, on_date=None):
	return any(row.member_role not in READ_ONLY_MEMBER_ROLES for row in _member_rows(user, service, on_date))


def can_access(user, service, action="read", on_date=None):
	user = user or frappe.session.user
	if not service or not isinstance(service, str):
		return False
	if is_admin(user):
		return bool(frappe.db.exists("GEO Service", service))
	if action == "owner":
		return is_service_owner(user, service, on_date)
	if action == "write":
		return _can_write_in(user, service, on_date)
	return bool(_member_rows(user, service, on_date))


def assert_service_access(user, service, action="read"):
	"""action 取 read、write、owner。无权与不存在返回同一个 403 文本。"""
	if action not in ("read", "write", "owner"):
		raise ValueError(action)
	if not can_access(user or frappe.session.user, service, action):
		frappe.throw(DENIED, frappe.PermissionError)
	return service


# ---------------------------------------------------------------- 行级范围 SQL
# 列表钩子与单条检查共用同一组子查询，保证列表能看到的记录与打开详情的结果一致。
# 日期用站点时区的今天，不用数据库的 CURRENT_DATE，避免数据库时区与站点时区不同。


def _esc(value):
	return frappe.db.escape(str(value))


def _services_sql(user, on_date=None):
	return (
		"select m.parent from `tabGEO Service Member` m"
		" where m.parenttype = 'GEO Service' and m.parentfield = 'members'"
		f" and m.user = {_esc(user)} and m.from_date <= {_esc(_today(on_date))}"
		f" and (m.to_date is null or m.to_date >= {_esc(_today(on_date))})"
	)


def _contracts_sql(user):
	"""可见合同：被 S(u) 中服务引用（含有效期已结束的行，便于追溯修订链），或本人起草且未被任何服务引用。"""
	return (
		"select sc.contract as name from `tabGEO Service Contract` sc"
		f" where sc.parenttype = 'GEO Service' and sc.parent in ({_services_sql(user)})"
		" union select c.name from `tabContract` c"
		f" where c.owner = {_esc(user)} and not exists ("
		"select 1 from `tabGEO Service Contract` x where x.parenttype = 'GEO Service' and x.contract = c.name)"
	)


def _customers_sql(user):
	contracts = _contracts_sql(user)
	u = _esc(user)
	return (
		"select s.served_customer as name from `tabGEO Service` s"
		f" where s.name in ({_services_sql(user)})"
		" union select c.party_name from `tabContract` c"
		f" where c.party_type = 'Customer' and c.name in ({contracts})"
		" union select c.geo_payer_customer from `tabContract` c"
		f" where c.geo_payer_customer is not null and c.name in ({contracts})"
		" union select sc.customer from `tabGEO Contract Served Customer` sc"
		f" where sc.parenttype = 'Contract' and sc.parent in ({contracts})"
		" union select cu.name from `tabCustomer` cu"
		f" where cu.owner = {u}"
		" and not exists (select 1 from `tabGEO Service` s where s.served_customer = cu.name)"
		" and not exists (select 1 from `tabContract` c where c.party_type = 'Customer' and c.party_name = cu.name)"
		" and not exists (select 1 from `tabContract` c where c.geo_payer_customer = cu.name)"
		" and not exists (select 1 from `tabGEO Contract Served Customer` x"
		" where x.parenttype = 'Contract' and x.customer = cu.name)"
	)


def _contacts_sql(user):
	"""通过 Dynamic Link 关联到可见客户；本人新建且尚未关联任何对象的联系人留给本人。"""
	return (
		"select dl.parent as name from `tabDynamic Link` dl"
		" where dl.parenttype = 'Contact' and dl.link_doctype = 'Customer'"
		f" and dl.link_name in ({_customers_sql(user)})"
		" union select ct.name from `tabContact` ct"
		f" where ct.owner = {_esc(user)} and not exists ("
		"select 1 from `tabDynamic Link` x where x.parenttype = 'Contact' and x.parent = ct.name)"
	)


def _profile_customers_sql(user):
	return f"select s.served_customer from `tabGEO Service` s where s.name in ({_services_sql(user)})"


def _contains(sql, name):
	if not name:
		return False
	return bool(frappe.db.sql(f"select 1 from ({sql}) v where v.name = %s limit 1", (name,)))


def _names(sql):
	return {row[0] for row in frappe.db.sql(sql) if row[0]}


def _narrows_crm(user):
	"""只收窄持有 GEO 人员角色、且没有 GEO Admin 与 ERPNext 管理角色的用户（04 §5.4 第 3 条）。"""
	if not user or user == "Administrator":
		return False
	roles = set(frappe.get_roles(user))
	return bool(roles & set(PERSON_ROLES)) and ADMIN not in roles and not roles & ERP_MANAGER_ROLES


def customers_visible_to(user=None):
	user = user or frappe.session.user
	if not _narrows_crm(user):
		return set(frappe.get_all("Customer", pluck="name", ignore_permissions=True))
	return _names(_customers_sql(user))


def contracts_visible_to(user=None):
	user = user or frappe.session.user
	if not _narrows_crm(user):
		return set(frappe.get_all("Contract", pluck="name", ignore_permissions=True))
	return _names(_contracts_sql(user))


# ---------------------------------------------------------------- 列表钩子（permission_query_conditions）
# 返回 "" 表示不过滤，只在用户不受范围限制时返回。子表不注册，框架会套用父表条件。


def _pqc_user(user):
	return user or frappe.session.user


def service_pqc(user=None, doctype=None):
	user = _pqc_user(user)
	if is_admin(user):
		return ""
	return f"`tabGEO Service`.`name` in ({_services_sql(user)})"


def service_scoped_pqc(user=None, doctype=None):
	user = _pqc_user(user)
	if is_admin(user):
		return ""
	if not doctype:
		return "1 = 0"
	return f"`tab{doctype}`.`service` in ({_services_sql(user)})"


def customer_pqc(user=None, doctype=None):
	user = _pqc_user(user)
	if not _narrows_crm(user):
		return ""
	return f"`tabCustomer`.`name` in ({_customers_sql(user)})"


def contract_pqc(user=None, doctype=None):
	user = _pqc_user(user)
	if not _narrows_crm(user):
		return ""
	return f"`tabContract`.`name` in ({_contracts_sql(user)})"


def contact_pqc(user=None, doctype=None):
	user = _pqc_user(user)
	if not _narrows_crm(user):
		return ""
	return f"`tabContact`.`name` in ({_contacts_sql(user)})"


RELATION_ENDS = {
	"GEO Group Relation": ("parent_customer", "child_customer"),
	"GEO Channel Relation": ("channel_customer", "end_customer"),
}


def relation_pqc(user=None, doctype=None):
	user = _pqc_user(user)
	if is_admin(user):
		return ""
	if doctype not in RELATION_ENDS:
		return "1 = 0"
	customers = _customers_sql(user)
	a, b = RELATION_ENDS[doctype]
	return f"`tab{doctype}`.`{a}` in ({customers}) and `tab{doctype}`.`{b}` in ({customers})"


def profile_pqc(user=None, doctype=None):
	user = _pqc_user(user)
	if is_admin(user):
		return ""
	return f"`tabGEO Customer Profile Version`.`customer` in ({_profile_customers_sql(user)})"


# ---------------------------------------------------------------- 单条钩子（has_permission）
# 只能收窄 DocPerm。先判断行级范围，再判断服务内分工；Owner 专属动作见 OWNER_PTYPES。


def _get(doc, field):
	return doc.get(field) if hasattr(doc, "get") else getattr(doc, field, None)


def _is_new(doc):
	if hasattr(doc, "is_new"):
		return doc.is_new()
	return not _get(doc, "name") or not _get(doc, "creation")


def _stored(doc, field):
	"""已保存记录取库里的值，防止改 service 字段把记录挪进自己的服务。"""
	if _is_new(doc):
		return None
	return frappe.db.get_value(_get(doc, "doctype"), _get(doc, "name"), field)


# 这些动作在对应 DocType 上只允许当天有效的 Owner（04 §4.3）；其余写入动作要求可写分工。
OWNER_PTYPES = {
	"GEO Service Pause": {"create", "write", "submit", "cancel"},
	"GEO Question Replacement": {"submit", "cancel"},
}


def _service_action(doctype, ptype):
	if ptype in OWNER_PTYPES.get(doctype, ()):
		return "owner"
	if ptype in WRITE_PTYPES:
		return "write"
	return "read"


def service_has_permission(doc, ptype=None, user=None):
	user = _pqc_user(user)
	if is_admin(user):
		return True
	if _is_new(doc):
		# 建草稿只给销售（DocPerm 层控制）；保存时控制器把建草稿的销售加为 Sales 成员。
		return ptype in ("create", "read", "write", None) and has_person_role(user)
	action = "write" if ptype in WRITE_PTYPES else "read"
	return can_access(user, _get(doc, "name"), action)


def service_scoped_has_permission(doc, ptype=None, user=None):
	user = _pqc_user(user)
	if is_admin(user):
		return True
	doctype = _get(doc, "doctype")
	action = _service_action(doctype, ptype or "read")
	if _is_new(doc) and action == "write":
		action = _service_action(doctype, "create")
	services = {_get(doc, "service"), _stored(doc, "service")} - {None, ""}
	if not services:
		# 新记录尚未选服务时允许打开表单；保存时控制器要求 service 并再次校验。
		return _is_new(doc)
	return all(can_access(user, service, action) for service in services)


def customer_has_permission(doc, ptype=None, user=None):
	user = _pqc_user(user)
	if not _narrows_crm(user) or _is_new(doc):
		return True
	return _contains(_customers_sql(user), _get(doc, "name"))


def contract_has_permission(doc, ptype=None, user=None):
	user = _pqc_user(user)
	if not _narrows_crm(user) or _is_new(doc):
		return True
	return _contains(_contracts_sql(user), _get(doc, "name"))


def contact_has_permission(doc, ptype=None, user=None):
	user = _pqc_user(user)
	if not _narrows_crm(user) or _is_new(doc):
		return True
	return _contains(_contacts_sql(user), _get(doc, "name"))


def relation_has_permission(doc, ptype=None, user=None):
	user = _pqc_user(user)
	if is_admin(user):
		return True
	ends = RELATION_ENDS.get(_get(doc, "doctype"))
	if not ends:
		return False
	customers = customers_visible_to(user)
	values = [_get(doc, field) for field in ends]
	if not _is_new(doc):
		values += [_stored(doc, field) for field in ends]
	values = [value for value in values if value]
	return all(value in customers for value in values)


def profile_has_permission(doc, ptype=None, user=None):
	user = _pqc_user(user)
	if is_admin(user):
		return True
	customers = {_get(doc, "customer"), _stored(doc, "customer")} - {None, ""}
	if not customers:
		return _is_new(doc)
	allowed = _names(_profile_customers_sql(user))
	return customers <= allowed
