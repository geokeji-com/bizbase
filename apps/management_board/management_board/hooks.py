app_name = "management_board"
app_title = "管理看板"
app_publisher = "geokeji-com"
app_description = "管理看板"
app_license = "MIT"

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/management_board/icon.svg",
        "route": "/desk/management_board",
        "has_permission": "management_board.can_access_app",
    }
]

# 应用屏统一排序（两行：自研入口在前，Insights/ERP/Build 在后）
extend_bootinfo = ["management_board.apps_screen.apply"]
app_include_js = ["/assets/management_board/apps-screen.js", "/assets/management_board/workspace-urls.js"]
