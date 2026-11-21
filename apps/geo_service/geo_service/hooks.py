app_name = "geo_service"
app_title = "服务管理"
app_publisher = "geokeji-com"
app_description = "管理 GEO 服务范围、问句与监测计划。"
app_license = "MIT"

required_apps = ["erpnext", "task_execution"]

doc_events = {
    "GEO Service": {"validate": "geo_service.validation.service"},
    "GEO Prompt": {"validate": "geo_service.validation.prompt"},
    "GEO Sampling Slot": {"validate": "geo_service.validation.slot"},
    "GEO Service Prompt": {"validate": "geo_service.validation.service_prompt"},
    "GEO Monitoring Plan": {"validate": "geo_service.validation.plan"},
}

scheduler_events = {"hourly": ["geo_service.api.dispatch_due_plans"]}

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/geo_service/icon.svg",
        "route": "/desk/geo-service",
        "has_permission": "geo_service.can_access_app",
    }
]
