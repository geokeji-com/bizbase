app_name = "yishan_id"
app_title = "移山 ID"
app_publisher = "geokeji-com"
app_description = "站点级移山 ID（飞书员工）登录"
app_license = "MIT"

add_to_apps_screen = [
	{
		"name": app_name,
		"title": app_title,
		"logo": "/assets/yishan_id/yishan-id.svg",
		"route": "/yishan-id",
		"has_permission": "yishan_id.can_manage_bindings",
	}
]

# Both Desk and website pages count navigation through a first-party, isolated frame.
app_include_js = ["/assets/yishan_id/clarity-features.js", "/assets/yishan_id/clarity-navigation.js"]
web_include_js = app_include_js.copy()
after_request = ["yishan_id.usage.standalone_view"]

website_redirects = [
	{"source": "/yishan-id", "target": "/desk/yishan-id-binding", "redirect_http_status": 302},
	{
		"source": "/yishan-id/login",
		"target": "/api/method/yishan_id.auth.start",
		"redirect_http_status": 302,
		"forward_query_parameters": True,
	},
]

# 每个请求复查移山 ID 会话的在职状态；非移山 ID 会话直接跳过。
before_request = ["yishan_id.session.enforce"]

# 在 /login 页增加移山 ID 按钮。
update_website_context = ["yishan_id.auth.login_page_context"]
