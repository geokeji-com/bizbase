app_name = "geo_content"
app_title = "内容管理"
app_publisher = "geokeji-com"
app_description = "管理选题、稿件、审核、投放和回链。"
app_license = "MIT"

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/geo_content/icon.svg",
        "route": "/desk/geo-content",
        "has_permission": "geo_content.can_access_app",
    }
]
