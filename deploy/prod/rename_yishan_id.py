"""一次性迁移：把已安装的 `yishan_id_login` 应用改名为 `yishan_id`。

必须在**旧镜像**中运行（新镜像已没有 `yishan_id_login` 包，Frappe 加载 hooks 时会失败），
且站点已开启维护模式、worker 与 scheduler 已停止、已完成一致性备份。完成后立即把 `apps.txt`
中的 `yishan_id_login` 换成 `yishan_id`、切换到新镜像，再执行 migrate 与 clear-cache。

    deploy.sh compose exec -T backend env/bin/python - --site bizbase.geokeji.com < rename_yishan_id.py

迁移内容：
- 标准模块 Module Def `yishan_id_login` → `yishan_id`。`rename_doc` 同步所有指向 Module Def 的
  Link 字段（DocType.module、Workspace.module 等）、动态链接与用户设置。
- 已安装应用记录、`installed_apps` 全局值、User / System Settings 的默认应用、Dock 与 Desktop Icon
  的 app 字段。
历史类记录（Version、Permission Log、Activity Log 等）保持原样。已迁移的站点重复运行时直接退出。
"""

import argparse
import json
import os

OLD, NEW = "yishan_id_login", "yishan_id"
SITES = "/home/frappe/frappe-bench/sites"


def migrate(frappe):
	from frappe.model.rename_doc import rename_doc

	apps = frappe.get_installed_apps()
	if OLD not in apps and NEW in apps:
		if frappe.db.get_value("Module Def", NEW, "app_name") != NEW:
			raise RuntimeError("已安装新应用，但模块归属不一致")
		print("已经迁移，无需重复执行")
		return False
	if str(frappe.conf.maintenance_mode) != "1":
		raise RuntimeError("先开启维护模式并停止 worker 与 scheduler")
	if apps.count(OLD) != 1 or NEW in apps:
		raise RuntimeError("已安装应用不符合预期")
	if frappe.db.get_value("Module Def", OLD, "app_name") != OLD or frappe.db.exists("Module Def", NEW):
		raise RuntimeError("模块归属或目标名称不符合预期")
	if frappe.db.get_value("DocType", "Yishan ID Binding", "module") != OLD:
		raise RuntimeError("绑定 DocType 的模块不符合预期")

	# 标准模块的 before_rename 只允许改名自定义模块；来源与目标已在上面核对，跳过该校验。
	rename_doc("Module Def", OLD, NEW, validate=False, rebuild_search=False, show_alert=False)
	frappe.db.set_value("Module Def", NEW, {"module_name": NEW, "app_name": NEW})

	for doctype, field in [
		("Installed Application", "app_name"),
		("User", "default_app"),
		("Block Module", "module"),  # Data 类型，rename_doc 不会更新
		("Sidebar", "app"),
		("Dock", "mount_on"),
		("Dock", "app"),
		("Desktop Icon", "app"),
	]:
		if frappe.db.exists("DocType", doctype) and frappe.get_meta(doctype).has_field(field):
			frappe.db.set_value(doctype, {field: OLD}, field, NEW)
	if frappe.db.get_single_value("System Settings", "default_app") == OLD:
		frappe.db.set_single_value("System Settings", "default_app", NEW)

	frappe.db.set_value("Desktop Icon", {"app": NEW, "logo_url": f"/assets/{OLD}/yishan-id.svg"},
		"logo_url", f"/assets/{NEW}/yishan-id.svg")
	for user in frappe.get_all("User", filters={"last_known_versions": ["like", f"%{OLD}%"]},
		fields=["name", "last_known_versions"]):
		versions = json.loads(user.last_known_versions)
		if OLD in versions:
			if NEW in versions:
				raise RuntimeError("用户版本快照同时含新旧安装名")
			versions[NEW] = versions.pop(OLD)
			frappe.db.set_value("User", user.name, "last_known_versions", json.dumps(versions), update_modified=False)
	if frappe.db.get_value("DocType", "Yishan ID Binding", "module") != NEW:
		raise RuntimeError("绑定 DocType 的模块引用未同步")

	# 最后切换安装身份；随后必须立即换镜像。
	frappe.db.set_global("installed_apps", json.dumps([NEW if app == OLD else app for app in apps]))
	return True


def main(argv=None):
	parser = argparse.ArgumentParser(description="yishan_id_login → yishan_id")
	parser.add_argument("--site", required=True)
	args = parser.parse_args(argv)

	import frappe

	os.chdir(SITES)
	frappe.init(site=args.site)
	frappe.connect()
	frappe.set_user("Administrator")
	try:
		if migrate(frappe):
			frappe.db.commit()
			print(f"{args.site}：{OLD} 已改名为 {NEW}。请立即更新 apps.txt、切换新镜像并执行 migrate。")
	except Exception:
		frappe.db.rollback()
		raise
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
