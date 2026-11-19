app_name = "customer_board"
app_title = "客户看板"
app_publisher = "geokeji-com"
app_description = "客户看板"
app_license = "MIT"

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/customer_board/icon.svg",
        "route": "/desk/customer_board",
        "has_permission": "customer_board.can_access_app",
    }
]
