"""安装与迁移后的幂等配置：角色、合同字段、原生单据权限、实体分类和复合唯一索引。"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, update_permission_property

from geo_service.permissions import ADMIN, COLLECTOR, OPERATIONS, REPORT_AGENT, SALES

ROLES = {ADMIN: 1, OPERATIONS: 1, SALES: 1, COLLECTOR: 0, REPORT_AGENT: 0}

# 原生单据上的 GEO 角色权限（04 §4.2）。行级范围由 permissions.py 收窄。
NATIVE_PERMS = {
	"Customer": {OPERATIONS: "R", SALES: "RCW", ADMIN: "RCWEP"},
	"Contact": {OPERATIONS: "R", SALES: "RCW", ADMIN: "RCWEP"},
	"Contract": {OPERATIONS: "R", SALES: "RCWSXM", ADMIN: "RCWSXMEP"},
	"Holiday List": {OPERATIONS: "R", SALES: "R", ADMIN: "R"},
	"Customer Group": {OPERATIONS: "R", SALES: "R", ADMIN: "R"},
	"Territory": {OPERATIONS: "R", SALES: "R", ADMIN: "R"},
}
LETTERS = {"R": "read", "C": "create", "W": "write", "S": "submit", "X": "cancel", "M": "amend", "D": "delete", "E": "export", "P": "report"}

# S2 才重做的旧 DocType：在此之前只给管理员。
LEGACY = ("GEO Monitoring Plan", "GEO Prompt", "GEO Sampling Slot", "GEO Service Prompt")

CATEGORIES = [
	("shopping_platform", "购物平台"),
	("product_brand", "商品品牌"),
	("company", "公司"),
	("product", "产品"),
	("other", "其他"),
]

UNIQUE_INDEXES = {
	"GEO Customer Profile Version": ("uniq_profile_version", ("customer", "target_entity", "version_no")),
	"GEO Competitor List": ("uniq_competitor_version", ("service", "target_entity", "version_no")),
	"GEO Question Group": ("uniq_question_group", ("service", "group_name")),
}

CONTRACT_FIELDS = {
	"Contract": [
		{"fieldname": "geo_section", "fieldtype": "Section Break", "label": "GEO 服务条款", "insert_after": "contract_terms", "collapsible": 0},
		{"fieldname": "geo_payer_customer", "fieldtype": "Link", "options": "Customer", "label": "付款方", "insert_after": "geo_section",
			"description": "留空时等于签约方。"},
		{"fieldname": "geo_question_quota", "fieldtype": "Int", "label": "问句名额", "insert_after": "geo_payer_customer"},
		{"fieldname": "geo_min_samples_per_day", "fieldtype": "Int", "label": "每问句每日最少采样", "insert_after": "geo_question_quota"},
		{"fieldname": "geo_raw_records_required", "fieldtype": "Check", "label": "需交付原始记录", "insert_after": "geo_min_samples_per_day"},
		{"fieldname": "geo_cb_terms", "fieldtype": "Column Break", "insert_after": "geo_raw_records_required"},
		{"fieldname": "geo_report_frequency", "fieldtype": "Select", "options": "\nWeekly\nBiweekly\nMonthly\nOther",
			"label": "报告频次", "insert_after": "geo_cb_terms"},
		{"fieldname": "geo_sampling_note", "fieldtype": "Small Text", "label": "采样约定", "insert_after": "geo_report_frequency"},
		{"fieldname": "geo_served_customers", "fieldtype": "Table", "options": "GEO Contract Served Customer",
			"label": "被服务组织", "insert_after": "geo_sampling_note", "description": "合同覆盖的被服务组织，至少一个。"},
		{"fieldname": "geo_deliverable_terms", "fieldtype": "Table", "options": "GEO Contract Deliverable Term",
			"label": "交付条款", "insert_after": "geo_served_customers"},
		{"fieldname": "geo_penalty_section", "fieldtype": "Section Break", "label": "逾期违约", "insert_after": "geo_deliverable_terms", "collapsible": 1},
		{"fieldname": "geo_late_penalty_rate", "fieldtype": "Percent", "label": "日违约比例", "insert_after": "geo_penalty_section"},
		{"fieldname": "geo_late_penalty_cap", "fieldtype": "Percent", "label": "违约金上限", "insert_after": "geo_late_penalty_rate"},
		{"fieldname": "geo_late_penalty_base", "fieldtype": "Small Text", "label": "计算基数", "insert_after": "geo_late_penalty_cap"},
	]
}


def after_install():
	sync()


def after_migrate():
	sync()


def sync():
	for role, desk in ROLES.items():
		_role(role, desk)
	create_custom_fields(CONTRACT_FIELDS, update=True)
	for doctype, roles in NATIVE_PERMS.items():
		for role, letters in roles.items():
			_grant(doctype, role, letters)
	for doctype in LEGACY:
		_admin_only(doctype)
	for code, name in CATEGORIES:
		if not frappe.db.exists("GEO Entity Category", code):
			frappe.get_doc({"doctype": "GEO Entity Category", "category_code": code, "category_name": name}).insert(ignore_permissions=True)
	for doctype, (index, columns) in UNIQUE_INDEXES.items():
		_unique_index(doctype, index, columns)
	frappe.db.set_single_value("System Settings", "disable_document_sharing", 1)
	frappe.clear_cache()


def _role(name, desk_access):
	if frappe.db.exists("Role", name):
		frappe.db.set_value("Role", name, "desk_access", desk_access)
		return
	frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": desk_access}).insert(ignore_permissions=True)


def _grant(doctype, role, letters):
	if not frappe.db.exists("DocType", doctype):
		return
	add_permission(doctype, role, 0)
	wanted = {LETTERS[letter] for letter in letters}
	for ptype in LETTERS.values():
		update_permission_property(doctype, role, 0, ptype, 1 if ptype in wanted else 0, validate=False)


def _admin_only(doctype):
	if not frappe.db.exists("DocType", doctype):
		return
	for role in ("System Manager", OPERATIONS, SALES, COLLECTOR, REPORT_AGENT):
		frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": role})
	_grant(doctype, ADMIN, "RCWDEP")


def _unique_index(doctype, index, columns):
	table = f"tab{doctype}"
	exists = frappe.db.sql("select 1 from pg_indexes where tablename = %s and indexname = %s", (table, index))
	if exists:
		return
	cols = ", ".join(f'"{column}"' for column in columns)
	frappe.db.sql_ddl(f'create unique index "{index}" on "{table}" ({cols})')
