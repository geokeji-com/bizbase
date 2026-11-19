import frappe
from frappe.query_builder.functions import Concat


def execute():
	"""Refresh generated links without re-saving uploads or rotating viewer credentials."""
	share = frappe.qb.DocType("Static Share")
	(frappe.qb.update(share)
		.set(share.share_url, Concat("/file-share/", share.name))
		.where(share.share_url == Concat("/s/", share.name))
	).run()

	# Saved desktop layouts use the icon docname. Update only the old built-in values.
	icon = frappe.qb.DocType("Desktop Icon")
	app_icons = (icon.app == "static_share") & (icon.icon_type == "App")
	(frappe.qb.update(icon).set(icon.label, "文件分享")
		.where(app_icons & (icon.label == "分享"))).run()
	(frappe.qb.update(icon).set(icon.link, "/file-share")
		.where(app_icons & (icon.link == "/desk/static-share"))).run()

	# v16's optional Desktop Icon grid stores copies of labels and links in each layout.
	icon_names = set(frappe.get_all("Desktop Icon", filters={"app": "static_share", "icon_type": "App"}, pluck="name"))
	for row in frappe.get_all("Desktop Layout", fields=["name", "layout"]):
		try:
			icons = frappe.parse_json(row.layout)
		except ValueError:
			continue
		if not isinstance(icons, list):
			continue
		changed = False
		for item in icons:
			if not isinstance(item, dict) or item.get("icon_type") != "App":
				continue
			if item.get("app") != "static_share" and item.get("name") not in icon_names:
				continue
			if item.get("label") == "分享":
				item["label"] = "文件分享"
				changed = True
			if item.get("link") == "/desk/static-share":
				item["link"] = "/file-share"
				changed = True
		if changed:
			frappe.db.set_value("Desktop Layout", row.name, "layout", frappe.as_json(icons), update_modified=False)
