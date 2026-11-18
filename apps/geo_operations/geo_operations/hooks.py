app_name = "geo_operations"
app_title = "GEO 运营"
app_publisher = "geokeji-com"
app_description = "GEO 运营"
app_license = "MIT"

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/geo_operations/icon.svg",
        "route": "/desk/geo_operations",
        "has_permission": "geo_operations.can_access_app",
    }
]
