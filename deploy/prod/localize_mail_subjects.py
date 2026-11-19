"""Localize outgoing mail copy in a Frappe 16.56.0 bench at image build time.

Usage: python3 localize_mail_subjects.py [BENCH_PATH] (defaults to cwd).
Run before starting Frappe processes. Requires only the Python standard library.
"""

import argparse
import re
import stat
from pathlib import Path
from tempfile import NamedTemporaryFile


VERSION = "16.56.0"

# Each rule contains upstream text, final text and any earlier shipped variant.
# Include call-site context where the same text appears outside outgoing mail.
OTP_SETTING = 'frappe.get_system_settings("otp_issuer_name")'
OTP_SUBJECT_END = (f'\n\t\t{OTP_SETTING}\n\t)\n'
                   '\treturn frappe.render_template(subject_template, kwargs_dict, restrict_globals=True)')
OTP_SUBJECT_START = 'def get_email_subject_for_2fa(kwargs_dict):\n\t"""Get email subject for 2fa."""\n\t'
PATCHES = {
    "email/doctype/email_queue/email_queue.py": [
        ("\t\tself.subject = subject\n", "\t\tfrom yishan_id_login.mail_brand import subject_line\n\n\t\tself.subject = subject_line(subject)\n"),
    ],
    "email/email_body.py": [
        ("\t\tself.subject = subject\n", "\t\tfrom yishan_id_login.mail_brand import subject_line\n\n\t\tself.subject = subject_line(subject)\n"),
        ("\t\tself.set_part_html(formatted, inline_images)", "\t\tfrom yishan_id_login.mail_brand import html_with_footer\n\n\t\tself.set_part_html(html_with_footer(formatted), inline_images)"),
        ('part = MIMEText(message, "plain", "utf-8", policy=policy.SMTP)', 'from yishan_id_login.mail_brand import text_with_footer\n\n\t\tpart = MIMEText(text_with_footer(message), "plain", "utf-8", policy=policy.SMTP)'),
    ],
    "www/login.py": [
        ('subject = _("Login To {0}").format(app_name)',
         'if app_name in ("Frappe", "Frappe Framework", _("Frappe")):\n'
         '\t\t\tapp_name = "BizBase"\n'
         '\t\tsubject = f"登录 {app_name} 的专属链接"'),
    ],
    "core/doctype/user_invitation/user_invitation.py": [
        ('def _get_email_title(self):\n\t\treturn frappe.get_hooks("app_title", app_name=self.app_name)[0]',
         'def _get_email_title(self):\n\t\ttitle = frappe.get_hooks("app_title", app_name=self.app_name)[0]\n'
         '\t\tif self.app_name == "frappe" and title in ("Frappe", "Frappe Framework"):\n'
         '\t\t\tfrom frappe.email.email_body import get_brand_name\n\n'
         '\t\t\tbrand = get_brand_name()\n'
         '\t\t\treturn brand if brand and brand not in ("Frappe", "Frappe Framework") else "BizBase"\n'
         '\t\treturn title'),
        ('subject=_("You\'ve been invited to join {0}").format(email_title)', 'subject=f"邀请您加入 {email_title}"'),
        ('subject=_("Invitation to join {0} cancelled").format(email_title)', 'subject=f"加入 {email_title} 的邀请已取消"'),
        ('subject=_("Invitation to join {0} expired").format(email_title)', 'subject=f"加入 {email_title} 的邀请已过期"'),
    ],
    "workflow/doctype/workflow_action/workflow_action.py": [
        ('subject = _("Workflow Action") + f" on {doctype}: {docname}"', 'subject = f"待处理的工作流操作：{doctype}：{docname}"'),
        ('"header": "Workflow Action",', '"header": "待处理的工作流操作",'),
    ],
    "twofactor.py": [
        (OTP_SUBJECT_START + 'subject_template = _("Login Verification Code from {}").format(' + OTP_SUBJECT_END,
         'def _otp_email_display_name(issuer):\n'
         '\treturn "BizBase" if not issuer or issuer == "Frappe Framework" else issuer\n\n\n'
         + OTP_SUBJECT_START + f'issuer = _otp_email_display_name({OTP_SETTING})\n'
         '\treturn f"{issuer} 登录验证码"',
         OTP_SUBJECT_START + 'subject_template = "{} 登录验证码".format(' + OTP_SUBJECT_END),
        ('subject_template = _("One Time Password (OTP) Registration Code from {}").format(' + OTP_SUBJECT_END,
         f'issuer = _otp_email_display_name({OTP_SETTING})\n\treturn f"{{issuer}} 身份验证器设置"',
         'subject_template = "{} 身份验证器设置".format(' + OTP_SUBJECT_END),
        ('otp_issuer = settings.otp_issuer_name or "Frappe Framework"\n\tuser_email =',
         'from html import escape\n\n\temail_issuer = _otp_email_display_name(settings.otp_issuer_name)\n\tuser_email ='),
        ('"subject": _("OTP Secret Reset - {0}").format(otp_issuer)',
         '"subject": f"{email_issuer} 的动态口令密钥已重置"', '"subject": f"{otp_issuer} 的动态口令密钥已重置"'),
        ('"message": _(\n\t\t\t"<p>Your OTP secret on {0} has been reset. If you did not perform this reset and did not request it, please contact your System Administrator immediately.</p>"\n\t\t).format(otp_issuer)',
         '"message": (\n\t\t\tf"<p>您在 {escape(email_issuer)} 的动态口令密钥已重置，下次登录时需要重新设置双因素认证。"\n'
         '\t\t\t"如果此次重置并非您本人操作，也不是应您的要求进行，请立即联系系统管理员。</p>"\n\t\t)',
         '"message": f"<p>您在 {otp_issuer} 的动态口令密钥已重置。如果您未执行或申请重置，请立即联系系统管理员。</p>"'),
    ],
    "core/doctype/user/user.py": [
        ('_("Password Reset"),\n\t\t\t"password_reset",', '"重置密码",\n\t\t\t"password_reset",'),
        ('subject = _("Welcome to {0}").format(site_name)', 'subject = f"欢迎使用 {site_name}"'),
        ('subject = _("Complete Registration")', 'subject = "完成账号注册"'),
        ('subject=_("Administrator Logged In")', 'subject="管理员账号已登录"'),
        ('subject=_("Security Alert: Your password has been changed.")', 'subject="安全提醒：您的密码已更改"'),
        ('email_message = _(\n\t\t\t\t\t"Your password has been changed and you might have been logged out of all systems.<br>Please contact the Administrator for further assistance."\n\t\t\t\t)',
         'email_message = "您的密码已更改，您可能已从所有系统退出登录。<br>如需帮助，请联系管理员。"'),
        ('subject=_("Security Alert: Your account is being impersonated")', 'subject="安全提醒：有人正在以您的身份操作"'),
        ('email_message = _(\n\t\t\t"User {0} has started an impersonation session as you. <br><br><b>Reason provided:</b> {1}"\n\t\t).format(escape_html(impersonator), escape_html(reason))',
         'email_message = "用户 {0} 已开始以您的身份操作。<br><br><b>操作原因：</b>{1}".format(escape_html(impersonator), escape_html(reason))'),
    ],
    "core/doctype/security_settings/security_settings_alert.py": [
        ('return f"[URGENT] Security.txt expires in 1 day - {site}"', 'return f"【紧急】{site} 的 security.txt 将在 1 天后到期"'),
        ('return f"Security.txt expires in {days_until_expiry} days - {site}"', 'return f"{site} 的 security.txt 将在 {days_until_expiry} 天后到期"'),
    ],
    "website/doctype/personal_data_download_request/personal_data_download_request.py": [
        ('subject=_("Download Your Data")', 'subject="下载您的个人数据"'),
        ('header=[_("Download Your Data"),', 'header=["下载您的个人数据",'),
    ],
    "website/doctype/personal_data_deletion_request/personal_data_deletion_request.py": [
        ('subject=_("Confirm Deletion of Account")', 'subject="请确认删除账号"'),
        ('header=[_("Confirm Deletion of Account"),', 'header=["请确认删除账号",'),
        ('subject=_("User {0} has requested for data deletion").format(self.email)', 'subject=f"用户 {self.email} 已申请删除个人数据"'),
        ('header=[_("Approval Required"),', 'header=["需要审批",'),
        ('subject=_("Your account has been deleted")', 'subject="您的账号已停用，个人数据处理已安排"', 'subject="您的账号已删除"'),
        ('header=[_("Your account has been deleted"),', 'header=["您的账号已停用",', 'header=["您的账号已删除",'),
    ],
    "desk/doctype/event/event.py": [
        ('subject=frappe._("Upcoming Events for Today")', 'subject="今日待办日程"'),
        ('header=[frappe._("Events in Today\'s Calendar"),', 'header=["今日日程",'),
        ('e.starts_on = "All Day"', 'e.starts_on = "全天"'),
    ],
    "desk/form/document_follow.py": [
        ('subject=_("Document Follow Notification")', 'subject="您关注的文档有更新"'),
    ],
    "desk/page/backups/backups.py": [
        ('subject = _("File backup is ready")', 'subject = "文件备份已就绪"'),
    ],
    "desk/utils.py": [
        ('subject=frappe._("Your exported report: {0}").format(report_name)', 'subject=f"您导出的报表：{report_name}"'),
        ('message=frappe._(\n\t\t\t"The report you requested has been generated.<br><br>"\n'
         '\t\t\t"Click here to download:<br>"\n\t\t\t"<a href=\'{0}\'>{0}</a><br><br>"\n'
         '\t\t\t"This link will expire in {1} hours."\n\t\t).format(file_url, file_retention_hours)',
         'message=(\n\t\t\t"您请求的报表已生成。<br><br>点击下载：<br>"\n'
         '\t\t\tf"<a href=\'{file_url}\'>{file_url}</a><br><br>"\n'
         '\t\t\tf"链接将在 {file_retention_hours} 小时后失效。"\n\t\t)'),
    ],
    "www/contact.py": [
        # Restore the public signature on images that received the first patch.
        # An explicit subject (even "Website Query") belongs to the sender.
        ('def send_message(sender: str, message: str, subject: str = "网站咨询"):',
         'def send_message(sender: str, message: str, subject: str = "Website Query"):'),
        ('reply = _("Thank you for reaching out to us. We will get back to you at the earliest.")',
         'reply = "感谢您的来信，我们会尽快回复。"'),
        ('subject=_("We\'ve received your query!")', 'subject="我们已收到您的咨询"'),
    ],
}


