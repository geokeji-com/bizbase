"""真实 Frappe DB/权限测试；不读取真实快照，审计提交后显式清理。

运行：bench --site bizbase-acceptance.localhost run-tests --module bizbase.tests.test_directory
每次调用使用独立连接与认证身份；HTTP 凭证及页面验收由外部测试另行覆盖。
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from uuid import uuid4

import frappe

from bizbase.api import directory as api
from bizbase.directory import audit, policy, service, snapshot
from bizbase.directory.errors import DirectoryError


SITE = "bizbase-acceptance.localhost"
ROLE = "BB Directory Reader"
REFERENCE = "BB Customer Reference"


class TestDirectory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if frappe.local.site != SITE:
            raise unittest.SkipTest("真实 DB 集成测试仅允许 bizbase-acceptance.localhost")
        cls.sites_path = str(Path(frappe.local.sites_path).resolve())
        cls.original_user = frappe.session.user
        cls.state_name, _ = service._read_state()
        cls.original_state = frappe.db.get_value("DefaultValue", cls.state_name, "defvalue")
        cls.original_disabled = frappe.db.get_value("Role", ROLE, "disabled")
        cls.token = uuid4().hex[:12]
        cls.source = "synthetic-integration-" + cls.token
        cls.users = {name: f"bb-dir-{cls.token}-{name}@example.invalid" for name in
                     ("reader", "client", "parent", "no-grant", "foreign-scope", "no-role", "manager")}
        cls.request_ids = set()
        cls.permission_ids = set()
        cls.reference_ids = set()
        cls.temp = tempfile.TemporaryDirectory(prefix="bb-directory-integration-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.root_patch = patch.object(snapshot, "SNAPSHOT_ROOT", str(cls.root))
        cls.root_patch.start()
        cls.addClassCleanup(cls.root_patch.stop)
        # 即使创建夹具失败也恢复状态；从不依赖 test runner 的 rollback。
        cls.addClassCleanup(cls.cleanup_database)
        frappe.set_user("Administrator")
        frappe.db.set_value("Role", ROLE, "disabled", 0, update_modified=False)
        for name, email in cls.users.items():
            roles = ["System Manager"] if name == "manager" else ([] if name == "no-role" else [ROLE])
            frappe.get_doc({"doctype": "User", "email": email, "first_name": "合成验收 " + name,
                            "enabled": 1, "send_welcome_email": 0,
                            "roles": [{"role": role} for role in roles]}).insert(ignore_permissions=True)
        frappe.db.commit()
        cls.v1 = {"schema_version": 1, "source_system": cls.source, "data_as_of": "2026-11-02",
                  "customers": [{"customer_id": key, "name": name} for key, name in
                                (("parent", "合成父客户"), ("delivery", "合成交付客户 V1"), ("empty", "合成零对象客户"))],
                  "subjects": [{"subject_id": "subject-v1", "customer_id": "delivery", "name": "合成对象 V1", "source_type": None}]}
        cls.v2 = deepcopy(cls.v1)
        cls.v2["customers"][1]["name"] = "合成交付客户 V2"
        cls.v2["customers"].append({"customer_id": "new-v2", "name": "合成新增客户 V2"})
        cls.v2["subjects"] = [{"subject_id": "subject-v2", "customer_id": "delivery", "name": "合成对象 V2", "source_type": "synthetic"}]
        cls.files = {}
        for version, data in (("v1", cls.v1), ("v2", cls.v2)):
            raw = json.dumps(data, ensure_ascii=False).encode()
            filename = version + ".json"
            (cls.root / filename).write_bytes(raw)
            cls.files[version] = (filename, hashlib.sha256(raw).hexdigest())

    @classmethod
    def cleanup_database(cls):
        frappe.db.rollback()
        frappe.set_user("Administrator")
        try:
            frappe.db.set_value("DefaultValue", cls.state_name, "defvalue", cls.original_state, update_modified=False)
            frappe.db.set_value("Role", ROLE, "disabled", cls.original_disabled, update_modified=False)
            # 先恢复可见状态并提交，即使后续清理异常也不留下合成目录指针。
            frappe.db.commit()
            cls.reference_ids.update(frappe.get_all(REFERENCE, filters={"source_system": cls.source}, pluck="name"))
            refs = list(cls.reference_ids)
            users = list(cls.users.values())
            cls.permission_ids.update(frappe.get_all("User Permission", filters={"user": ["in", users]}, pluck="name"))
            for doctype in ("Integration Request", "Access Log", "Activity Log"):
                frappe.db.delete(doctype, {"owner": ["in", users]})
            if cls.request_ids:
                frappe.db.delete("Integration Request", {"request_id": ["in", list(cls.request_ids)]})
            frappe.db.delete("User Permission", {"user": ["in", users]})
            if refs:
                frappe.db.delete("DocShare", {"share_doctype": REFERENCE, "share_name": ["in", refs]})
                frappe.db.delete("Version", {"ref_doctype": REFERENCE, "docname": ["in", refs]})
                frappe.db.delete("Comment", {"reference_doctype": REFERENCE, "reference_name": ["in", refs]})
                frappe.db.delete(REFERENCE, {"source_system": cls.source})
            for email in users:
                if frappe.db.exists("User", email):
                    frappe.delete_doc("User", email, ignore_permissions=True, force=True, delete_permanently=True)
            for doctype, names in (("User", users), ("User Permission", list(cls.permission_ids)), (REFERENCE, refs)):
                if names:
                    frappe.db.delete("Permission Log", {"reference_type": doctype, "reference": ["in", names]})
                    frappe.db.delete("Permission Log", {"for_doctype": doctype, "for_document": ["in", names]})
                    frappe.db.delete("Version", {"ref_doctype": doctype, "docname": ["in", names]})
                    frappe.db.delete("Comment", {"reference_doctype": doctype, "reference_name": ["in", names]})
            frappe.db.commit()
            assert not frappe.db.exists(REFERENCE, {"source_system": cls.source})
            assert not frappe.db.exists("User", {"name": ["in", users]})
            assert frappe.db.get_value("DefaultValue", cls.state_name, "defvalue") == cls.original_state
        finally:
            frappe.set_user(cls.original_user)

    @classmethod
    def request(cls, identity, function, *args, **kwargs):
        """调用者必须在独立线程中运行；真实权限查询、事务及审计均不替换。"""
        frappe.init(site=SITE, sites_path=cls.sites_path)
        frappe.connect()
        try:
            frappe.flags.in_test = True
            user = cls.users.get(identity, identity)
            frappe.set_user(user)
            frappe.local.form_dict = frappe._dict()
            frappe.local.response = frappe._dict()
            # 刻意预热原生缓存，直接 SQL 撤权仍必须对后续请求生效。
            frappe.get_roles(user)
            frappe.permissions.get_user_permissions(user)
            result = function(*args, **kwargs)
            if isinstance(result, dict):
                request_id = result.get("request_id") or result.get("meta", {}).get("request_id") or result.get("error", {}).get("request_id")
                if request_id:
                    cls.request_ids.add(request_id)
            return result, frappe.local.response.get("http_status_code", 200)
        finally:
            frappe.db.rollback()
            frappe.destroy()

    def call(self, identity, function, *args, **kwargs):
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(self.request, identity, function, *args, **kwargs).result(timeout=30)

    def setUp(self):
        frappe.db.rollback()
        frappe.set_user("Administrator")
        frappe.db.set_value("Role", ROLE, "disabled", 0, update_modified=False)
        for identity, email in self.users.items():
            frappe.db.set_value("User", email, "enabled", 1, update_modified=False)
            if identity not in ("manager", "no-role") and not frappe.db.exists("Has Role", {"parent": email, "role": ROLE}):
                doc = frappe.get_doc("User", email)
                doc.append("roles", {"role": ROLE})
                doc.save(ignore_permissions=True)
        frappe.db.delete("User Permission", {"user": ["in", list(self.users.values())]})
        # V2 用于验证新增引用的原子性，每个场景都从尚未存在该引用的 V1 开始。
        self.reference_ids.update(frappe.get_all(REFERENCE, filters={"source_system": self.source}, pluck="name"))
        frappe.db.delete(REFERENCE, {"source_system": self.source, "source_customer_id": "new-v2"})
        frappe.db.commit()
        self.call("manager", service.activate, *self.files["v1"])
        self.refs = {row.source_customer_id: row.name for row in frappe.get_all(REFERENCE, filters={"source_system": self.source}, fields=["name", "source_customer_id"])}
        self.reference_ids.update(self.refs.values())
        for identity, customer in (("reader", "delivery"), ("reader", "empty"), ("client", "delivery"), ("parent", "parent"), ("no-role", "delivery")):
            self.grant(identity, customer)
        self.grant("foreign-scope", "delivery", applicable_for="ToDo", apply_to_all_doctypes=0)
        frappe.db.commit()

    def grant(self, identity, customer, **scope):
        doc = frappe.get_doc({"doctype": "User Permission", "user": self.users[identity], "allow": REFERENCE,
                              "for_value": self.refs[customer], "apply_to_all_doctypes": 1, **scope}).insert(ignore_permissions=True)
        self.permission_ids.add(doc.name)
        return doc.name

    def subjects(self, identity="reader", customer="delivery", **kwargs):
        return self.call(identity, api.list_subjects, self.source, customer, **kwargs)

    def assert_error(self, response, code, status):
        data, actual_status = response
        self.assertEqual(actual_status, status)
        self.assertEqual(set(data), {"error"})
        self.assertEqual(set(data["error"]), {"code", "message", "request_id"})
        self.assertEqual(data["error"]["code"], code)
        self.assertEqual(len(data["error"]["request_id"]), 32)

    def test_a3_readers_need_only_directory_role_and_explicit_grant(self):
        for identity in ("reader", "client"):
            self.assertFalse(frappe.db.exists("Has Role", {"parent": self.users[identity], "role": "System Manager"}))
            data, status = self.subjects(identity)
            self.assertEqual(status, 200)
            self.assertEqual(data["items"], self.v1["subjects"])
            self.assertEqual(data["meta"]["version"], self.files["v1"][1])
            self.assertEqual(data["meta"]["mode"], "snapshot")
            self.assertEqual(data["meta"]["data_as_of"], "2026-11-02")

    def test_a4_reactivate_same_digest_keeps_reference_identity(self):
        before = dict(self.refs)
        first, _ = self.call("manager", service.activate, *self.files["v1"])
        second, _ = self.call("manager", service.activate, *self.files["v1"])
        frappe.db.rollback()
        after = {row.source_customer_id: row.name for row in frappe.get_all(REFERENCE, filters={"source_system": self.source}, fields=["name", "source_customer_id"])}
        self.assertEqual(before, after)
        self.assertEqual(first["meta"]["version"], second["meta"]["version"])
        self.assertNotEqual(first["meta"]["request_id"], second["meta"]["request_id"])
        self.assertEqual(self.subjects()[1], 200)

    def test_b1_authorized_empty_and_query_miss_are_successful_empty(self):
        for response in (self.subjects(customer="empty"), self.subjects(query="cannot-match-" + self.token)):
            self.assertEqual(response[1], 200)
            self.assertEqual(response[0]["items"], [])
            self.assertEqual(response[0]["meta"]["version"], self.files["v1"][1])

    def test_c1_bad_active_file_does_not_fall_back_and_recovers(self):
        valid = (self.root / "v1.json").read_bytes()
        for bad in (None, b"broken-json", json.dumps(self.v2).encode()):
            try:
                if bad is None:
                    (self.root / "v1.json").unlink()
                else:
                    (self.root / "v1.json").write_bytes(bad)
                self.assert_error(self.subjects(), "SOURCE_UNAVAILABLE", 503)
            finally:
                (self.root / "v1.json").write_bytes(valid)
        self.assertEqual(self.subjects()[0]["items"], self.v1["subjects"])

    def test_c2_concurrent_activation_never_exposes_partial_references_or_mixed_version(self):
        prepared, release = Event(), Event()
        original = service._prepare_references

        def pause_after_real_writes(data):
            original(data)
            prepared.set()
            if not release.wait(15):
                raise TimeoutError("合成事务等待超时")

        with patch.object(service, "_prepare_references", side_effect=pause_after_real_writes):
            with ThreadPoolExecutor(max_workers=5) as executor:
                activation = executor.submit(self.request, "manager", service.activate, *self.files["v2"])
                try:
                    self.assertTrue(prepared.wait(10))
                    reads = [executor.submit(self.request, "reader", api.list_subjects, self.source, "delivery") for _ in range(4)]
                    for future in reads:
                        data, status = future.result(timeout=10)
                        self.assertEqual(status, 200)
                        self.assertEqual(data["meta"]["version"], self.files["v1"][1])
                        self.assertEqual(data["items"], self.v1["subjects"])
                        self.assertEqual(data["customer"]["name"], self.v1["customers"][1]["name"])
                    frappe.db.rollback()
                    self.assertFalse(frappe.db.exists(REFERENCE, {"source_system": self.source, "source_customer_id": "new-v2"}))
                finally:
                    release.set()
                activation.result(timeout=15)
        data, status = self.subjects()
        self.assertEqual(status, 200)
        self.assertEqual(data["meta"]["version"], self.files["v2"][1])
        self.assertEqual(data["items"], self.v2["subjects"])
        self.assertEqual(data["customer"]["name"], self.v2["customers"][1]["name"])

    def test_c3_audit_write_failure_fails_closed(self):
        with patch.object(audit, "create_request_log", side_effect=RuntimeError("synthetic-secret-must-not-leak")):
            response = self.subjects()
        self.assert_error(response, "AUDIT_UNAVAILABLE", 503)
        self.assertNotIn("synthetic-secret", json.dumps(response))
        self.assertNotIn("items", response[0])
        self.assertEqual(self.subjects()[1], 200)

    def test_c4_unknown_parameters_and_actor_spoofing_are_rejected(self):
        for kwargs in ({"actor": self.users["manager"]}, {"user": "Administrator"}, {"limit": 100}, {"query": []}, {"query": "x" * 201}, {"query": "a\x00b"}):
            self.assert_error(self.subjects(**kwargs), "INVALID_ARGUMENT", 400)
        self.assert_error(self.call("reader", api.list_subjects, "different-source", "delivery"), "NOT_FOUND", 404)
        self.assert_error(self.subjects(customer=""), "INVALID_ARGUMENT", 400)

    def test_d1_d2_exact_grant_scope_and_no_administrator_business_bypass(self):
        for identity in ("no-grant", "foreign-scope", "no-role", "manager", "Administrator"):
            self.assert_error(self.call(identity, api.list_customers), "FORBIDDEN", 403)
            self.assert_error(self.subjects(identity), "NOT_FOUND", 404)
        self.assert_error(self.subjects("parent"), "NOT_FOUND", 404)
        actual, _ = self.subjects("no-grant")
        missing, _ = self.subjects("no-grant", customer="does-not-exist")
        self.assertEqual({k: v for k, v in actual["error"].items() if k != "request_id"},
                         {k: v for k, v in missing["error"].items() if k != "request_id"})
        self.grant("foreign-scope", "delivery", applicable_for=REFERENCE, apply_to_all_doctypes=0)
        frappe.db.commit()
        self.assertEqual(self.subjects("foreign-scope")[1], 200)

    def test_d3_direct_database_revocation_overrides_warm_permissions_cache(self):
        for identity in ("reader", "client"):
            self.assertEqual(self.subjects(identity)[1], 200)
            frappe.db.delete("User Permission", {"user": self.users[identity], "for_value": self.refs["delivery"]})
            frappe.db.commit()
            self.assert_error(self.subjects(identity), "NOT_FOUND", 404)

    def test_d4_user_role_and_membership_changes_override_warm_role_cache(self):
        email = self.users["reader"]
        for target in ("User", "Role", "Has Role"):
            self.assertEqual(self.subjects()[1], 200)
            member = frappe.db.get_value("Has Role", {"parent": email, "role": ROLE}, "name")
            try:
                if target == "User":
                    frappe.db.set_value("User", email, "enabled", 0, update_modified=False)
                elif target == "Role":
                    frappe.db.set_value("Role", ROLE, "disabled", 1, update_modified=False)
                else:
                    frappe.db.set_value("Has Role", member, "role", "Guest", update_modified=False)
                frappe.db.commit()
                self.assert_error(self.subjects(), "NOT_FOUND", 404)
                self.assert_error(self.call("reader", api.list_customers), "FORBIDDEN", 403)
            finally:
                frappe.db.set_value("User", email, "enabled", 1, update_modified=False)
                frappe.db.set_value("Role", ROLE, "disabled", 0, update_modified=False)
                frappe.db.set_value("Has Role", member, "role", ROLE, update_modified=False)
                frappe.db.commit()
            self.assertEqual(self.subjects()[1], 200)

    def test_d5_native_reads_and_administrative_share_cannot_bypass_directory(self):
        from frappe.client import get, get_list
        from frappe.desk.search import search_link
        from frappe.core.doctype.data_export.exporter import export_data
        for function, kwargs in ((get, {"doctype": REFERENCE, "name": self.refs["delivery"]}),
                                 (get_list, {"doctype": REFERENCE}),
                                 (search_link, {"doctype": REFERENCE, "txt": ""}),
                                 (export_data, {"doctype": REFERENCE, "with_data": True})):
            with self.subTest(function=function.__name__), self.assertRaises(frappe.PermissionError):
                self.call("reader", function, **kwargs)
        with self.assertRaises(frappe.PermissionError):
            self.call("manager", frappe.share.add, REFERENCE, self.refs["delivery"], self.users["no-grant"], read=1,
                      flags={"ignore_share_permission": True})
        self.assertFalse(frappe.db.exists("DocShare", {"share_doctype": REFERENCE, "share_name": self.refs["delivery"]}))

    def test_d6_responses_only_include_approved_fields(self):
        customers, _ = self.call("reader", api.list_customers)
        subjects, _ = self.subjects()
        self.assertEqual(set(customers), {"items", "meta"})
        self.assertEqual(set(subjects), {"items", "meta", "customer"})
        self.assertEqual(set(subjects["meta"]), {"mode", "source_system", "version", "data_as_of", "request_id"})
        self.assertEqual({item["customer_id"] for item in customers["items"]}, {"delivery", "empty"})
        for item in customers["items"] + [subjects["customer"]]:
            self.assertEqual(set(item), {"customer_id", "name"})
        for item in subjects["items"]:
            self.assertEqual(set(item), {"subject_id", "customer_id", "name", "source_type"})
        self.assertNotIn(str(self.root), json.dumps([customers, subjects]))

    def test_d7_all_outcomes_have_persistent_minimal_business_audit(self):
        outcomes = [(self.subjects(), "success", "reader"), (self.subjects(customer="empty"), "empty", "reader"),
                    (self.subjects("no-grant"), "NOT_FOUND", "no-grant")]
        with patch.object(snapshot, "SNAPSHOT_ROOT", str(self.root / "absent")):
            outcomes.append((self.subjects(), "SOURCE_UNAVAILABLE", "reader"))
        frappe.db.rollback()
        for (result, _), outcome, identity in outcomes:
            request_id = (result.get("meta") or result["error"])["request_id"]
            rows = frappe.get_all("Integration Request", filters={"request_id": request_id}, fields=["data", "status", "integration_request_service"])
            self.assertEqual(len(rows), 1)
            record = json.loads(rows[0].data)
            self.assertEqual(set(record), {"actor", "action", "outcome", "request_id", "version", "count"})
            self.assertEqual(record["actor"], self.users[identity])
            self.assertEqual(record["outcome"], outcome)
            self.assertEqual(record["request_id"], request_id)
            self.assertEqual(rows[0].integration_request_service, "BizBase Directory")
            self.assertEqual(rows[0].status, "Completed" if outcome in ("success", "empty") else "Failed")

    def test_f1_failed_activation_rolls_back_prepared_references_and_state(self):
        original = service._prepare_references

        def fail_after_real_writes(data):
            original(data)
            raise RuntimeError("合成事务故障")

        with patch.object(service, "_prepare_references", side_effect=fail_after_real_writes):
            with self.assertRaises(DirectoryError):
                self.call("manager", service.activate, *self.files["v2"])
        frappe.db.rollback()
        self.assertFalse(frappe.db.exists(REFERENCE, {"source_system": self.source, "source_customer_id": "new-v2"}))
        self.assertEqual(frappe.db.get_value(REFERENCE, self.refs["delivery"], "display_name"), self.v1["customers"][1]["name"])
        self.assertEqual(self.subjects()[0]["meta"]["version"], self.files["v1"][1])

    def test_f1_disable_reenable_and_bad_enable_are_atomic_and_restricted(self):
        self.assertNotIn(service.activate, frappe.whitelisted)
        self.assertNotIn(service.set_enabled, frappe.whitelisted)
        with self.assertRaises(DirectoryError):
            self.call("reader", service.set_enabled, False)
        self.call("manager", service.set_enabled, False)
        self.assert_error(self.subjects(), "DIRECTORY_DISABLED", 503)
        with self.assertRaises(DirectoryError):
            self.call("manager", service.set_enabled, "true")
        with patch.object(snapshot, "SNAPSHOT_ROOT", str(self.root / "absent")):
            with self.assertRaises(DirectoryError):
                self.call("manager", service.set_enabled, True)
        self.assert_error(self.subjects(), "DIRECTORY_DISABLED", 503)
        self.call("manager", service.set_enabled, True)
        self.assertEqual(self.subjects()[0]["meta"]["version"], self.files["v1"][1])
