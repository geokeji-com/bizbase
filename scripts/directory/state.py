#!/usr/bin/env python3
"""隔离验收状态操作；固定账号及资源范围，无网络入口。"""
import argparse
import json

import bootstrap as infra
from site_ops import execute, set_grant


def change(kind, enabled, actor="reader"):
    credentials = json.loads((infra.PRIVATE / "credentials.json").read_text())
    if actor not in ("reader", "client"):
        raise ValueError("Only isolated reader/client may be changed")
    user = credentials["accounts"][actor]["user"]
    if kind == "grant":
        return set_grant(user, credentials["references"][credentials["delivery_id"]], enabled)
    return execute('''
kind=payload["kind"]
if kind=="account":
    frappe.db.set_value("User",payload["user"],"enabled",int(payload["enabled"]))
elif kind=="membership":
    doc=frappe.get_doc("User",payload["user"])
    doc.set("roles",[{"role":"BB Directory Reader"}] if payload["enabled"] else [])
    doc.save(ignore_permissions=True)
elif kind=="role":
    frappe.db.set_value("Role","BB Directory Reader","disabled",int(not payload["enabled"]))
elif kind=="directory":
    from bizbase.directory.service import set_enabled
    set_enabled(payload["enabled"])
else:
    raise ValueError("Unknown isolated test operation")
frappe.db.commit()
result={"kind":kind,"enabled":payload["enabled"]}
''', {"kind": kind, "enabled": enabled, "user": user})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["grant", "account", "membership", "role", "directory"])
    parser.add_argument("value", choices=["on", "off"])
    parser.add_argument("--actor", default="reader", choices=["reader", "client"])
    args = parser.parse_args()
    print(json.dumps(change(args.kind, args.value == "on", args.actor)))
