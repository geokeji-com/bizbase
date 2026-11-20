"""Give existing reports exactly one entry; never infer the public host from a request."""

import frappe
from frappe.query_builder.functions import Concat

from file_share.publication import DOMAIN, ENTRY, epoch, parse_origin


def execute():
	origin = frappe.conf.get("file_share_primary_origin") or frappe.conf.get("host_name")
	if not origin and frappe.local.site == "bizbase.geokeji.com":
		origin = "https://bizbase.geokeji.com"
	if not origin:
		if frappe.db.count("File Share"):
			frappe.throw("迁移前请设置本站 file_share_primary_origin（原有链接的完整外部访问地址）")
		return
	domain, origin = parse_origin(origin)
	if not frappe.db.exists(DOMAIN, domain):
		frappe.get_doc({"doctype": DOMAIN, "display_name": domain, "origin": origin, "status": "Enabled"}).insert(ignore_permissions=True)
	domain_epoch = frappe.db.get_value(DOMAIN, domain, "domain_epoch")
	# This is a one-time patch, in the same transaction as schema migration. Do not re-save
	# the parent: uploads, session revocation epochs and source history must not change.
	for report in frappe.get_all("File Share", fields=["name", "share_url"]):
		name = report.name
		if report.share_url == f"/file-share/s/{name}":
			continue  # a retried migration must not re-open a subsequently withdrawn report
		if not frappe.db.exists(ENTRY, {"parent": name, "parenttype": "File Share", "parentfield": "entries"}):
			frappe.get_doc({"doctype": ENTRY, "parenttype": "File Share", "parentfield": "entries",
				"parent": name, "idx": 1, "domain": domain, "enabled": 1, "access_mode": "Inherit",
				"version_mode": "Follow", "rule_epoch": epoch(), "version_epoch": epoch(),
				"legacy_domain_epoch": domain_epoch}).db_insert()
	share = frappe.qb.DocType("File Share")
	frappe.qb.update(share).set(share.share_url, Concat("/file-share/s/", share.name)).run()
	# A historical log had no title snapshot. Recover the current title where the report
	# still exists, leaving deleted reports and unattributable historical domains blank.
	frappe.db.multisql({
		"postgres": '''UPDATE "tabFile Share Access Log" AS l SET title_snapshot = s.title
			FROM "tabFile Share" AS s WHERE l.share = s.name AND COALESCE(l.title_snapshot, '') = '' ''',
		"mariadb": '''UPDATE `tabFile Share Access Log` AS l JOIN `tabFile Share` AS s ON l.share = s.name
			SET l.title_snapshot = s.title WHERE COALESCE(l.title_snapshot, '') = '' ''',
	})
