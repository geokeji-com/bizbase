"""仅用于本轮隔离站点的命令行配置与验收；不注册任何网络方法。"""
import json
import subprocess

import bootstrap as infra


def execute(code: str, payload=None):
    infra.load_env()
    infra.validate_config()
    container = infra.compose("ps", "-q", "backend", capture=True).strip()
    details = json.loads(infra.run(["docker", "inspect", container], capture=True))[0]
    if details["Config"]["Labels"].get("com.docker.compose.project") != infra.PROJECT:
        raise SystemExit("Refusing to operate outside bizbase-r01")
    wrapper = '''import json,sys,os,frappe
payload=json.load(sys.stdin)
os.chdir("/home/frappe/frappe-bench/sites")
frappe.init(site="bizbase-acceptance.localhost",sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
try:
    exec(compile(%r,"<isolated-round01-operation>","exec"))
    print("__BIZBASE_RESULT__"+json.dumps(result,ensure_ascii=False,default=str))
finally:
    frappe.destroy()
''' % code
    process = subprocess.run(["docker", "exec", "-i", container, "env/bin/python", "-c", wrapper], input=json.dumps(payload or {}), text=True, capture_output=True)
    if process.returncode:
        # traceback 可能包含私有值，仅保存本机，不回显 stdout 或凭据。
        infra.private_write(infra.PRIVATE / "last-site-operation-error.txt", process.stderr)
        raise RuntimeError("Isolated site operation failed; inspect private last-site-operation-error.txt")
    marker = "__BIZBASE_RESULT__"
    lines = [line[len(marker):] for line in process.stdout.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise RuntimeError("Site operation did not return its structured result")
    return json.loads(lines[0])


def set_grant(user: str, reference: str, enabled: bool):
    return execute('''
assert payload["user"] in {"reader@bizbase.invalid","client@bizbase.invalid","parent-reader@bizbase.invalid","no-grant@bizbase.invalid"}
filters={"user":payload["user"],"allow":"BB Customer Reference","for_value":payload["reference"]}
rows=frappe.get_all("User Permission",filters=filters,pluck="name")
if payload["enabled"] and not rows:
    frappe.get_doc({"doctype":"User Permission",**filters,"apply_to_all_doctypes":1}).insert(ignore_permissions=True)
if not payload["enabled"]:
    for name in rows:
        frappe.delete_doc("User Permission",name,ignore_permissions=True)
frappe.db.commit()
result={"enabled":payload["enabled"]}
''', {"user": user, "reference": reference, "enabled": enabled})


def directory_fingerprint():
    return execute('''
import hashlib
users=["reader@bizbase.invalid","client@bizbase.invalid","parent-reader@bizbase.invalid","no-grant@bizbase.invalid"]
state=frappe.db.get_value("DefaultValue",{"parent":"__global","defkey":"bizbase_directory_state"},"defvalue")
facts={"state":json.loads(state),"role_disabled":frappe.db.get_value("Role","BB Directory Reader","disabled"),
"desk_setup":frappe.get_all("Installed Application",filters={"app_name":["in",["frappe","erpnext"]]},fields=["app_name","is_setup_complete"],order_by="app_name"),
"users":frappe.get_all("User",filters={"name":["in",users]},fields=["name","enabled","api_key"],order_by="name"),
"roles":frappe.get_all("Has Role",filters={"parent":["in",users],"parenttype":"User"},fields=["parent","role"],order_by="parent,role"),
"grants":frappe.get_all("User Permission",filters={"user":["in",users],"allow":"BB Customer Reference"},fields=["user","allow","for_value","apply_to_all_doctypes","applicable_for"],order_by="user,for_value"),
"refs":frappe.get_all("BB Customer Reference",fields=["name","source_system","source_customer_id","display_name"],order_by="name")}
result=hashlib.sha256(json.dumps(facts,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
''')
