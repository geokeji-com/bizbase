"""Page counts for built-in HTML views that render outside Frappe's standard layouts."""

import frappe


STANDALONE_PAGES = {
	"/banking": "web/banking",
	"/printview": "web/print",
	"/printpreview": "web/print",
}


def standalone_view(request, response):
	feature = STANDALONE_PAGES.get(request.path.rstrip("/"))
	if not feature or frappe.local.site != "bizbase.geokeji.com" or request.method != "GET":
		return
	if response.status_code != 200 or response.mimetype != "text/html" or response.is_streamed:
		return
	if response.headers.get("Content-Disposition", "").startswith("attachment"):
		return
	frame = (f'<iframe src="/_usage/{feature}" title="访问统计" aria-hidden="true" tabindex="-1" '
		'credentialless sandbox="allow-scripts" referrerpolicy="no-referrer" style="display:none" width="1" height="1"></iframe>')
	data = response.get_data()
	end = data.rfind(b"</body>")
	if end < 0:
		end = len(data)
	response.set_data(data[:end] + frame.encode() + data[end:])
