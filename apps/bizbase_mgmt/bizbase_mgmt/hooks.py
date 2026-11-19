app_name = "bizbase_mgmt"
app_title = "管理看板"
app_publisher = "geokeji-com"
app_description = "管理看板"
app_license = "MIT"

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/bizbase_mgmt/icon.svg",
        "route": "/desk/bizbase_mgmt",
        "has_permission": "bizbase_mgmt.can_access_app",
    }
]

# 应用屏统一排序（两行：自研入口在前，Insights/CRM/ERPNext/Build 在后）
extend_bootinfo = ["bizbase_mgmt.apps_screen.apply"]
