import json
import unittest
from types import SimpleNamespace

from crm_uninstall_compat import archive_serializer


class TestArchiveFilters(unittest.TestCase):
    def setUp(self):
        self.filters = [["CRM Territory", "enabled", "=", 1]]
        self.field = SimpleNamespace(parenttype="DocType", parent="CRM Territory", link_filters=self.filters)

    def test_preserves_json_and_restores_original_object(self):
        invoke = archive_serializer(lambda f: f.link_filters, {"CRM Territory"})
        self.assertEqual(json.loads(invoke(self.field)), self.filters)
        self.assertIs(self.field.link_filters, self.filters)

    def test_other_parent_and_non_list_pass_through(self):
        invoke = archive_serializer(lambda f: f.link_filters, {"CRM Territory"})
        self.field.parent = "Customer"
        self.assertIs(invoke(self.field), self.filters)
        self.field.parent = "CRM Territory"
        self.field.link_filters = '{"enabled":1}'
        self.assertEqual(invoke(self.field), self.field.link_filters)

    def test_error_restores_field_and_propagates(self):
        def fail(field):
            raise ValueError("original archive error")
        with self.assertRaisesRegex(ValueError, "original archive error"):
            archive_serializer(fail, {"CRM Territory"})(self.field)
        self.assertIs(self.field.link_filters, self.filters)