def localize(bench):
    package = bench / "apps/frappe/frappe"
    init = (package / "__init__.py").read_text(encoding="utf-8")
    versions = re.findall(r'^__version__\s*=\s*(.+)$', init, re.MULTILINE)
    if versions != [f'"{VERSION}"']:
        raise ValueError(f"Expected one Frappe {VERSION} version declaration, found {versions!r}")

    # Preflight every file before writing any. An interrupted run can resume
    # from any mix of complete files. Each write replaces a single whole file.
    pending = {}
    for relative, rules in PATCHES.items():
        path = package / relative
        source = path.read_bytes().decode("utf-8")
        updated = source
        for rule in rules:
            original, localized, *_ = rule
            counts = [source.count(variant) for variant in rule]
            if sum(counts) != 1:
                raise ValueError(f"{path}: expected exactly one recognized match for "
                                 f"{original!r}, found {counts}")
            if not counts[1]:
                updated = updated.replace(rule[counts.index(1)], localized, 1)
        if updated != source:
            pending[path] = updated

    for path, updated in pending.items():
        with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            staged = Path(tmp.name)
            try:
                tmp.write(updated.encode("utf-8"))
                tmp.flush()
                staged.chmod(stat.S_IMODE(path.stat().st_mode))
                staged.replace(path)
            finally:
                staged.unlink(missing_ok=True)
    print(f"Frappe {VERSION}: checked {sum(map(len, PATCHES.values()))} mail patches, "
          f"updated {len(pending)}/{len(PATCHES)} files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bench", nargs="?", type=Path, default=Path.cwd())
    try:
        localize(parser.parse_args().bench)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Mail localization failed: {exc}\n")
