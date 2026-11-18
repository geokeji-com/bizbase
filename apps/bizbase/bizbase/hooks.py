app_name = "bizbase"
app_title = "GEO"
app_publisher = "geokeji-com"
app_description = "GEO 业务应用"
app_license = "MIT"

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/bizbase/icon.svg",
        "route": "/desk/bizbase",
        "has_permission": "bizbase.can_access_app",
    }
]
