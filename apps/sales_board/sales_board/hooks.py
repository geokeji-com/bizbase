app_name = "sales_board"
app_title = "销售看板"
app_publisher = "geokeji-com"
app_description = "销售看板"
app_license = "MIT"

extend_bootinfo = ["sales_board.erp_navigation.apply"]
app_include_css = ["/assets/sales_board/erp-navigation.css"]

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/sales_board/icon.svg",
        "route": "/desk/sales_board",
        "has_permission": "sales_board.can_access_app",
    }
]
