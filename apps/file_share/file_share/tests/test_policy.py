"""Share authorization regression checks with Frappe installed, no active site."""

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from file_share import permissions, serve
from file_share.file_share.doctype.file_share.file_share import FileShare


class SharePolicyTest(unittest.TestCase):
	def setUp(self):
		self.share = SimpleNamespace(name="abcDEF0123", owner="author", current_version=1, access_level="Specified",
			access_salt="epoch", password_salt="pwd-epoch", legacy_salt=None, domain="company.example",
			password_doc=Mock(), allowed_users=[SimpleNamespace(user="invited")], allowed_roles=[SimpleNamespace(role="Sales User")])
		self.frappe = self.enter_patch(serve, "frappe")
		self.frappe.get_roles.side_effect = lambda user: {"manager": ["System Manager"], "seller": ["Sales User"]}.get(user, [])
		self.employee = self.enter_patch(serve, "is_employee")
		self.employee.side_effect = lambda user, **kwargs: user not in {"Guest", "left"}

	def enter_patch(self, module, name):
		patcher = patch.object(module, name)
		self.addCleanup(patcher.stop)
		return patcher.start()

	def test_management_entry_is_the_canonical_doctype_route(self):
		from file_share import hooks
		self.frappe.request.path = "/file-share"
		response = serve.ShareRenderer.render(None)
		self.assertEqual((response.status_code, response.location), (302, "/desk/file-share"))
		self.assertEqual(hooks.add_to_apps_screen[0]["route"], response.location)

	def test_existing_viewer_tokens_survive_the_package_rename(self):
		import hmac
		from file_share import core

		with patch("frappe.utils.password.get_encryption_key", return_value="site-key"):
			old_key = hmac.new(b"site-key", b"static_share/v1", hashlib.sha256).digest()
			token = core.sign(old_key, "pwd", self.share.name, self.share.access_salt, ttl=60)
			self.share.access_level = "Password"
			self.share.legacy_salt = self.share.access_salt
			self.frappe.request.cookies = {serve.password_cookie(self.share.name): token}
			self.assertEqual(serve.viewer_decision(self.share, "Guest"), "view")
			self.assertEqual(serve.grant_key("t"), "static_share:grant:t")

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
		with patch.object(serve, "live_session_data", return_value={}) as live:
			self.assertTrue(serve.asset_allowed(self.share, 1, token))
			live.assert_called_once_with("invited", "original")
			live.return_value = None
			self.assertFalse(serve.asset_allowed(self.share, 1, token))
			live.return_value = {}
			self.share.allowed_users = []
			self.assertFalse(serve.asset_allowed(self.share, 1, token))
			self.share.allowed_users = [SimpleNamespace(user="invited")]
			self.frappe.request.cookies = {}
			self.assertFalse(serve.asset_allowed(self.share, 1, token))
			self.frappe.request.cookies = {serve.CAP_COOKIE: cookie}
			self.share.access_salt = "rotated"
			self.assertFalse(serve.asset_allowed(self.share, 1, token))

	def test_history_and_login_keep_the_requested_share_path(self):
		from urllib.parse import parse_qs, urlsplit
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		self.share.title = "Report"
		self.share.versions = [SimpleNamespace(version=1, entry="index.html"), SimpleNamespace(version=2, entry="old.html")]
		for prefix in ("/file-share/s", "/s", "/file-share"):
			base = f"{prefix}/{self.share.name}"
			self.frappe.request = Request(EnvironBuilder(path=base, query_string="v=2").get_environ())
			self.frappe.session.user = "Guest"
			login = serve.serve_wrapper(self.share, base)
			self.assertEqual(parse_qs(urlsplit(login.location).query), {"redirect-to": [base + "?v=2"]})
			with patch.object(serve, "log"), patch.object(serve, "asset_grant", return_value=("token", "cookie")):
				for user, version, entry in (("author", 2, "old.html"), ("invited", 1, "index.html")):
					self.frappe.session.user = user
					response = serve.serve_wrapper(self.share, base)
					directory = f"{base}/c/{version}/token/"
					self.assertIn(f'src="{directory}{entry}"', response.get_data(as_text=True))
					self.assertIn(f"Path={directory};", response.headers["Set-Cookie"])

	def test_password_form_post_and_cookie_stay_on_each_alias(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		self.share.title = "Report"
		self.share.access_level = "Password"
		self.frappe.session.user = "Guest"
		self.frappe.cache.get.return_value = 0
		for prefix in ("/file-share/s", "/s", "/file-share"):
			base = f"{prefix}/{self.share.name}"
			url = base + "?v=2"
			self.share.password_doc.get_password.return_value = "secret"
			with patch.object(serve, "signing_key", return_value=b"key"):
				self.frappe.request = Request(EnvironBuilder(path=base, query_string="v=2").get_environ())
				gate = serve.serve_wrapper(self.share, base)
				self.assertIn(f'action="{url}"', gate.get_data(as_text=True))
				self.frappe.request = Request(EnvironBuilder(path=base, method="POST", query_string="v=2",
					data={"password": "secret"}).get_environ())
				response = serve.serve_wrapper(self.share, base)
				self.assertEqual((response.status_code, response.location), (303, url))
				self.assertIn(f"Path={base};", response.headers["Set-Cookie"])

	def test_employee_requires_both_database_records(self):
		with patch.object(permissions, "frappe") as framework:
			framework.db.exists.side_effect = [True, False]
			self.assertFalse(permissions.is_employee("desk"))
			self.assertEqual(framework.db.exists.call_args_list[0].args, ("User", {"name": "desk", "enabled": 1, "user_type": "System User"}))
			self.assertEqual(framework.db.exists.call_args_list[1].args, ("Employee", {"user_id": "desk", "status": "Active"}))

	def test_verified_sso_session_can_upload_without_hr_record(self):
		with patch.object(permissions, "frappe") as f:
			f.session.user = "staff"
			f.session.data = {"user": "staff", "yid_uid": "uid", "yid_token_exp": 300, "yid_lease_until": 200, "yid_verified_at": 100}
			f.db.exists.side_effect = lambda dt, filters: dt in ("User", "Yishan ID Binding")
			with patch("time.time", return_value=150):
				self.assertTrue(permissions.is_employee("staff"))
				self.assertFalse(permissions.is_employee("other"))
				f.db.exists.side_effect = lambda dt, filters: dt == "User"
				self.assertFalse(permissions.is_employee("staff"))
			f.db.exists.side_effect = lambda dt, filters: dt in ("User", "Yishan ID Binding")
			with patch("time.time", return_value=301):
				self.assertFalse(permissions.is_employee("staff"))

	def test_history_is_server_owned(self):
		doc = Mock(versions=[{"version": 10, "entry": "index.html"}])
		with patch("file_share.file_share.doctype.file_share.file_share._", side_effect=lambda s: s), patch(
			"file_share.file_share.doctype.file_share.file_share.frappe.throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				FileShare._validate_versions(doc, None)
			doc.versions = []
			FileShare._validate_versions(doc, None)
			doc.set.assert_called_once_with("versions", [])
