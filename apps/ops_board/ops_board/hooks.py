app_name = "ops_board"
app_title = "运营看板"
app_publisher = "geokeji-com"
app_description = "运营看板"
app_license = "MIT"

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/ops_board/icon.svg",
        "route": "/desk/ops_board",
        "has_permission": "ops_board.can_access_app",
    }
]
