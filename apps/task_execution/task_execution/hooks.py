app_name = "task_execution"
app_title = "任务执行"
app_publisher = "geokeji-com"
app_description = "管理采集、发布和监测任务的领取、执行与回传。"
app_license = "MIT"

scheduler_events = {"cron": {"*/5 * * * *": ["task_execution.api.expire_tasks"]}}

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/task_execution/icon.svg",
        "route": "/desk/task-execution",
        "has_permission": "task_execution.can_access_app",
    }
]
