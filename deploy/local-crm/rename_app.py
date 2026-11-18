"""在旧镜像、维护模式及完成备份后执行的一次性空 App 改名迁移。"""
import json
import os

import frappe
from frappe.model.rename_doc import rename_doc


def main():
    os.chdir("/home/frappe/frappe-bench/sites")
    frappe.init(site="frontend")
    frappe.connect()
    frappe.set_user("Administrator")
    try:
        apps = frappe.get_installed_apps()
        if "bizbase" not in apps and "geo_operations" in apps:
            print("应用已经迁移，无需重复执行")
            return
        assert frappe.conf.maintenance_mode, "先开启维护模式并停止后台任务"
        assert "bizbase" in apps and "geo_operations" not in apps
        assert not frappe.db.count("DocType", {"module": "BizBase"}), "仅适用于当前空 App"
        for dt in ["Module Def", "Workspace"]:
            assert frappe.db.exists(dt, "BizBase")
            assert not frappe.db.exists(dt, "geo_operations"), "存在同名对象，停止迁移"
        assert frappe.db.get_value("Module Def", "BizBase", "app_name") == "bizbase"
        # 已验证来源、目标和空 App 边界；标准模块默认禁止界面改名。
        # rename_doc 仍会更新 Link、Dynamic Link、用户设置和附件引用。
        for dt in ["Module Def", "Workspace"]:
            rename_doc(dt, "BizBase", "geo_operations", validate=False,
                              rebuild_search=False, show_alert=False)
        frappe.db.set_value("Module Def", "geo_operations", {
            "module_name": "geo_operations", "app_name": "geo_operations"})
        frappe.db.set_value("Workspace", "geo_operations", {
            "title": "geo_operations", "label": "geo_operations", "module": "geo_operations"})
        for dt, field in [("Installed Application", "app_name"), ("User", "default_app"),
                          ("Dock", "app"), ("Desktop Icon", "app")]:
            if frappe.db.exists("DocType", dt) and frappe.get_meta(dt).has_field(field):
                for name in frappe.get_all(dt, filters={field: "bizbase"}, pluck="name"):
                    frappe.db.set_value(dt, name, field, "geo_operations")
        if frappe.db.get_single_value("System Settings", "default_app") == "bizbase":
            frappe.db.set_single_value("System Settings", "default_app", "geo_operations")
        frappe.clear_cache()
        # 最后切换安装身份；随后必须立即切换镜像，再执行 migrate/clear-cache。
        frappe.db.set_global("installed_apps", json.dumps([
            "geo_operations" if a == "bizbase" else a for a in apps]))
        frappe.db.commit()
        print("安装身份、标准模块、工作区及关联引用已迁移至 geo_operations")
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
