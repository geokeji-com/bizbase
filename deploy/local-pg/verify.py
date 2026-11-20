"""Read-only smoke test, executed with the bench environment on the local PG site."""
import os
from importlib.metadata import version

import frappe

EXPECTED = {
    "frappe": "16.56.0", "erpnext": "16.55.0", "crm": "16.0.4", "insights": "3.50.1",
    "yishan_id": "0.1.0", "file_share": "0.1.0", "bizbase_mgmt": "0.0.1",
    "sales_board": "0.0.1", "ops_board": "0.0.1", "customer_board": "0.0.1",
}


def main():
    os.chdir("sites")
    frappe.init(site="frontend")
    try:
        frappe.connect()
        if frappe.db.db_type != "postgres" or frappe.db.sql("SHOW server_version_num")[0][0][:2] != "16":
            raise RuntimeError("expected PostgreSQL 16")
        installed = {app: version(app) for app in frappe.get_installed_apps()}
        if installed != EXPECTED:
            raise RuntimeError(f"unexpected installed app versions: {installed}")
        if frappe.db.get_value("Insights Data Source v3", "Site DB", "database_type") != "PostgreSQL":
            raise RuntimeError("Insights Site DB has the wrong database type")
        from insights.insights.doctype.insights_data_source_v3.connectors.frappe_db import get_sitedb_connection
        connection = get_sitedb_connection()
        try:
            if connection.sql("select 1::integer as health").execute().iloc[0, 0] != 1:
                raise RuntimeError("unexpected result from Insights PostgreSQL connector")
        finally:
            connection.disconnect()
        print("PostgreSQL 16；10 个应用版本正确；Insights 已通过站点数据源执行查询。")
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
