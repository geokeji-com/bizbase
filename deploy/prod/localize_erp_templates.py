"""Localize fixed ERPNext 16.55.0 mail copy in an incremental image.

Run `python3 localize_erp_templates.py [BENCH_PATH]` after copying yishan_id.
No site connection is needed. Accept the pinned upstream, first patch or current patch.
"""

import argparse
import ast
import hashlib
import json
import stat
from pathlib import Path
from tempfile import NamedTemporaryFile


TEMPLATES = {
    "confirm_appointment": "9f3e2b2b3d9331617c44c7dfa7ef168aceb02051299e8f68f9eb817c321bf52c",
    "appointment_confirmed": "f968380e8d1fc4dd15ed43381a357dc2dd11c748d9ae842f9164803cc8581bb4",
    "reorder_item": "57bb1ee6568b0e9ce187473b4ac1eb2c5d091912678c74f5b057d6b94e0365f5",
}

# Match fixed copy in the 16.55.0 sources. Field lookups, template precedence,
# link generation, recipient selection and send conditions stay in upstream code.
PATCHES = {
    "crm/doctype/appointment/appointment.py": ("91b8953b086fe180513a55a96033dd699bdecf661a70c9d128e3b0ff7f11f864", [
        ('subject=_("Appointment Confirmation")', 'subject="请验证邮箱并确认预约"'),
        ('subject=_("Appointment Confirmed")', 'subject="预约已确认"'),
    ]),
    "stock/reorder_item.py": ("98308b246745ab192058e6a65e1a93e8449c9f27404d79ea4d479a94f817e44e", [
        ('subject=_("Auto Material Requests Generated")', 'subject="系统已自动生成物料需求单"'),
        ('_("[Important] [ERPNext] Auto Reorder Errors")', '"【重要】ERPNext 自动补货异常"'),
        ('_("Dear System Manager,")', '"系统管理员，您好！"'),
        ("An error occurred for certain Items while creating Material Requests based on Re-order level. Please rectify these issues :", "系统根据重订货点生成物料需求单时，部分物料处理失败。请核查以下错误："),
        ('_("Regards,") + "<br>" + _("Administrator")', '"此致<br>管理员"'),
    ]),
    "projects/doctype/project/project.py": ("5d4ff3d29e1d56b2223f6c44ac2b0b6a12deecec56f811c6fd5a5d840bc2c6a4", [
        ('_("You have been invited to collaborate on the project {0}.")', '"您已获邀参与项目 {0}。"'),
        ('_("Project Collaboration Invitation")', '"项目协作邀请"'),
        ('_("Project Summary for {0}")', '"{0} 项目摘要"'),
        ('_("Daily Project Summary for {0}")', '"项目日报：{0}"'),
    ]),
    "projects/doctype/project/project.js": ("1e72427220045f36732e216aa07e67e2e221c703bd47de49e9cf8e5d79270bf0", [
        ('__("For project - {0}, update your status", [frm.doc.project_name])', '`请更新项目“${frm.doc.project_name}”的进展`'),
    ]),
    "projects/doctype/project_update/project_update.py": ("5950c4fe41e70b93c9ce5dedf99763bbd0467fc35895cffe8330092324869053", [
        ("<p>Project Name: ", "<p>项目名称："), ("<p>Frequency: ", "<p>频率："),
        ("<p>Update Reminder:", "<p>更新提醒："), ("<p>Expected Date End:", "<p>预计结束日期："),
        ("<p>Percent Progress:", "<p>完成百分比："), ("<p>Number of Updates:", "<p>更新次数："),
        ("<p>Number of drafts:", "<p>草稿数："),
        ("<th>Project ID</th><th>Date Updated</th><th>Time Updated</th>", "<th>项目编号</th><th>更新日期</th><th>更新时间</th>"),
        ('frappe._(project_name + " " + "Summary")', 'f"{project_name} 项目摘要"'),
    ]),
    "accounts/doctype/payment_request/payment_request.py": ("98ee03950e1d959da816b07c054e8c3bb182f1baee0d02265f56e52535ba65a6", [
        ('_("Payment Request for {0}")', '"付款请求：{0}"'),
        ("<p>Dear {{ doc.contact_person }},</p>", "<p>{{ doc.contact_person }}，您好！</p>"),
        ("<p>Hello,</p>", "<p>您好！</p>"),
        ('_("Requesting payment against {0} {1} for amount {2}")', '"请支付 {0} {1} 的款项，金额为 {2}。"'),
        ('{{ _("Make Payment") }}', '前往付款'),
        ('{{ _("If you have any questions, please get back to us.") }}', '如有疑问，请与我们联系。'),
        ('{{ _("Thank you for your business!") }}', '感谢您的惠顾！'),
    ]),
    "buying/doctype/request_for_quotation/request_for_quotation.py": ("120538bde3d8cbee44e9a71cc5e48c3493b8d13c7e9167c0703eefa30028f690", [
        ('or _("Request for Quotation")', 'or "询价单"'),
    ]),
    "buying/doctype/request_for_quotation/request_for_quotation.json": ("ed25067a5f1c1dd0eab9911874d7f3842524e296ec681356535f79f881df9634", [
        ('"default": "Please supply the specified items at the best possible rates"', '"default": "请为所列物料提供最优惠的报价。"'),
        ('"default": "Request for Quotation"', '"default": "询价单"'),
    ]),
    "selling/doctype/proforma_invoice/proforma_invoice.py": ("cc00f1625f756dbe442b1a67b05b89525cc5f23a84e4abaae871fc1072748ca5", [
        ('default_subject=_("Proforma Invoice {0}")', 'default_subject="形式发票 {0}"'),
        ('default_message=_("Please find attached the proforma invoice {0}.")', 'default_message="请查收附件中的形式发票 {0}。"'),
    ]),
    "crm/doctype/email_campaign/email_campaign.py": ("c84dc18d6a086ee8757db7add7b58e55110ff2d07647d15df9e1d53b149710ef", [
        ('unsubscribe_message=_("Unsubscribe from this campaign")', 'unsubscribe_message="退订此营销活动"'),
    ]),
    "buying/doctype/supplier_scorecard/supplier_scorecard.py": ("c578c7b2429de23da03e494d6fe45e501cadb29cc6a9ea2fc269286e42a21728", [
        ('_("Supplier Scorecard standing of {0}: {1}")', '"供应商 {0} 的评级：{1}"'),
        ('_("The Supplier Scorecard standing of {0} is now {1}.")', '"供应商 {0} 的评级现为 {1}。"'),
    ]),
    "selling/doctype/customer/customer.py": ("4fb108a4b24f3da59b1e53453577363333705182f3304fae63b9e39551451a74", [
        ('_("Credit limit reached for customer {0}")', '"客户 {0} 已达信用额度上限"'),
        ("A transaction for customer {0} is blocked by its credit limit. Current outstanding: {1}, credit limit: {2}", "客户 {0} 的交易因信用额度限制被阻止。当前未结金额为 {1}，信用额度为 {2}。"),
    ]),
    "accounts/deferred_revenue.py": ("9850269ccac4c51dbd74578d985f652438e262caa1a723748c155029ef0b41d9", [
        ('_("Error while processing deferred accounting for {0}")', '"递延会计处理失败：{0}"'),
        ('_("Deferred accounting failed for some invoices:")', '"部分发票的递延会计处理失败。"'),
        ("Please check Process Deferred Accounting {0} and submit manually after resolving errors.", "请检查递延会计处理单 {0}，解决错误后手动提交。"),
    ]),
    "assets/doctype/asset/depreciation.py": ("b96812220250251ac717dbff853a30ed8917add4128b25e6e60a3580af82f73c", [
        ('_("Error while posting depreciation entries")', '"折旧分录过账失败"'),
        ('_("Hello,")', '"您好！"'),
        ("The following assets have failed to automatically post depreciation entries: {0}", "以下资产的折旧分录自动过账失败：{0}"),
        ("Here are the error logs for the aforementioned failed depreciation entries: {0}", "相关错误日志：{0}"),
        ("Please share this email with your support team so that they can find and fix the issue.", "请将这封邮件转给支持团队，以便排查并修复问题。"),
    ]),
    "stock/doctype/repost_item_valuation/repost_item_valuation.py": ("2284d2fbd9f61ab5ccff12881fd201b0fd1c07731ba42bb0c825b9b8268bf801", [
        ('_("Error while reposting item valuation")', '"物料估值重新过账失败"'),
        ('_("Hi,")', '"您好！"'),
        ("An error has been appeared while reposting item valuation via {0}", "处理 {0} 时，物料估值重新过账失败。"),
        ("Please check the error message and take necessary actions to fix the error and then restart the reposting again.", "请检查错误信息，解决问题后重新开始过账。"),
    ]),
    "stock/doctype/stock_reposting_settings/stock_reposting_settings.py": ("8623b05900a7f38dd2a7598d8ab1a9a24af0e977704e115c9f8f14a6b23ec024", [
        ('account or _("No account set")', 'account or "未设置科目"'),
        ('_("Incorrect Stock Asset Account in {0}")', '"{0} 的库存资产科目设置有误"'),
        ("Stock and accounting values could not be reconciled by reposting for {0}.", "{0} 的库存与会计账面金额在重新过账后仍不一致。"),
        ("The warehouse account(s) below are not of type 'Stock'. Please set a correct Stock asset account on the warehouse (Account Type must be 'Stock'):", "以下仓库的科目类型有误。请在仓库中设置类型为“库存”（Stock）的库存资产科目："),
    ]),
    "setup/doctype/email_digest/email_digest.py": ("0613178e32a735cca5ef88ca0f77f81e9fdee6a51886a34775fd59d640705ab8", [
        ('_("{0} Digest").format(_(self.frequency))', '{"Daily": "每日摘要", "Weekly": "每周摘要", "Monthly": "每月摘要"}.get(self.frequency, f"{self.frequency} 摘要")'),
        ('_("Unsubscribe from this Email Digest")', '"退订此邮件摘要"'),
        ('_("Daily Reminders")', '"每日提醒"'), ('_("Pending activities for today")', '"今日待办事项"'),
        ('_("This Week\'s Summary")', '"本周摘要"'), ('_("Summary for this week and pending activities")', '"本周摘要与待办事项"'),
        ('_("This Month\'s Summary")', '"本月摘要"'), ('_("Summary for this month and pending activities")', '"本月摘要与待办事项"'),
    ]),
    "setup/doctype/email_digest/templates/default.html": ("5deb8f13c0e92905dd0c14b5dc7ff736f9113b95e121926f0b7163703ba6a978", [
        ('{{ _("Open Issues ") }}', '待处理问题'), ('{{ _("Open Projects ") }}', '进行中项目'),
        ('{{ _("Pending Activities") }}', '待办事项'), ('{{ _("Upcoming Calendar Events ") }}', '即将开始的日程'),
        ('{{ _("All Day") }}', '全天'), ('{{ _("Open To Do ") }}', '未完成待办'),
        ('{{ _("Open Notifications") }}', '待处理通知'),
        ('{{ _("Purchase Order Items not received on time") }}', '未按时收货的采购物料'),
        ('>Item Code</span>', '>物料编码</span>'), ('>Quantity</span>', '>数量</span>'),
        ('>Rate</span>', '>单价</span>'), ('>Amount</span>', '>金额</span>'),
        ('>Please take necessary action</span>', '>请及时跟进处理。</span>'),
    ]),
    "stock/doctype/delivery_trip/dispatch_notification_template.html": ("b6c304e7ac8aa799d118c5f9cb2f660da36724313400a012afd6c54194a47e9e", [
        ('>Dispatch Notification<', '>发货通知<'), ('>Details:<', '>配送详情<'),
        (">Customer's Name<", '>客户名称<'), (">Contact's Name<", '>联系人<'),
        ('>Address Name<', '>地址名称<'), ('>Address Details<', '>详细地址<'),
        ('>Order Number<', '>订单编号<'), ('>Order Total<', '>订单总额<'),
        ('>Departure Time<', '>出发时间<'), ('>Estimated Arrival<', '>预计到达时间<'),
        (">Driver's Name<", '>司机姓名<'), (">Driver's Number<", '>司机电话<'),
        ('>Vehicle Number<', '>车牌号<'),
    ]),
    "setup/setup_wizard/operations/install_fixtures.py": ("189aabd536459541e516809be2ea1e545c5cbdb8f7f22ef6a3d7dbadaf9db3a8", [
        ('"subject": _("Your order is out for delivery!")', '"subject": "您的订单已发出"'),
    ]),
    "patches/v11_0/add_default_dispatch_notification_template.py": ("0bb4e9205d2c1d5f8cf6240a1eab9a67e1a73e20642e48ad601ed5528c3282bc", [
        ('"subject": _("Your order is out for delivery!")', '"subject": "您的订单已发出"'),
    ]),
}


