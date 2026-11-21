"""BizBase 应用屏的统一排序。

Frappe 16 的应用屏是 6 列网格，按 `frappe.boot.app_data[].sequence_id` 升序排列。
ERPNext 自带 `sequence_id: 1`，CRM、Insights 未声明（按 100 处理），Framework 为 1000。
这里集中改写一次，避免在各 App 的 hooks 里分散维护、互相抢位。

第一行：移山 ID、文件分享、管理看板、销售看板、运营看板、客户看板。
第二行：Insights、ERP、Build（Frappe 框架入口 /desk/build）。
"""

APPS_SCREEN_ORDER = {
	"yishan_id": 1,
	"file_share": 2,
	"management_board": 3,
	"sales_board": 4,
	"ops_board": 5,
	"customer_board": 6,
	"insights": 11,
	"erpnext": 13,
	"frappe": 14,
}

APPS_SCREEN_TITLES = {
	"erpnext": "ERP",
	"frappe": "Build",
}


# Register routes only for workspaces visible in the apps screen.
WORKSPACE_APPS = {"management_board", "sales_board", "ops_board", "customer_board"}


def apply(bootinfo):
	aliases = {}
	apps = [app for app in bootinfo.get("app_data") or [] if app.get("app_name") != "crm"]
	bootinfo["app_data"] = apps
	roles = (bootinfo.get("user") or {}).get("roles") or []
	for app in apps:
		name = app.get("app_name")
		if name in APPS_SCREEN_ORDER:
			app["sequence_id"] = APPS_SCREEN_ORDER[name]
		if name in APPS_SCREEN_TITLES:
			app["app_title"] = APPS_SCREEN_TITLES[name]
		if name == "erpnext" and {"Sales User", "Sales Manager", "System Manager"}.intersection(roles):
			app["app_route"] = "/desk/selling"
		if name in WORKSPACE_APPS:
			slug = name.replace("_", "-")
			aliases[slug] = name
			if name == "management_board":
				aliases["bizbase-mgmt"] = aliases["bizbase_mgmt"] = name
			if app.get("app_route") == f"/desk/{name}":
				app["app_route"] = f"/desk/{slug}"
	bootinfo["bizbase_workspace_aliases"] = aliases
