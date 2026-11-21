app_name = "geo_analysis"
app_title = "数据分析"
app_publisher = "geokeji-com"
app_description = "管理样本分析、指标口径与报告版本。"
app_license = "MIT"
required_apps = ["task_execution", "geo_service"]

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/geo_analysis/icon.svg",
        "route": "/desk/geo-analysis",
        "has_permission": "geo_analysis.can_access_app",
    }
]
