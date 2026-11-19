"""Run with bench's Python from the bench root. Render examples without queueing mail."""

import argparse
import inspect
import os
from contextlib import ExitStack
from email import message_from_string, policy
from pathlib import Path
from unittest.mock import patch

import frappe
from bs4 import BeautifulSoup
from frappe.core.doctype.user.user import User
from frappe.email.doctype.email_account.email_account import EmailAccount
from frappe.email.doctype.email_queue.email_queue import QueueBuilder
from frappe.www import login


def verify(isolated=False):
    address = "sample@example.invalid"
    link = "https://example.invalid/test-only?example=1&sample=2"
    user = frappe.get_doc({"doctype": "User", "enabled": 1, "name": address, "email": address, "first_name": "示例同事"})
    output = []
    rendered = []

    def capture(builder, send_now=False):
        assert builder.recipients == [address]
        mail = message_from_string(builder.prepare_email_content().as_string(), policy=policy.default)
        html = BeautifulSoup(mail.get_body(preferencelist=("html",)).get_content(), "html.parser")
        text = mail.get_body(preferencelist=("plain",)).get_content()
        images = html.select('a[href="https://geokeji.com/"] img[src^="cid:"]')
        assert len(images) == 1 and "移山科技" in images[0]["alt"]
        cid = images[0]["src"][4:]
        parts = [p for p in mail.walk() if p.get("Content-ID") == f"<{cid}>"]
        assert len(parts) == 1 and parts[0].get_content_disposition() == "inline" and parts[0].get_content_type() == "image/png"
        assert parts[0].get_payload(decode=True) == Path(frappe.get_app_path("yishan_id_login", "public", "yishan-tech-mail.png")).read_bytes()
        assert text.rstrip().endswith("https://geokeji.com/") and "移山科技官网" in text
        subject = str(mail["Subject"])
        assert subject.count("移山科技 数据中台(BizBase)") == 1
        rendered.append(html)
        output.append((subject, text))

    with ExitStack() as stack:
        stack.enter_context(patch.object(QueueBuilder, "process", capture))
        stack.enter_context(patch.object(User, "_reset_password", return_value=link))
        stack.enter_context(patch.object(login, "_generate_temporary_login_link", return_value=link))
        if isolated:
            stack.enter_context(patch.object(EmailAccount, "find_outgoing", return_value=frappe._dict(name="模拟发件账号", default_sender="sender@example.invalid")))
        user.send_welcome_mail_to_user()
        user.password_reset_mail(link)
        if frappe.get_system_settings("login_with_email_link"):
            inspect.unwrap(login.send_login_link)(address)
        accounts = len(output)
        assert accounts == 2 + bool(frappe.get_system_settings("login_with_email_link")), "部分邮件未成功组装"
        message = f'<p>请核对示例单据。</p><a href="{link}">{link}</a>'
        frappe.sendmail(recipients=address, subject="示例单据已收货", message=message)
        frappe.sendmail(recipients=address, subject="【移山科技 数据中台(BizBase)】示例摘要", message=f"<html><body>{message}</body></html>", raw_html=True)
    assert output[-2][0] == "【移山科技 数据中台(BizBase)】示例单据已收货"
    assert output[-1][0] == "【移山科技 数据中台(BizBase)】示例摘要"
    assert output[0][0] == "【移山科技 数据中台(BizBase)】欢迎使用，您的账号已创建" and address in output[0][1] and "移山 ID" in output[0][1]
    assert output[1][0] == "【移山科技 数据中台(BizBase)】重置您的密码" and "重置" in output[1][1]
    minutes = int(frappe.get_system_settings("reset_password_link_expiry_duration") or 0) // 60
    if minutes:
        assert f"{minutes} 分钟" in output[1][1]
    if accounts == 3:
        expiry = frappe.get_system_settings("login_with_email_link_expiry") or 10
        assert "登录" in output[2][0] and "BizBase" in output[2][0]
        assert "一次" in output[2][1] and f"{expiry} 分钟" in output[2][1]
    for html, (subject, text) in zip(rendered, output, strict=True):
        assert "Frappe" not in html.get_text()
        assert not html.select('img[src*="frappe-wordmark"], img[src*="frappe-framework-logo"], a[href*="via_email_footer"]')
        assert html.find("a", href=link) and link in text
        print("通过：", subject)


def verify_notifications():
    from frappe.utils.jinja import get_email_from_template

    cases = [
        ("user_invitation", dict(title="BizBase", invited_by="示例同事", expiry_days=3, invite_link="https://example.invalid/invite"), ("示例同事", "3 天", "https://example.invalid/invite")),
        ("user_invitation_cancelled", {"title": "BizBase"}, ("取消", "BizBase")),
        ("user_invitation_expired", {"title": "BizBase"}, ("过期", "BizBase")),
        ("administrator_logged_in", dict(date_and_time="2000-01-01", ip_address="192.0.2.1"), ("登录时间", "192.0.2.1")),
        ("verification_code", dict(code="000000", minutes=5), ("验证码", "000000", "5 分钟")),
        ("two_factor_setup", {"qrcode_link": "https://example.invalid/setup"}, ("验证器", "https://example.invalid/setup")),
    ]
    if "erpnext" in frappe.get_installed_apps():
        cases.extend([
            ("confirm_appointment", dict(full_name="示例同事", site_url="example.invalid", link="https://example.invalid/appointment", expiry_minutes=12), ("确认预约", "12 分钟", "https://example.invalid/appointment")),
            ("appointment_confirmed", dict(full_name="示例同事", site_url="example.invalid", scheduled_time="15:30"), ("预约时间", "15:30")),
            ("reorder_item", {"mr_list": []}, ("物料需求单",)),
        ])
    for name, context, expected in cases:
        html, _ = get_email_from_template(name, context)
        assert all(item in html for item in expected), name
    print(f"通过：{len(cases)} 个邀请、安全与业务邮件正文")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site")
    parser.add_argument("--isolated", action="store_true", help="Use a fake outgoing account on an isolated test site")
    args = parser.parse_args()
    os.chdir("sites")
    frappe.init(site=args.site)
    frappe.connect()
    try:
        frappe.set_user("Administrator")
        verify(args.isolated)
        verify_notifications()
    finally:
        frappe.db.rollback()
        frappe.destroy()
