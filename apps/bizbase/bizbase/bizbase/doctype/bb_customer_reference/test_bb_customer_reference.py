import json
import uuid

import frappe
from frappe.tests import IntegrationTestCase

from bizbase.install import ensure_model


class TestBBCustomerReference(IntegrationTestCase):
    def make_reference(self):
        return frappe.get_doc({"doctype": "BB Customer Reference", "source_system": "model-fixture", "source_customer_id": str(uuid.uuid4()), "display_name": "模型测试记录"}).insert()

    def test_unique_source_identity(self):
        ref = self.make_reference()
        with self.assertRaises(frappe.UniqueValidationError):
            frappe.get_doc({"doctype": ref.doctype, "source_system": ref.source_system, "source_customer_id": ref.source_customer_id, "display_name": "同源重复"}).insert()

    def test_identity_immutable_and_label_mutable(self):
        ref = self.make_reference()
        ref.display_name = "已修正展示名"
        ref.save()
        ref.source_customer_id = str(uuid.uuid4())
        with self.assertRaises(frappe.ValidationError):
            ref.save()

    def test_share_is_rejected(self):
        ref = self.make_reference()
        with self.assertRaises(frappe.PermissionError):
            frappe.share.add(ref.doctype, ref.name, "Administrator", read=1, flags={"ignore_share_permission": True})

    def test_install_is_idempotent_and_reader_has_no_crud(self):
        before = frappe.db.get_value("DefaultValue", {"parent": "__global", "defkey": "bizbase_directory_state"}, "defvalue")
        ensure_model()
        ensure_model()
        self.assertEqual(before, frappe.db.get_value("DefaultValue", {"parent": "__global", "defkey": "bizbase_directory_state"}, "defvalue"))
        self.assertTrue(frappe.db.exists("Role", "BB Directory Reader"))
        self.assertFalse(any(p.role == "BB Directory Reader" for p in frappe.get_meta("BB Customer Reference").permissions))
