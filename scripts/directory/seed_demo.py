#!/usr/bin/env python3
"""初始化独立测试身份，凭据仅写本机私有文件；不更改旧站点。"""
import json
import secrets

import bootstrap as infra
from site_ops import execute


def seed():
    snapshot = json.loads((infra.PRIVATE / "snapshot-s01.json").read_text())
    delivery_id = snapshot["subjects"][0]["customer_id"]
    parent_id = next(c["customer_id"] for c in snapshot["customers"] if c["customer_id"] != delivery_id)
    credential_file = infra.PRIVATE / "credentials.json"
    existing = json.loads(credential_file.read_text()).get("accounts", {}) if credential_file.exists() else {}
    accounts = {}
    for kind in ("reader", "client", "parent-reader", "no-grant"):
        accounts[kind] = existing.get(kind) or {"user": f"{kind}@bizbase.invalid", "password": secrets.token_urlsafe(30), "api_key": secrets.token_hex(10), "api_secret": secrets.token_urlsafe(30)}
        assert accounts[kind]["user"] == f"{kind}@bizbase.invalid"
    result = execute('''
from frappe.utils.password import update_password
from bizbase.directory.service import activate
activate("snapshot-s01.json",payload["sha256"])
references={row.source_customer_id:row.name for row in frappe.get_all("BB Customer Reference",filters={"source_system":payload["source"]},fields=["name","source_customer_id"])}
for kind,account in payload["accounts"].items():
    email=account["user"]
    doc=frappe.get_doc("User",email) if frappe.db.exists("User",email) else frappe.new_doc("User")
    doc.update({"email":email,"first_name":"目录验收 " + kind,"enabled":1,"user_type":"System User","language":"zh","send_welcome_email":0,"api_key":account["api_key"],"api_secret":account["api_secret"]})
    doc.set("roles",[{"role":"BB Directory Reader"}])
    doc.save(ignore_permissions=True)
    update_password(email,account["password"],logout_all_sessions=True)
    for permission in frappe.get_all("User Permission",filters={"user":email,"allow":"BB Customer Reference"},pluck="name"):
        frappe.delete_doc("User Permission",permission,ignore_permissions=True)
    customer=payload["parent"] if kind=="parent-reader" else payload["delivery"]
    if kind!="no-grant":
        frappe.get_doc({"doctype":"User Permission","user":email,"allow":"BB Customer Reference","for_value":references[customer],"apply_to_all_doctypes":1}).insert(ignore_permissions=True)
# Frappe 16 的 Desk 门槛读取 Installed Application；此隔离目录站点跳过
# ERP 初次设置向导，不创建财务公司，不能据此宣称 ERP 经营配置已完成。
for app in ("frappe","erpnext"):
    frappe.db.set_value("Installed Application",{"app_name":app},"is_setup_complete",1)
frappe.db.commit()
frappe.clear_cache()
result={"references":references,"roles":{kind:frappe.get_all("Has Role",filters={"parent":account["user"],"parenttype":"User"},pluck="role") for kind,account in payload["accounts"].items()}}
''', {"sha256": "bf4aadc135bccab60529a68e99a0df451290fcf0c87effa311958d4530ea7124", "source": snapshot["source_system"], "delivery": delivery_id, "parent": parent_id, "accounts": accounts})
    for roles in result["roles"].values():
        if "System Manager" in roles or "BB Directory Reader" not in roles:
            raise RuntimeError("Seeded account has unexpected roles")
    document = {"base_url": "http://127.0.0.1:8081", "accounts": accounts, "references": result["references"], "delivery_id": delivery_id, "parent_id": parent_id}
    infra.private_write(infra.PRIVATE / "credentials.json", json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    infra.private_write(infra.PRIVATE / "client.json", json.dumps({"base_url": document["base_url"], **accounts["client"]}, indent=2) + "\n")
    infra.private_write(infra.PRIVATE / "login.txt", "本地客户目录：http://127.0.0.1:8081/desk/bb-directory\n人员账号：" + accounts["reader"]["user"] + "\n密码：" + accounts["reader"]["password"] + "\n本文件仅供本地验收；不要复制到 Git 或共享文档。\n")
    print("Seeded four isolated ordinary accounts; credentials saved privately")
    return document


if __name__ == "__main__":
    seed()
