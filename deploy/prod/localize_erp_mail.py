"""ERPNext 16.55.0 standard Notification defaults. Run from the bench directory.

Image build: env/bin/python /tmp/localize_erp_mail.py --image
Existing site, once on that image: env/bin/python /tmp/localize_erp_mail.py --site SITE
No reload-doc, migration or mail delivery is involved.
"""

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Notification:
    module: str
    name: str
    body_sha256: str
    original_subject: str
    subject: str
    body: str
    previous_body_sha256: str | None = None

    def folder(self, root):
        slug = self.name.lower().replace(" ", "_")
        return root / self.module.lower() / "notification" / slug


DEFAULTS = (
    Notification(
        "Manufacturing",
        "Material Request Receipt Notification",
        "1a0dc61c2da1c16b2ad912c67716e25e9ddcfa9f974e758beda325530158297c",
        "{{ doc.name }} has been received",
        "物料需求单 {{ doc.name }} 收货通知",
        """<p><b>物料需求类型</b>：{{ {'Purchase': '采购', 'Material Transfer': '物料调拨', 'Material Issue': '物料领用', 'Manufacture': '生产', 'Subcontracting': '委外加工', 'Customer Provided': '客户供料'}.get(doc.material_request_type, doc.material_request_type) | e }}<br>
<b>公司</b>：{{ doc.company | e }}</p>
<h3>收货明细</h3>
<table border="2">
    <tr><th>物料编码</th><th>已收数量</th></tr>
    {% for item in doc.items %}
        {% if frappe.utils.flt(item.received_qty, 2) > 0.0 %}
            <tr><td>{{ item.item_code | e }}</td><td>{{ frappe.utils.flt(item.received_qty, 2) }}</td></tr>
        {% endif %}
    {% endfor %}
</table>
""",
        previous_body_sha256="0e7011fb64d4171ce4af886692526366833c1f11261b1dd0515f05eb46a309a4",
    ),
    Notification(
        "Accounts",
        "Notification for new fiscal year",
        "664379c36b9e90b8777c61adfeea5ec78245cddc407053f1beaeb8e58a969df1",
        "New Fiscal Year {{ doc.name }} - Review Required",
        "请核对新会计年度 {{ doc.name }} 的设置",
        """<h4>新会计年度：{{ doc.name | e }}</h4>
<p>系统已自动创建新的会计年度。</p>
<p>会计年度详情</p>
<table style="margin-bottom: 1rem; width: 70%">
    <tr><th>年度名称</th><td>{{ doc.name | e }}</td></tr>
    <tr><th>开始日期</th><td>{{ frappe.format_value(doc.year_start_date) }}</td></tr>
    <tr><th>结束日期</th><td>{{ frappe.format_value(doc.year_end_date) }}</td></tr>
    {% for company in doc.companies %}
    <tr>
        {% if loop.first %}<th rowspan="{{ doc.companies | length }}">公司</th>{% endif %}
        <td>{{ company.company | e }}</td>
    </tr>
    {% endfor %}
</table>
{% if doc.disabled %}
<p>为与上一会计年度的状态一致，新会计年度已设为停用。</p>
{% endif %}
<p>请核对{{ frappe.utils.get_link_to_form("Fiscal Year", doc.name, frappe.bold("会计年度")) }}的设置，并完成所需的财务配置。</p>
""",
    ),
)


def is_original_body(text, spec):
    return text is not None and hashlib.sha256(text.encode()).hexdigest() in (
        spec.body_sha256, spec.previous_body_sha256,
    )


def image_changes(root):
    changes = {}
    for spec in DEFAULTS:
        folder = spec.folder(root)
        html_path = folder / (folder.name + ".html")
        json_path = html_path.with_suffix(".json")
        html = html_path.read_text()
        record = json.loads(json_path.read_text())
        identity = ("doctype", "name", "module", "channel", "message_type", "is_standard")
        expected = ("Notification", spec.name, spec.module, "Email", "HTML", 1)
        if tuple(record[key] for key in identity) != expected:
            raise ValueError(f"Unexpected standard Notification in {json_path}")
        for text in (html, record["message"]):
            if text != spec.body and not is_original_body(text, spec):
                raise ValueError(f"Unexpected body for {spec.name}")
        if record["subject"] not in (spec.original_subject, spec.subject):
            raise ValueError(f"Unexpected subject for {spec.name}")
        if html != spec.body:
            changes[html_path] = spec.body
        if (record["subject"], record["message"]) != (spec.subject, spec.body):
            record.update(subject=spec.subject, message=spec.body)
            changes[json_path] = json.dumps(record, ensure_ascii=False, indent=1) + "\n"
    return changes


def sync_site(site):
    import frappe
    from frappe.email.doctype.notification.notification import clear_notification_cache

    os.chdir("sites")
    frappe.init(site=site)
    try:
        frappe.connect()
        if "erpnext" not in frappe.get_installed_apps():
            raise ValueError(f"ERPNext is not installed on {site}")
        for spec in DEFAULTS:
            filters = dict(
                name=spec.name, module=spec.module, is_standard=1, channel="Email", message_type="HTML"
            )
            row = frappe.db.get_value(
                "Notification", filters, ["subject", "message", "email_template"],
                as_dict=True, for_update=True,
            )
            updates = {}
            if row and not row.email_template:
                if row.subject == spec.original_subject:
                    updates["subject"] = spec.subject
                if is_original_body(row.message, spec):
                    updates["message"] = spec.body
            if updates:
                frappe.db.set_value("Notification", spec.name, updates, update_modified=False)
            print(f"{spec.name}: {', '.join(updates) or 'no matching defaults to update'}")
        frappe.db.after_commit.add(clear_notification_cache)
        frappe.db.commit()
    finally:
        frappe.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--image", action="store_true")
    mode.add_argument("--site", metavar="SITE")
    args = parser.parse_args()
    import erpnext

    if erpnext.__version__ != "16.55.0":
        parser.error(f"Expected ERPNext 16.55.0, found {erpnext.__version__}")
    changes = image_changes(Path(erpnext.__file__).resolve().parent)
    if args.site:
        if changes:
            parser.error("Run --image in the incremental image build before --site")
        sync_site(args.site)
    else:
        for path, text in changes.items():
            path.write_text(text)
            print(path)


if __name__ == "__main__":
    main()
