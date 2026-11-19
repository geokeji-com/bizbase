app_name = "static_share"
app_title = "分享"
app_publisher = "geokeji-com"
app_description = "员工上传 HTML 等静态内容，按内部、指定人员、密码或公开范围分享"
app_license = "MIT"

add_to_apps_screen = [
	{
		"name": app_name,
		"title": app_title,
		"logo": "/assets/static_share/icon.svg",
		"route": "/desk/static-share",
		"has_permission": "static_share.permissions.can_open_desk",
	}
]

# /s/<分享 ID>[/c/<版本>/<令牌>/<文件路径>] 由本 App 渲染。
page_renderer = ["static_share.serve.ShareRenderer"]

permission_query_conditions = {
	"Static Share": "static_share.permissions.share_query",
	"Static Share Access Log": "static_share.permissions.access_log_query",
}

has_permission = {
	"Static Share": "static_share.permissions.share_has_permission",
	"Static Share Access Log": "static_share.permissions.access_log_has_permission",
}

required_apps = ["erpnext"]  # Employee.user_id / status
doc_events = {
	"File": {"before_validate": "static_share.permissions.validate_file"},
	"Static Share Role": {"validate": "static_share.permissions.reject_direct_child_save"},
	"Static Share User": {"validate": "static_share.permissions.reject_direct_child_save"},
}

extend_doctype_class = {"File": ["static_share.permissions.ShareFileGuard"]}