# Apply after the first image patch. Counts pin repeated template expressions to
# the known call sites in 16.55.0. Translate labels before report links are built.
BODY_PATCHES = {
    "projects/doctype/project_update/project_update.py": [
        ('+ str(frequency)', '+ {"Hourly": "每小时", "Twice Daily": "每天两次", "Daily": "每天", "Weekly": "每周"}'
         '.get(frequency, frequency or "")'),
    ],
    "accounts/doctype/payment_request/payment_request.py": [
        ('\n\t\t\t\tdoc.doctype,\n\t\t\t\tdoc.name,', '\n\t\t\t\t_(doc.doctype, lang="zh"),\n\t\t\t\tdoc.name,'),
    ],
    "setup/doctype/email_digest/email_digest.py": [
        ('f"email_digest:card:', 'f"email_digest:card:zh:'),
        *[(f'_(self.meta.get_label({field}))', f'_(self.meta.get_label({field}), lang="zh")', count)
          for field, count in [('"income"', 1), ('"expenses_booked"', 1), ('root_type + "_year_to_date"', 2),
                               ('"sales_orders_to_bill"', 1), ('"sales_orders_to_deliver"', 1),
                               ('"purchase_orders_to_receive"', 1), ('"purchase_orders_to_bill"', 1), ('fieldname', 7)]],
    ],
    "setup/doctype/email_digest/templates/default.html": [
        ('{{ _(t.status) }}', '{{ _(t.status, lang="zh") }}', 3),
        ('{{ _(n.key) }}', '{{ _(n.key, lang="zh") | e }}'),
        ('{{ _(t.subject) }}', '{{ t.subject | e }}'),
        ('{{ _(t.project_name) }}', '{{ t.project_name | e }}'),
        ('{{ _(t.description) }}', '{{ t.description }}'),
        ('{{ _(row.item_code) | e }}', '{{ row.item_code | e }}'),
    ],
}


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_rules(source, rules, path, *, reverse=False):
    for old, new, *counts in (reversed(rules) if reverse else rules):
        if reverse:
            old, new = new, old
        expected = counts[0] if counts else 1
        if source.count(old) != expected:
            raise ValueError(f"{path}: expected {expected} occurrence(s) of {old!r}")
        source = source.replace(old, new)
    return source


