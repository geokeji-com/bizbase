"""Brand outgoing BizBase mail at assembly time, including plain-text mail."""

BRAND = "移山科技 数据中台(BizBase)"
PREFIX = f"【{BRAND}】"
WEBSITE = "https://geokeji.com/"
LOGO = "assets/yishan_id_login/yishan-tech-mail.png"


def subject_line(subject):
	value = (subject or "").strip().replace("【移山科技数据中台(BizBase)】", PREFIX)
	if BRAND in value:
		return value
	labels = {
		"[No Subject]": "系统通知",
		"欢迎使用 BizBase": "欢迎使用，您的账号已创建",
		"重置您的 BizBase 密码": "重置您的密码",
		"登录 BizBase 的专属链接": "您的专属登录链接",
	}
	return PREFIX + labels.get(value, value or "系统通知")


def html_with_footer(html):
	# Keep the original HTML intact, including Outlook conditional comments.
	footer = (
		'<div align="center" style="margin:20px auto;padding:12px;text-align:center">'
		f'<a href="{WEBSITE}" style="display:inline-block;background-color:#fff;'
		'padding:6px 10px;color:#222;text-decoration:none">'
		f'<img embed="{LOGO}" width="32" height="32" alt="移山科技标志" '
		'style="vertical-align:middle;border:0">'
		'<span style="vertical-align:middle">&nbsp;移山科技官网</span></a></div>'
	)
	end = html.rfind("</body>")  # Frappe's mail formatter serializes lowercase tags.
	return html[:end] + footer + html[end:] if end >= 0 else html + footer


def text_with_footer(text):
	return (text or "").rstrip() + f"\n\n移山科技官网　{WEBSITE}"
