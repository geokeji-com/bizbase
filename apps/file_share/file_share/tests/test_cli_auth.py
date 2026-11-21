"""File-share delegated identity checks with the framework installed, no site required."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from file_share import cli_auth


class DelegateIdentityTest(unittest.TestCase):
	def setUp(self):
		self.f = self.enterContext(patch.object(cli_auth, "frappe"))
		self.f.throw.side_effect = PermissionError
		self.f.session.data = {}
		self.ip = self.enterContext(patch("frappe.auth.validate_ip_address"))
		self.live = self.enterContext(patch.object(cli_auth, "live_session_data"))
		self.employee = self.enterContext(patch.object(cli_auth, "is_employee"))
		self.grant = {"user": "employee", "sid": "browser-session"}

	def test_dead_session_never_becomes_employee(self):
		self.live.return_value = None
		with self.assertRaises(PermissionError):
			cli_auth._delegate(self.grant)
		self.f.set_user.assert_not_called()

	def test_requires_current_employee_and_only_transfers_identity_fields(self):
		self.live.return_value = {"user": "employee", "csrf_token": "browser-only"}
		self.employee.return_value = False
		with self.assertRaises(PermissionError):
			cli_auth._delegate(self.grant)
		self.employee.return_value = True
		cli_auth._delegate(self.grant)
		self.assertEqual(self.f.session.data, {"user": "employee"})
		self.ip.assert_called_with("employee")

	def test_requires_scoped_rpc_path_and_post(self):
		def whoami():
			return {"user": "employee"}
		whoami.__module__ = "file_share.api"
		self.f.whitelist.return_value = lambda fn: fn
		rpc = cli_auth.share_rpc(whoami)
		self.f.request.method = "POST"
		self.f.request.path = "/api/method/unrelated.route"
		with self.assertRaises(PermissionError):
			rpc()
		self.f.request.method = "GET"
		self.f.request.path = "/api/method/file_share.api.whoami"
		with self.assertRaises(PermissionError):
			rpc()
		self.f.request.method = "POST"
		self.f.request.headers = {}
		self.assertEqual(rpc(), {"user": "employee"})
		self.f.cache.get.assert_not_called()

	def test_pre_inventory_claim_fails_closed(self):
		with self.assertRaises(PermissionError):
			cli_auth._record(None, lock=True)
		self.f.db.get_value.assert_not_called()

	def test_only_owner_or_manager_can_disable_and_repeat_keeps_actor(self):
		self.f.session.user = "peer"
		name = "a" * 32
		row = SimpleNamespace(employee="employee", revoked_at=None)
		with patch.object(cli_auth, "_record", return_value=row), patch.object(cli_auth, "is_manager", return_value=False) as manager:
			with self.assertRaises(PermissionError):
				cli_auth.disable_grant(name)
			self.f.db.set_value.assert_not_called()
			manager.return_value = True
			with patch.object(cli_auth, "now_datetime", return_value="now"):
				self.assertEqual(cli_auth.disable_grant(name), {"revoked": True})
			self.f.db.set_value.assert_called_once_with("File Share Grant", name, {"revoked_at": "now", "revoked_by": "peer"})
			row.revoked_at = "now"
			self.f.session.user = row.employee
			manager.return_value = False
			self.assertEqual(cli_auth.disable_grant(name), {"revoked": True})
			self.assertEqual(self.f.db.set_value.call_count, 1)

	def test_approval_requires_cookie_session_and_csrf(self):
		self.f.request.cookies = {"sid": "browser-session"}
		self.f.request.headers = {}
		self.f.session.sid = "browser-session"
		self.f.session.data = SimpleNamespace(get=Mock(return_value="csrf"), csrf_token="csrf")
		self.live.return_value = {"user": "employee"}
		with self.assertRaises(PermissionError):
			cli_auth.approve.__wrapped__("a" * 64)
		self.f.request.headers = {"X-Frappe-CSRF-Token": "csrf"}
		self.f.request.cookies = {}
		with self.assertRaises(PermissionError):
			cli_auth.approve.__wrapped__("a" * 64)
		self.f.cache.eval.assert_not_called()
