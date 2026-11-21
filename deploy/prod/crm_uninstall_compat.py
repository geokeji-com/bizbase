"""Frappe 16.56.0 / CRM 16.0.4: archive JSON link filters during CRM removal.

Call in the old bench's maintenance process, after the caller has frozen writes,
verified the inventory and tested its recovery point. Does not open a site,
commit, force deletion, change the manifest, or skip the installer's backup.
"""
import json
from unittest.mock import patch


def archive_serializer(original, crm_doctypes):
    def serialize(field, *args, **kwargs):
        filters = field.link_filters
        if field.parenttype != "DocType" or field.parent not in crm_doctypes or not isinstance(filters, list):
            return original(field, *args, **kwargs)
        field.link_filters = json.dumps(filters, ensure_ascii=False)
        try:
            return original(field, *args, **kwargs)
        finally:
            field.link_filters = filters

    return serialize


def uninstall_empty_crm():
    import frappe
    from importlib.metadata import version
    from frappe.core.doctype.docfield.docfield import DocField
    from frappe.installer import remove_app

    if "crm" not in frappe.get_installed_apps():
        return
    if (version("frappe"), version("crm")) != ("16.56.0", "16.0.4"):
        raise RuntimeError("Unverified versions; revalidate uninstall compatibility first")
    if not frappe.conf.get("maintenance_mode"):
        raise RuntimeError("CRM removal requires maintenance mode")
    modules = frappe.get_all("Module Def", filters={"app_name": "crm"}, pluck="name")
    if set(modules) != {"FCRM", "Lead Syncing", "Domain Enrichment"}:
        raise RuntimeError("Unexpected CRM modules; inspect the site before removal")
    owned = set(frappe.get_all("DocType", filters={"module": ["in", modules]}, pluck="name"))
    # A last guard, not a replacement for the full deployment inventory.
    for dt in ("CRM Lead", "CRM Deal", "CRM Organization", "CRM Contacts", "CRM Task", "CRM Call Log", "FCRM Note"):
        if dt not in owned or frappe.db.count(dt):
            raise RuntimeError(f"Missing or nonempty {dt}; stop and inspect")
    with patch.object(DocField, "get_valid_dict", archive_serializer(DocField.get_valid_dict, owned)):
        remove_app("crm", yes=True)
    if "crm" in frappe.get_installed_apps():
        raise RuntimeError("Uninstaller did not remove CRM")


if __name__ == "__main__":
    import argparse
    import os
    from pathlib import Path
    import frappe

    parser = argparse.ArgumentParser(description="Remove the verified-empty CRM app on the frozen old site")
    parser.add_argument("--site", required=True)
    site = parser.parse_args().site
    os.chdir("sites")
    if Path(site).name != site or not (Path(site) / "site_config.json").is_file():
        raise SystemExit("Invalid site")
    frappe.init(site=site)
    try:
        frappe.connect()
        frappe.set_user("Administrator")
        uninstall_empty_crm()
    finally:
        frappe.destroy()
