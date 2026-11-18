"""真实 Cookie/token 和原生接口验收；详细结果不离开本机。"""
import http.cookiejar
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

import bootstrap as infra
from site_ops import execute
from state import change

BASE = "http://127.0.0.1:8081"
METHOD = "/api/method/bizbase.api.directory."


class Client:
    def __init__(self, account, token=False):
        self.account = account
        self.headers = {"Accept": "application/json"}
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        if token:
            self.headers["Authorization"] = "token " + account["api_key"] + ":" + account["api_secret"]
        else:
            status, _ = self.call("/api/method/login", {"usr": account["user"], "pwd": account["password"]}, post=True)
            assert status == 200, "Ordinary person login failed"

    def call(self, path, params=None, post=False):
        params = params or {}
        data = urllib.parse.urlencode(params).encode() if post else None
        url = BASE + path + ("?" + urllib.parse.urlencode(params) if params and not post else "")
        req = urllib.request.Request(url, data=data, headers=self.headers)
        try:
            response = self.opener.open(req, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read().decode()
            try:
                body = json.loads(raw)
            except ValueError:
                body = {"non_json": True}
            return response.status, body

    def directory(self, method="list_customers", **params):
        return self.call(METHOD + method, params)


def verify():
    credentials = json.loads((infra.PRIVATE / "credentials.json").read_text())
    snapshot = json.loads((infra.PRIVATE / "snapshot-s01.json").read_text())
    accounts = credentials["accounts"]
    person = Client(accounts["reader"])
    machine = Client(accounts["client"], token=True)
    none = Client(accounts["no-grant"], token=True)
    parent = Client(accounts["parent-reader"], token=True)
    params = {"source_system": snapshot["source_system"], "customer_id": credentials["delivery_id"]}
    checks = []
    request_ids = []

    def expect(client, method, status=200, **values):
        actual, body = client.directory(method, **values)
        assert actual == status, f"{method}: expected {status}, received {actual}"
        result = body.get("message", {})
        request_id = result.get("meta", {}).get("request_id") or result.get("error", {}).get("request_id")
        if request_id:
            request_ids.append(request_id)
        for forbidden in ("/run/bizbase-directory", "Traceback", "api_secret", "password", "parent_id", "registeredCustomerId"):
            assert forbidden not in json.dumps(body), f"Response leaked forbidden field: {forbidden}"
        return result

    for client in (person, machine):
        customers = expect(client, "list_customers")
        assert [row["customer_id"] for row in customers["items"]] == [credentials["delivery_id"]]
        assert set(customers) == {"items", "meta"}
        assert set(customers["items"][0]) == {"customer_id", "name"}
    first = expect(person, "list_subjects", **params)
    second = expect(machine, "list_subjects", **params)
    expected = [s for s in snapshot["subjects"] if s["customer_id"] == params["customer_id"]]
    assert first["items"] == second["items"] == expected
    assert first["meta"]["version"] == second["meta"]["version"]
    assert first["meta"]["data_as_of"] == "2026-11-02"
    assert set(first) == {"items", "meta", "customer"}
    assert set(first["meta"]) == {"mode", "source_system", "version", "data_as_of", "request_id"}
    cli = subprocess.run([sys.executable, str(infra.ROOT / "scripts/directory/consumer.py"), "--credentials", str(infra.PRIVATE / "client.json")], capture_output=True, text=True)
    assert cli.returncode == 0, "Independent consumer failed"
    cli_data = json.loads(cli.stdout)
    assert cli_data["items"] == expected and cli_data["meta"]["version"] == first["meta"]["version"]
    infra.private_write(infra.PRIVATE / "evidence/consumer.json", json.dumps(cli_data, ensure_ascii=False, indent=2))
    checks += ["A1/A2 real Cookie and independent machine consumer agree", "A3 ordinary users", "D6 field whitelist"]
    assert expect(person, "list_customers", query="round01-unmatched-query-947159")["items"] == []
    checks.append("B2 real unmatched query")
    expect(none, "list_customers", 403)
    denied = expect(none, "list_subjects", 404, **params)
    absent = expect(none, "list_subjects", 404, **{**params, "customer_id": "does-not-exist"})
    assert denied["error"]["code"] == absent["error"]["code"]
    expect(parent, "list_subjects", 404, **params)
    checks += ["D1 default deny and indistinguishable absent", "D2 no parent inheritance"]
    for actor, client in (("reader", person), ("client", machine)):
        try:
            change("grant", False, actor)
            expect(client, "list_customers", 403)
            expect(client, "list_subjects", 404, **params)
        finally:
            change("grant", True, actor)
        expect(client, "list_subjects", **params)
    checks.append("D3 committed grant revocation rejects existing Cookie and token")
    for kind in ("membership", "account", "role"):
        for actor, client in (("reader", person), ("client", machine)):
            try:
                change(kind, False, actor)
                status, _ = client.directory("list_customers")
                assert status in (401, 403), f"{kind} did not deny {actor}"
            finally:
                change(kind, True, actor)
        # User.save 可能作废会话；恢复后重新登录，禁止把失效会话当权限缺陷。
        person = Client(accounts["reader"])
        expect(person, "list_subjects", **params)
        expect(machine, "list_subjects", **params)
    checks.append("D4 user, membership and Role disabled")
    for key in ("actor", "user", "filename", "unexpected"):
        expect(person, "list_customers", 400, **{key: "Administrator"})
    checks.append("C4 unsupported inputs rejected")
    ref = credentials["references"][params["customer_id"]]
    native = [
        ("/api/resource/BB%20Customer%20Reference", {}),
        ("/api/resource/BB%20Customer%20Reference/" + urllib.parse.quote(ref), {}),
        ("/api/method/frappe.client.get", {"doctype": "BB Customer Reference", "name": ref}),
        ("/api/method/frappe.client.get_list", {"doctype": "BB Customer Reference"}),
        ("/api/method/frappe.desk.search.search_link", {"doctype": "BB Customer Reference", "txt": ""}),
        ("/api/method/frappe.core.doctype.data_export.exporter.export_data", {"doctype": "BB Customer Reference", "export_fields": json.dumps({"BB Customer Reference": ["name", "display_name"]}), "export_records": "all", "file_type": "CSV"}),
        ("/api/resource/Integration%20Request", {}),
        ("/api/resource/Permission%20Log", {}),
        ("/api/resource/DefaultValue", {}),
        ("/files/snapshot-s01.json", {}),
        ("/private/files/snapshot-s01.json", {}),
    ]
    for path, values in native:
        status, body = person.call(path, values)
        assert status in (400, 401, 403, 404, 405, 417), f"Native path allowed: {path} ({status})"
        serialized = json.dumps(body, ensure_ascii=False)
        assert all(row["name"] not in serialized for row in snapshot["customers"] + snapshot["subjects"]), "Native response leaked data"
    checks.append("D5/D9 native resources, methods, search, export, logs and private files denied")
    bad = Client({**accounts["client"], "api_secret": "deliberately-invalid"}, token=True)
    auth_probe = uuid4().hex
    auth_status, auth_body = bad.directory(authentication_probe=auth_probe)
    assert auth_status in (401, 403)
    frontend = infra.compose("ps", "-q", "frontend", capture=True).strip()
    access = subprocess.run(["docker", "logs", "--since", "2m", frontend], capture_output=True, text=True)
    auth_lines = [line for line in (access.stdout + access.stderr).splitlines() if auth_probe in line]
    assert auth_lines and any(f" {auth_status} " in line for line in auth_lines), "Authentication rejection absent from framework access log"
    infra.private_write(infra.PRIVATE / "evidence/authentication.json", json.dumps({"status": auth_status, "exception_type": auth_body.get("exc_type"), "access_lines": auth_lines}, indent=2))
    checks.append("D8 framework authentication rejects invalid credential")
    try:
        change("directory", False)
        expect(person, "list_customers", 503)
        expect(machine, "list_subjects", 503, **params)
    finally:
        change("directory", True)
    expect(person, "list_subjects", **params)
    checks.append("F1 kill switch and recovery")
    audit = execute('''
rows=frappe.get_all("Integration Request",filters={"request_id":["in",payload["ids"]]},fields=["request_id","data","status"])
permissions=frappe.db.count("Permission Log",{"for_doctype":"User Permission"})
settings=frappe.get_doc("Log Settings").as_dict()
result={"audit_request_ids":[r.request_id for r in rows],"audit_rows":[{"status":r.status,"data":r.data} for r in rows],"permission_logs":permissions,"log_settings":settings}
''', {"ids": request_ids})
    assert set(request_ids).issubset(set(audit["audit_request_ids"])), "Business audit was not persisted"
    assert audit["permission_logs"] > 0, "Permission changes lack native logs"
    checks.append("D7/D9 business audit persisted and native permission logs present")
    infra.private_write(infra.PRIVATE / "evidence/http.json", json.dumps({"passed": True, "checks": checks, "request_ids": request_ids, "audit": audit}, ensure_ascii=False, indent=2))
    print(f"HTTP: {len(checks)} check groups passed")
    return checks


if __name__ == "__main__":
    verify()
