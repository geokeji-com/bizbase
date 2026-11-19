"""Share authorization regression checks with Frappe installed, no active site."""

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from static_share import permissions, serve
from static_share.static_share.doctype.static_share.static_share import StaticShare


class SharePolicyTest(unittest.TestCase):
	def setUp(self):
		self.share = SimpleNamespace(name="abcDEF0123", owner="author", current_version=1, access_level="Specified",
			access_salt="epoch", allowed_users=[SimpleNamespace(user="invited")], allowed_roles=[SimpleNamespace(role="Sales User")])
		self.frappe = self.enter_patch(serve, "frappe")
		self.frappe.get_roles.side_effect = lambda user: {"manager": ["System Manager"], "seller": ["Sales User"]}.get(user, [])
		self.employee = self.enter_patch(serve, "is_employee")
		self.employee.side_effect = lambda user: user not in {"Guest", "left"}

	def enter_patch(self, module, name):
		patcher = patch.object(module, name)
		self.addCleanup(patcher.stop)
		return patcher.start()

	def test_specified_requires_author_user_or_role(self):
		for user in ("author", "invited", "seller"):
			self.assertTrue(serve.staff_can_view(self.share, user))
		for user in ("Guest", "manager", "left", "other"):
			self.assertFalse(serve.staff_can_view(self.share, user))
		self.assertFalse(serve.is_author(self.share, "manager"))

	def test_password_requires_cookie_for_manager(self):
		self.share.access_level = "Password"
		self.frappe.request.cookies = {}
		with patch.object(serve, "signing_key", return_value=b"key"):
			self.assertEqual(serve.viewer_decision(self.share, "manager"), "password")
			self.assertEqual(serve.viewer_decision(self.share, "author"), "view")

	def test_private_asset_rechecks_cookie_session_and_eligibility(self):
		token, cookie = "t" * 32, "c" * 32
		grant = dict(share=self.share.name, version=1, salt="epoch", sid="original", user="invited",
			digest=hashlib.sha256(cookie.encode()).hexdigest())
		self.frappe.cache.get_value.return_value = grant
		self.frappe.request.cookies = {serve.CAP_COOKIE: cookie}
		with patch.object(serve, "session_is_live", return_value=True) as live:
			self.assertTrue(serve.asset_allowed(self.share, 1, token))
			live.assert_called_once_with("invited", "original")
			live.return_value = False
			self.assertFalse(serve.asset_allowed(self.share, 1, token))
			live.return_value = True
			self.share.allowed_users = []
			self.assertFalse(serve.asset_allowed(self.share, 1, token))
			self.share.allowed_users = [SimpleNamespace(user="invited")]
			self.frappe.request.cookies = {}
			self.assertFalse(serve.asset_allowed(self.share, 1, token))
			self.frappe.request.cookies = {serve.CAP_COOKIE: cookie}
			self.share.access_salt = "rotated"
			self.assertFalse(serve.asset_allowed(self.share, 1, token))

	def test_employee_requires_both_database_records(self):
		with patch.object(permissions, "frappe") as framework:
			framework.db.exists.side_effect = [True, False]
			self.assertFalse(permissions.is_employee("desk"))
			self.assertEqual(framework.db.exists.call_args_list[0].args, ("User", {"name": "desk", "enabled": 1, "user_type": "System User"}))
			self.assertEqual(framework.db.exists.call_args_list[1].args, ("Employee", {"user_id": "desk", "status": "Active"}))

	def test_history_is_server_owned(self):
		doc = Mock(versions=[{"version": 10, "entry": "index.html"}])
		with patch("static_share.static_share.doctype.static_share.static_share._", side_effect=lambda s: s), patch(
			"static_share.static_share.doctype.static_share.static_share.frappe.throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				StaticShare._validate_versions(doc, None)
			doc.versions = []
			StaticShare._validate_versions(doc, None)
			doc.set.assert_called_once_with("versions", [])
