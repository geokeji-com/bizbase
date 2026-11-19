"""测试首次登录和在职状态失效的边界，使用模拟请求与时钟。"""

import unittest
from unittest.mock import patch

from yishan_id_login import auth, session
from yishan_id_login.oidc import IdentityInactiveError, IdentityStatusUnavailableError, StatusLease
from yishan_id_login.tests.fake_idp import UID, settings


class TestCallback(unittest.TestCase):
	def test_checks_staff_status_before_creating_local_session(self):
		transaction = {"browser": auth._hash("browser"), "nonce": "nonce", "verifier": "verifier"}
		for error_type, status in ((IdentityInactiveError, 403), (IdentityStatusUnavailableError, 503)):
			with (
				self.subTest(status=status),
				patch.object(auth, "frappe") as frappe,
				patch.object(auth, "_", str),
				patch.object(auth, "get_valid_settings", return_value=settings()),
				patch.object(auth, "_pop_transaction", return_value=transaction),
				patch.object(auth, "exchange_code"),
				patch.object(auth, "check_identity_status", side_effect=error_type),
				patch.object(auth, "bound_user") as bound_user,
				patch.object(auth, "error_page") as error_page,
			):
				frappe.request.cookies = {auth.BROWSER_COOKIE: "browser"}
				auth.callback(code="code", state="state")
				self.assertEqual(error_page.call_args.args[1], status)
				bound_user.assert_not_called()
				frappe.local.login_manager.login_as.assert_not_called()


class TestSessionStatus(unittest.TestCase):
	def setUp(self):
		config = settings()
		self.data = {
			"yid_uid": UID,
			"yid_iss": config.issuer,
			"yid_version": 1,
			"yid_token": "encrypted",
			"yid_token_exp": 1000,
			"yid_verified_at": 100,
			"yid_lease_until": 160,
		}
		self.enterContext(patch.object(session, "frappe"))
		self.enterContext(patch.object(session, "get_valid_settings", return_value=config))
		self.enterContext(patch.object(session, "still_bound", return_value=True))
		self.enterContext(patch.object(session, "decrypt", return_value="token"))
		self.check_status = self.enterContext(patch.object(session, "check_identity_status"))

	def test_refresh_updates_verified_time(self):
		self.check_status.return_value = StatusLease(160, 220)
		self.assertIsNone(session.evaluate(self.data, 160))
		self.assertEqual(self.data["yid_verified_at"], 160)
		self.assertEqual(self.data["yid_lease_until"], 220)

	def test_transient_failure_does_not_extend_last_success(self):
		self.check_status.side_effect = IdentityStatusUnavailableError
		with patch.object(session.time, "time", return_value=399):
			self.assertIsNone(session.evaluate(self.data, 398))
		self.assertEqual(self.data["yid_verified_at"], 100)
		self.assertEqual(self.data["yid_lease_until"], 400)

	def test_failure_returning_after_five_minute_deadline_denies_request(self):
		self.check_status.side_effect = IdentityStatusUnavailableError
		with patch.object(session.time, "time", return_value=400):
			self.assertEqual(session.evaluate(self.data, 399), "Yishan ID status unavailable")

	def test_explicit_refusal_denies_request_during_outage_grace_period(self):
		self.check_status.side_effect = IdentityInactiveError
		self.assertEqual(session.evaluate(self.data, 160), "Yishan ID identity inactive")
