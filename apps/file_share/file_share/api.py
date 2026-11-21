"""Employee file-share RPCs. Publish by pinning one domain, never by moving the report default."""

import hashlib
import hmac
import json
import re
from pathlib import PurePath
from uuid import UUID

import frappe
from frappe.utils.file_manager import get_max_file_size
from frappe.utils.password import get_encryption_key

from file_share import core, publication
from file_share.cli_auth import share_rpc

REPORT = "File Share"
OPERATION = "File Share Operation"


def _integer(value, field, low, high):
	if not re.fullmatch(r"[0-9]{1,10}", str(value)) or not low <= int(value) <= high:
		frappe.throw(f"{field} 必须是 {low} 到 {high} 之间的整数")
	return int(value)


def _owned(share_id, *, write=False):
	# Filter by owner even for an employee who is also a System Manager. Do not disclose
	# whether an unowned ID exists. No user-supplied filters or DocType names are accepted.
	if not isinstance(share_id, str) or not re.fullmatch(r"[A-Za-z0-9]{10}", share_id):
		frappe.throw("无效的分享 ID")
	if not frappe.db.exists(REPORT, {"name": share_id, "owner": frappe.session.user}):
		frappe.throw("无法访问这份报告", frappe.PermissionError)
	doc = frappe.get_doc(REPORT, share_id, for_update=write)
	if doc.owner != frappe.session.user:
		frappe.throw("无法访问这份报告", frappe.PermissionError)
	doc.check_permission("write" if write else "read")
	return doc


def _summary(doc):
	return dict(share_id=doc.name, title=doc.title, status=doc.status, current_version=doc.current_version or 0)


def _entry(doc, row):
	config = frappe.db.get_value(publication.DOMAIN, row.domain, ["status", "origin"], as_dict=True)
	version = row.pinned_version if row.version_mode == "Pinned" else doc.current_version
	live = bool(doc.status == "Active" and row.enabled and config and config.status == "Enabled" and version)
	return dict(domain=row.domain, version=version or 0, enabled=live,
		access_mode=doc.access_level if row.access_mode == "Inherit" else row.access_mode,
		url=f"{config.origin}/file-share/s/{doc.name}" if live else None)


@share_rpc
def whoami():
	return {"user": frappe.session.user}


@share_rpc
def domains():
	return publication.available_domains()


@share_rpc
def list_reports(start=0, limit=20):
	rows = frappe.get_list(REPORT, filters={"owner": frappe.session.user},
		fields=["name", "title", "current_version", "status"], order_by="modified desc, name asc",
		start=_integer(start, "start", 0, 2147483647), page_length=_integer(limit, "limit", 1, 100))
	return [_summary(row) for row in rows]


@share_rpc
def get_report(share_id):
	doc = _owned(share_id)
	return {**_summary(doc), "versions": [r.version for r in doc.versions], "entries": [_entry(doc, r) for r in doc.entries]}