def image_changes(bench):
    root = bench / "apps/erpnext/erpnext"
    version_file = root / "__init__.py"
    versions = [node.value.value for node in ast.parse(version_file.read_bytes()).body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)]
    if versions != ["16.55.0"]:
        raise ValueError(f"Expected ERPNext 16.55.0, found {versions!r}")

    changes = {}
    for name, sha in TEMPLATES.items():
        relative = f"templates/emails/{name}.html"
        target = bench / "apps/yishan_id/yishan_id" / relative
        if not target.is_file() or not target.read_text().strip():
            raise ValueError(f"Missing Chinese template: {target}")
        include = '{% include "yishan_id/' + relative + '" %}\n'
        path = root / relative
        source = path.read_bytes().decode("utf-8")
        if source == include:
            continue
        if digest(source) != sha:
            raise ValueError(f"Unexpected upstream template: {path}")
        changes[path] = include

    for relative, (sha, rules) in PATCHES.items():
        path = root / relative
        source = path.read_bytes().decode("utf-8")
        extra = BODY_PATCHES.get(relative, ())
        if digest(source) == sha:
            first_patch = apply_rules(source, rules, path)
        else:
            first_patch = source
            if extra and extra[0][1] in source:
                first_patch = apply_rules(source, extra, path, reverse=True)
            # Both patched versions must reconstruct the exact pinned upstream file.
            if digest(apply_rules(first_patch, rules, path, reverse=True)) != sha:
                raise ValueError(f"Unexpected ERPNext source: {path}")
        updated = apply_rules(first_patch, extra, path)
        if updated != source:
            if path.suffix == ".py":
                compile(updated, str(path), "exec")
            elif path.suffix == ".json":
                json.loads(updated)
            changes[path] = updated
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bench", type=Path, nargs="?", default=Path.cwd())
    changes = image_changes(parser.parse_args().bench)
    for path, content in changes.items():
        with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            temp_path = Path(tmp.name)
            try:
                tmp.write(content.encode("utf-8"))
                tmp.flush()
                temp_path.chmod(stat.S_IMODE(path.stat().st_mode))
                temp_path.replace(path)
            finally:
                temp_path.unlink(missing_ok=True)
    print(f"ERPNext 16.55.0 mail localization: {len(changes)} files updated")


if __name__ == "__main__":
    main()
