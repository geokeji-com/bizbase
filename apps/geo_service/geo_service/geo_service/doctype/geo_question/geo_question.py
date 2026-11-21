"""GEO Question：全局唯一、不可变问句（01 §4.7）。只经 get_or_create_question 创建。"""

import hashlib
import unicodedata

import frappe
from frappe import _
from frappe.model.document import Document


class GEOQuestion(Document):
	def validate(self):
		# 不可变：除首次插入外一律拒绝（D-026）
		if not self.is_new():
			frappe.throw(_("问句一经创建不可修改，包括管理员也不能修改。"))

	def on_trash(self):
		# 被引用时拒绝删除
		refs = frappe.db.count("GEO Service Question", {"question": self.name})
		if refs:
			frappe.throw(_("该问句已被 {0} 个服务问句引用，无法删除").format(refs))
		# 检查采集任务引用（如果 task_execution 已安装）
		if frappe.db.exists("DocType", "GEO Collection Task"):
			task_refs = frappe.db.count("GEO Collection Task", {"question": self.name})
			if task_refs:
				frappe.throw(_("该问句已被 {0} 个采集任务引用，无法删除").format(task_refs))


@frappe.whitelist()
def get_or_create_question(text):
	"""幂等创建：返回 GEO Question name。normalization_version=1 只做 strip，不做 NFC/NFKC/大小写/标点归一。"""
	if not isinstance(text, str):
		frappe.throw(_("问句文本必须是字符串"))

	normalized = text.strip()
	if not normalized:
		frappe.throw(_("问句文本不能为空"))

	text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

	# 尝试查找已有
	existing = frappe.db.get_value("GEO Question", {"text_hash": text_hash}, "name")
	if existing:
		return existing

	# 计算 loose_key（管理员查近似重复用）
	loose = unicodedata.normalize("NFKC", normalized).casefold()
	loose = "".join(c for c in loose if c.isalnum())
	loose_key = hashlib.sha256(loose.encode("utf-8")).hexdigest()

	# 插入；唯一索引冲突时回滚到保存点再读已有行。
	# PostgreSQL 在语句报错后整个事务失效，不回滚到保存点就无法继续查询。
	frappe.db.savepoint("geo_question_insert")
	try:
		doc = frappe.get_doc({
			"doctype": "GEO Question",
			"question_text": normalized,
			"text_hash": text_hash,
			"normalization_version": 1,
			"loose_key": loose_key,
		})
		doc.insert(ignore_permissions=True)
	except frappe.exceptions.DuplicateEntryError:
		frappe.db.rollback(save_point="geo_question_insert")
		existing = frappe.db.get_value("GEO Question", {"text_hash": text_hash}, "name")
		if existing:
			return existing
		raise
	frappe.db.release_savepoint("geo_question_insert")
	return doc.name
