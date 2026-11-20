app_name = "file_share"
app_title = "文件分享"
app_publisher = "geokeji-com"
app_description = "员工上传 HTML 等静态内容，按内部、指定人员、密码或公开范围分享"
app_license = "MIT"

app_include_js = ["/assets/file_share/desk-routes.js"]

add_to_apps_screen = [
	{
		"name": app_name,
		"title": app_title,
		"logo": "/assets/file_share/icon.svg",
		"route": "/desk/file-share",
		"has_permission": "file_share.permissions.can_open_desk",
	}
]

# /file-share 为管理入口；/file-share/<ID> 与旧 /s/<ID> 共用渲染器。
page_renderer = ["file_share.serve.ShareRenderer"]

permission_query_conditions = {
	"File Share": "file_share.permissions.share_query",
	"File Share Access Log": "file_share.permissions.access_log_query",
}

has_permission = {
	"File Share": "file_share.permissions.share_has_permission",
	"File Share Access Log": "file_share.permissions.access_log_has_permission",
}

required_apps = ["erpnext"]  # Employee.user_id / status
doc_events = {
	"File": {"before_validate": "file_share.permissions.validate_file"},
	"File Share Role": {"validate": "file_share.permissions.reject_direct_child_save"},
	"File Share User": {"validate": "file_share.permissions.reject_direct_child_save"},
}

extend_doctype_class = {"File": ["file_share.permissions.ShareFileGuard"]}