def _write(request_id, operation, params, apply):
	try:
		request_id = str(UUID(str(request_id)))
	except ValueError:
		frappe.throw("request_id 必须是 UUID")
	actor = frappe.session.user
	key = hashlib.sha256(f"{actor}\0{request_id}".encode()).hexdigest()
	# A keyed digest binds retries to the original input without storing content, ACLs or passwords.
	fingerprint = hmac.new(get_encryption_key().encode(),
		json.dumps([operation, params], ensure_ascii=False, sort_keys=True).encode(), hashlib.sha256).hexdigest()
	previous = frappe.db.get_value(OPERATION, key, ["fingerprint", "result_json", "share_id"], as_dict=True)
	if previous:
		if not hmac.compare_digest(previous.fingerprint, fingerprint):
			frappe.throw("同一 request_id 已用于不同的请求")
		_owned(previous.share_id)
		return json.loads(previous.result_json)

	# Reserve the unique primary key before touching files or running a report mutation. Frappe
	# commits this row and the business write together (or rolls both back on an exception).
	log = frappe.get_doc({"doctype": OPERATION, "request_id": request_id, "actor": actor,
		"operation": operation, "fingerprint": fingerprint})
	try:
		log.insert(set_name=key, ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# A racing transaction may have a prior repeatable-read snapshot. Let the caller replay
		# in a fresh HTTP request; never run the mutation twice.
		frappe.throw("该请求正在并发处理，请用同一 request_id 重试")
	result = {"request_id": request_id, **apply()}
	frappe.db.set_value(OPERATION, key, {"share_id": result["share_id"], "version": result["version"],
		"access_domain": result["domain"], "access_mode": result["access_mode"],
		"result_json": json.dumps(result, ensure_ascii=False)})
	return result


@share_rpc
def upload(request_id, title=None, share_id=None):
	if share_id is None:
		if not isinstance(title, str) or not title.strip() or len(title.strip()) > 140:
			frappe.throw("新建报告需要 1 到 140 字的标题")
		title = title.strip()
	elif title is not None:
		frappe.throw("更新版本只需提供 share_id")
	files = frappe.request.files.getlist("file")
	if len(files) != 1:
		frappe.throw("请上传一个 HTML 或 ZIP 文件")
	file = files[0]
	filename = PurePath((file.filename or "").replace("\\", "/")).name
	if not filename.lower().endswith((*core.HTML_SUFFIXES, ".zip")):
		frappe.throw("仅支持 .html、.htm 或 .zip 文件")
	max_size = min(core.MAX_TOTAL_BYTES, get_max_file_size())
	content = file.stream.read(max_size + 1)
	if not content or len(content) > max_size:
		frappe.throw("文件为空或超过站点上传限制")

	def apply():
		doc = _owned(share_id, write=True) if share_id is not None else frappe.new_doc(REPORT)
		if doc.is_new():
			doc.check_permission("create")
			doc.title = title
			doc.access_level = "Internal"
		source = frappe.get_doc({"doctype": "File", "file_name": filename, "content": content, "is_private": 1}).insert()
		# Frappe deduplicates identical uploads. Report.validate ingests only on URL change.
		# Keep an unchanged file as the same version; do not claim a new immutable version.
		doc.upload = source.file_url
		doc.publish_upload = 0
		doc.save()
		return dict(share_id=doc.name, version=doc.versions[-1].version, domain=None, access_mode=None, url=None)

	return _write(request_id, "upload", [share_id, title, filename, hashlib.sha256(content).hexdigest()], apply)


def _names(value):
	if value is None:
		return []
	if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() or
		len(item) > 140 or len(item.splitlines()) != 1 for item in value):
		frappe.throw("用户和角色必须是名称列表")
	return sorted({item.strip() for item in value})


def _domain(value):
	try:
		return publication.normalize_authority(value)
	except ValueError as error:
		frappe.throw(str(error))


@share_rpc
def publish(request_id, share_id, domain, version, access_mode, password=None, users=None, roles=None):
	domain = _domain(domain)
	version = _integer(version, "version", 1, 2147483647)
	if not isinstance(access_mode, str) or access_mode not in publication.MODES | {"Keep"}:
		frappe.throw("请选择 Internal、Specified、Password、Public 或 Keep 权限")
	if access_mode == "Keep" and any(value is not None for value in (users, roles, password)):
		frappe.throw("保留权限时不要传入口令、用户或角色")
	users, roles = _names(users), _names(roles)
	if access_mode != "Specified" and (users or roles):
		frappe.throw("仅指定人员或角色模式可设置用户和角色")
	if password is not None and (access_mode != "Password" or not isinstance(password, str) or not password.strip("*")):
		frappe.throw("请仅为密码模式提供有效口令")

	def apply():
		doc = _owned(share_id, write=True)
		if doc.status != "Active" or not frappe.db.exists(publication.DOMAIN, {"name": domain, "status": "Enabled"}):
			frappe.throw("只能发布启用的报告到已接入的域名")
		row = next((r for r in doc.entries if r.domain == domain), None)
		if access_mode == "Keep":
			if row is None or not row.enabled:
				frappe.throw("只有已开启的域名入口才能保留其现有权限")
		else:
			if row is None:
				row = doc.append("entries", {"domain": domain})
			if access_mode != "Password":
				row.password = None
			elif password is not None:
				row.password = password
			elif row.access_mode != "Password":
				frappe.throw("请为此入口设置密码")
			row.update({"enabled": 1, "access_mode": access_mode, "user_list": "\n".join(users), "role_list": "\n".join(roles)})
		row.update({"version_mode": "Pinned", "pinned_version": version})
		doc.save()
		entry = _entry(doc, row)
		return dict(share_id=doc.name, version=version, domain=domain, access_mode=entry["access_mode"], url=entry["url"])

	return _write(request_id, "publish", [share_id, domain, version, access_mode, password, users, roles], apply)


@share_rpc
def close(request_id, share_id, domain):
	domain = _domain(domain)

	def apply():
		doc = _owned(share_id, write=True)
		row = next((r for r in doc.entries if r.domain == domain), None)
		if row is None:
			frappe.throw("这份报告没有此域名入口")
		row.enabled = 0
		doc.save()
		entry = _entry(doc, row)
		return dict(share_id=doc.name, version=entry["version"], domain=domain, access_mode=entry["access_mode"], url=None)

	return _write(request_id, "close", [share_id, domain], apply)
