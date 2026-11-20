"""The publishing boundary: resolve a real HTTP authority to one report policy."""

import hashlib
import ipaddress
import re
import secrets
from urllib.parse import urlsplit

import frappe
from frappe.utils import cint

from file_share.permissions import is_employee, is_manager

DOMAIN = "File Share Domain"
ENTRY = "File Share Entry"
MODES = {"Internal", "Specified", "Password", "Public"}


def epoch():
	return secrets.token_hex(16)


def normalize_authority(value):
	"""Exact DNS name (ASCII/IDNA on the wire), plus an optional explicit port."""
	if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9.-]+(?::[1-9][0-9]{0,4})?", value):
		raise ValueError("域名必须是完整主机名，不能含路径、通配符或用户信息")
	host, sep, port = value.lower().partition(":")
	if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in host.split(".")):
		raise ValueError("无效的域名")
	if sep and int(port) > 65535:
		raise ValueError("无效的端口")
	return host + (sep + port if sep else "")


def parse_origin(value):
	parts = urlsplit(value or "")
	authority = normalize_authority(parts.netloc)
	host = authority.partition(":")[0]
	if parts.path not in ("", "/") or parts.query or parts.fragment or parts.scheme not in ("https", "http"):
		raise ValueError("请填写 https://域名，不含路径、参数或片段")
	try:
		loopback = ipaddress.ip_address(host).is_loopback
	except ValueError:
		loopback = False
	if parts.scheme == "http" and not (loopback or host == "localhost" or host.endswith((".localhost", ".test"))):
		raise ValueError("非本地测试域名必须使用 HTTPS")
	# Browsers omit default ports in Host and URL.origin.
	if parts.port == {"https": 443, "http": 80}[parts.scheme]:
		authority = host
	return authority, parts.scheme + "://" + authority


def names(value):
	return sorted({s.strip() for s in (value or "").splitlines() if s.strip()})


def derived(*values):
	return hashlib.sha256("\0".join(str(v) for v in values).encode()).hexdigest()


def resolve_entry(share, authority, *, allow_unpublished=False):
	try:
		domain = normalize_authority(authority)
	except ValueError:
		return None
	if share.status != "Active":
		return None
	row = next((r for r in share.entries if r.domain == domain and cint(r.enabled)), None)
	if not row:
		return None
	config = frappe.db.get_value(DOMAIN, domain, ["status", "domain_epoch"], as_dict=True)
	if not config or config.status != "Enabled":
		return None
	inherit = row.access_mode == "Inherit"
	level = share.access_level if inherit else row.access_mode
	version = cint(row.pinned_version if row.version_mode == "Pinned" else share.current_version)
	draft_preview = allow_unpublished and version == 0 and bool(share.versions)
	if level not in MODES or not draft_preview and not any(v.version == version for v in share.versions):
		return None
	password_salt = derived(domain, config.domain_epoch, row.rule_epoch, share.access_salt if inherit else "")
	return frappe._dict(domain=domain, access_level=level, current_version=version,
		access_salt=derived(password_salt, row.version_epoch, version), password_salt=password_salt,
		password_doc=share if inherit else row,
		allowed_users=share.allowed_users if inherit else [frappe._dict(user=v) for v in names(row.user_list)],
		allowed_roles=share.allowed_roles if inherit else [frappe._dict(role=v) for v in names(row.role_list)],
		legacy_credentials=bool(row.legacy_domain_epoch and row.legacy_domain_epoch == config.domain_epoch
			and inherit and row.version_mode == "Follow"))


@frappe.whitelist()
def available_domains():
	if not (is_employee() or is_manager(frappe.session.user)):
		frappe.throw("只有授权的员工可以选择分享域名", frappe.PermissionError)
	# Deliberately do not expose the administrative list or Pending/Disabled rows.
	return frappe.get_all(DOMAIN, filters={"status": "Enabled"}, fields=["name", "display_name", "origin"],
		order_by="display_name asc, name asc")


def same_entry(row, old):
	if not old or row.get("password") and not row.is_dummy_password(row.password):
		return False
	return all(row.get(k) == old.get(k) for k in ("domain", "enabled", "access_mode", "user_list", "role_list", "version_mode", "pinned_version"))


def validate_entries(share, before, default_changed):
	old_rows = {r.name: r for r in before.entries} if before else {}
	seen = set()
	versions = {v.version for v in share.versions}
	live = 0
	for row in share.entries:
		old = old_rows.get(row.name)
		if not old:
			# Never let a submitted child ID overwrite another report's rule or password.
			row.name = epoch()[:16]
			row.set("__islocal", 1)
		try:
			row.domain = normalize_authority(row.domain)
		except ValueError as e:
			frappe.throw(str(e))
		if row.domain in seen or old and old.domain != row.domain:
			frappe.throw("每个域名只能配置一次；更换域名请添加新入口")
		seen.add(row.domain)
		state = frappe.db.get_value(DOMAIN, row.domain, "status")
		if not state or state != "Enabled" and (not old or not old.enabled and row.enabled):
			frappe.throw("只能新增或开启已接入的分享域名")
		if row.access_mode not in MODES | {"Inherit"} or row.version_mode not in {"Pinned", "Follow"}:
			frappe.throw("无效的入口权限或版本设置")
		if row.version_mode == "Pinned" and cint(row.pinned_version) not in versions:
			frappe.throw("固定版本必须是本报告中已有的版本")
		if row.access_mode == "Password":
			pwd = row.get("password") or ""
			if row.is_dummy_password(pwd):
				if not old or not old.get_password("password", raise_exception=False):
					frappe.throw("请输入入口独立密码")
			elif len(pwd) < 6:
				frappe.throw("入口密码至少 6 位")
		if row.access_mode == "Specified":
			users, roles = names(row.user_list), names(row.role_list)
			if not (users or roles):
				frappe.throw("请为入口指定用户或角色，每行填写一个")
			for doctype, items in (("User", users), ("Role", roles)):
				if any(not frappe.db.exists(doctype, item) for item in items):
					frappe.throw("入口指定的用户或角色不存在")
			row.user_list, row.role_list = "\n".join(users), "\n".join(roles)
		rule_changed = (not old or before.status != share.status or
			any(row.get(k) != old.get(k) for k in ("enabled", "access_mode", "user_list", "role_list")) or
			bool(row.get("password") and not row.is_dummy_password(row.password)))
		old_version = (old.pinned_version if old and old.version_mode == "Pinned" else before.current_version) if old else None
		version = row.pinned_version if row.version_mode == "Pinned" else share.current_version
		version_changed = not old or row.version_mode != old.version_mode or version != old_version
		row.rule_epoch = epoch() if rule_changed else old.rule_epoch
		row.version_epoch = epoch() if version_changed else old.version_epoch
		row.legacy_domain_epoch = None if rule_changed or version_changed or default_changed else old.legacy_domain_epoch
		if row.enabled and state == "Enabled" and version:
			live += 1
	if share.status == "Active" and share.current_version and not live and (
		not before or before.status != "Active" or before.current_version != share.current_version
	):
		frappe.throw("首次发布、重新发布或切换当前发布版时至少要开启一个可用域名")
