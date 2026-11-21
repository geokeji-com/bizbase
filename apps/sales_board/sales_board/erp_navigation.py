"""GEO sales navigation. Only reshape the Desk payload, never grants or records."""

SALES_LINKS = ("Lead", "Opportunity", "Customer", "Contact", "Sales Partner", "Contract")
GROUPS = (
    ("sales-settings", "销售设置", "Sales Settings", "settings", (
        ("DocType", "Selling Settings"), ("DocType", "UTM Source"),
        ("DocType", "Sales Stage"), ("DocType", "Customer Group"),
    )),
    ("sales-analysis", "销售分析", "Sales Analysis", "chart-column", (
        ("Report", "Opportunity Summary by Sales Stage"), ("Page", "sales-funnel"),
    )),
)
COLLAPSED = {"CRM", "Buying", "Stock", "Manufacturing", "Assets"}


def apply(bootinfo):
    sidebars = bootinfo.get("module_sidebars") or {}
    selling = sidebars.get("Selling")
    if not selling or selling.get("app") != "erpnext":
        return
    app = next((a for a in bootinfo.get("app_data", []) if a.get("app_name") == "erpnext"), None)
    if not app:
        return
    # Reuse only entries present in this user's resolved native sidebars.
    available = [*selling.get("items", []), *sidebars.get("CRM", {}).get("items", [])]
    quick = []
    for name in SALES_LINKS:
        item = next((i for i in available if i.get("link_type") == "DocType" and i.get("link_to") == name), None)
        if name == "Sales Partner":
            if name not in (bootinfo.get("user") or {}).get("can_read", []):
                continue
            item = dict(key="Link|DocType|Sales Partner||", type="Link", link_type="DocType",
                        link_to=name, icon="handshake", label="销售伙伴" if (bootinfo.get("lang") or "").startswith("zh") else name)
        if item:
            quick.append(dict(item, child=0, indent=0, keep_closed=0))
            bootinfo.setdefault("entity_module", {})[name] = "Selling"
            bootinfo.setdefault("canonical_shell", {}).setdefault("DocType", {})[name] = "Selling"
    if not quick:
        return
    zh = (bootinfo.get("lang") or "").startswith("zh")
    for key, zh_label, en_label, icon, links in GROUPS:
        children = []
        for kind, name in links:
            item = next((i for i in available if i.get("link_type") == kind and i.get("link_to") == name), None)
            if item:
                child = dict(item, child=1, indent=0)
                if name == "Selling Settings":
                    child["label"] = "销售设置" if zh else "Selling Settings"
                children.append(child)
        if children:
            quick.append(dict(key=key, type="Section Break", label=zh_label if zh else en_label,
                              icon=icon, child=0, indent=1, collapsible=1, keep_closed=1))
            quick.extend(children)
    selling["items"] = quick
    if app.get("app_route") == "/desk/crm":
        app["app_route"] = "/desk/selling"
    dock = bootinfo.setdefault("dock", {})
    rows = dock.get("erpnext", app.get("dock") or [])
    dock["erpnext"] = sorted([
        dict(r, hidden=1) if r.get("link_type") == "Sidebar" and r.get("link_to") in COLLAPSED else r
        for r in rows
    ], key=lambda r: {"Setup": 0, "Selling": 1, "Accounts": 2}.get(r.get("link_to"), 3)
       if r.get("link_type") == "Sidebar" else 3)
