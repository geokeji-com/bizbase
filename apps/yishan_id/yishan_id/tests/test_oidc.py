"""OIDC 协议层单元测试。不依赖 Frappe，用本地模拟移山 ID，不发出网络请求。"""

import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import ec

from yishan_id.oidc import (
	IdentityInactiveError,
	IdentityStatusUnavailableError,
	OIDCError,
	Provider,
	authorization_url,
	check_identity_status,
	exchange_code,
	new_pkce,
	pkce_challenge,
	validate_settings,
	verify_logout_token,
)
from yishan_id.tests import fake_idp
from yishan_id.tests.fake_idp import FakeIdP, query, settings


class OIDCTestCase(unittest.TestCase):
	def setUp(self):
		self.idp = FakeIdP()
		self.provider = Provider(http=self.idp)
		self.settings = settings()

	def login(self, nonce="nonce-1", **id_extra):
		verifier, challenge = new_pkce()
		code = self.idp.issue_code(nonce, challenge, **id_extra)
		return exchange_code(self.provider, self.settings, code, verifier, nonce)


class TestSettings(OIDCTestCase):
	def test_requires_https_outside_loopback(self):
		with self.assertRaises(OIDCError):
			validate_settings(settings(issuer="http://id.example.com/oidc"))
		validate_settings(settings(issuer="https://id.geokeji.com/oidc", redirect_uri="https://bizbase.geokeji.com/cb"))

	def test_requires_client_id(self):
		with self.assertRaises(OIDCError):
			validate_settings(settings(client_id=""))

	def test_derives_audience_and_status_url(self):
		s = settings(issuer="https://id.geokeji.com/oidc")
		self.assertEqual(s.api_audience, "https://id.geokeji.com/yid/v1")
		self.assertEqual(s.identity_status_url, "https://id.geokeji.com/yid/v1/identity-status:check")


class TestAuthorizationUrl(OIDCTestCase):
	def test_contains_pkce_state_nonce_and_feishu_connector(self):
		verifier, _ = new_pkce()
		params = query(authorization_url(self.provider, self.settings, "state-1", "nonce-1", verifier))
		self.assertEqual(params["code_challenge"], pkce_challenge(verifier))
		self.assertEqual(params["code_challenge_method"], "S256")
		self.assertEqual(params["state"], "state-1")
		self.assertEqual(params["nonce"], "nonce-1")
		self.assertEqual(params["redirect_uri"], fake_idp.REDIRECT_URI)
		self.assertEqual(params["resource"], "http://127.0.0.1:3901/yid/v1")
		self.assertEqual(params["direct_sign_in"], "social:yishan-feishu")
		self.assertIn("identity:check", params["scope"].split())
		self.assertNotIn("code_verifier", params)

	def test_direct_sign_in_can_be_disabled(self):
		verifier, _ = new_pkce()
		url = authorization_url(self.provider, settings(direct_sign_in=None), "s", "n", verifier)
		self.assertNotIn("direct_sign_in", query(url))

	def test_rejects_discovery_with_other_issuer(self):
		original = self.idp.get

		def get(url, timeout=None, **kw):
			response = original(url, timeout=timeout)
			if url.endswith("openid-configuration"):
				response._body["issuer"] = "https://evil.example/oidc"
			return response

		self.idp.get = get
		with self.assertRaises(OIDCError):
			authorization_url(self.provider, self.settings, "s", "n", "v" * 43)


class TestExchangeCode(OIDCTestCase):
	def test_valid_login_returns_principal(self):
		principal = self.login()
		self.assertEqual(principal.yishan_uid, fake_idp.UID)
		self.assertEqual(principal.identity_version, 1)
		self.assertEqual(principal.issuer, fake_idp.ISSUER)
		self.assertEqual(principal.sid, "sid-1")

	def test_wrong_verifier_rejected(self):
		_, challenge = new_pkce()
		code = self.idp.issue_code("n", challenge)
		other_verifier, _ = new_pkce()
		with self.assertRaises(OIDCError):
			exchange_code(self.provider, self.settings, code, other_verifier, "n")

	def test_code_cannot_be_reused(self):
		verifier, challenge = new_pkce()
		code = self.idp.issue_code("n", challenge)
		exchange_code(self.provider, self.settings, code, verifier, "n")
		with self.assertRaises(OIDCError):
			exchange_code(self.provider, self.settings, code, verifier, "n")

	def test_nonce_mismatch_rejected(self):
		verifier, challenge = new_pkce()
		code = self.idp.issue_code("issued-nonce", challenge)
		with self.assertRaises(OIDCError):
			exchange_code(self.provider, self.settings, code, verifier, "expected-nonce")

	def test_old_authentication_rejected(self):
		with self.assertRaises(OIDCError):
			self.login(auth_time=int(time.time()) - 3 * 3600)

	def test_token_signed_by_unknown_key_rejected(self):
		forged = FakeIdP()  # 同 kid，不同私钥
		self.idp.token_overrides = forged.tokens_for("nonce-1")
		with self.assertRaises(OIDCError):
			self.login()

	def test_wrong_issuer_rejected(self):
		with self.assertRaises(OIDCError):
			self.login(iss="https://evil.example/oidc")

	def test_id_token_for_other_client_rejected(self):
		with self.assertRaises(OIDCError):
			self.login(aud="another-client")

	def test_access_token_from_other_client_rejected(self):
		self.idp.access_overrides = {"client_id": "vzztu42ec0rdyaonqdpme"}
		with self.assertRaises(OIDCError):
			self.login()

	def test_mismatched_subjects_rejected(self):
		with self.assertRaises(OIDCError):
			self.login(sub="someone-else")

	def test_missing_yishan_uid_rejected(self):
		self.idp.access_overrides = {"yishan": {"identity_version": 1}}
		with self.assertRaises(OIDCError):
			self.login()

	def test_customer_identity_rejected(self):
		self.idp.access_overrides = {
			"yishan": {"uid": fake_idp.UID, "identity_version": 1, "principal_class": "CUSTOMER"}
		}
		with self.assertRaises(OIDCError):
			self.login()

	def test_expired_access_token_rejected(self):
		self.idp.access_overrides = {"exp": int(time.time()) - 120}
		with self.assertRaises(OIDCError):
			self.login()

	def test_rotated_signing_key_is_fetched(self):
		self.login()  # 缓存旧 JWKS
		self.idp.key = ec.generate_private_key(ec.SECP384R1())
		self.idp.kid = "test-key-2"
		self.assertEqual(self.login().yishan_uid, fake_idp.UID)


class TestIdentityStatus(OIDCTestCase):
	def check(self, version=1):
		return check_identity_status(self.provider, self.settings, fake_idp.UID, version, "token")

	def test_active_lease_is_capped_at_60_seconds(self):
		now = time.time()
		lease = check_identity_status(self.provider, self.settings, fake_idp.UID, 1, "token", now=now)
		self.assertLessEqual(lease.expires_at, now + 60)

	def test_inactive_rejected(self):
		self.idp.status = {"active": False, "current_identity_version": 1, "reason": "resigned"}
		with self.assertRaises(IdentityInactiveError):
			self.check()

	def test_version_change_rejected(self):
		self.idp.status = {"active": True, "current_identity_version": 2}
		with self.assertRaises(IdentityInactiveError):
			self.check()

	def test_network_failure_is_unavailable(self):
		self.idp.status_error = ConnectionError("down")
		with self.assertRaises(IdentityStatusUnavailableError):
			self.check()

	def test_provider_refusal_is_not_a_transient_failure(self):
		for status in (401, 403):
			with self.subTest(status=status), patch.object(
				self.idp, "post", return_value=fake_idp.Response(status, {})
			):
				with self.assertRaises(IdentityInactiveError):
					self.check()

	def test_malformed_response_is_unavailable(self):
		self.idp.status = {"active": "yes", "current_identity_version": 1}
		with self.assertRaises(IdentityStatusUnavailableError):
			self.check()


class TestLogoutToken(OIDCTestCase):
	def test_valid_logout_token(self):
		claims = verify_logout_token(self.provider, self.settings, self.idp.logout_token())
		self.assertEqual(claims["sub"], "logto-sub-1")
		self.assertEqual(claims["sid"], "sid-1")

	def test_empty_subject_and_session_id_cannot_match_all_sessions(self):
		with self.assertRaises(OIDCError):
			verify_logout_token(self.provider, self.settings, self.idp.logout_token(sub="", sid=""))

	def test_nonce_rejected(self):
		with self.assertRaises(OIDCError):
			verify_logout_token(self.provider, self.settings, self.idp.logout_token(nonce="x"))

	def test_missing_event_rejected(self):
		with self.assertRaises(OIDCError):
			verify_logout_token(self.provider, self.settings, self.idp.logout_token(events={}))

	def test_other_audience_rejected(self):
		with self.assertRaises(OIDCError):
			verify_logout_token(self.provider, self.settings, self.idp.logout_token(aud="other"))

	def test_old_token_rejected(self):
		with self.assertRaises(OIDCError):
			verify_logout_token(
				self.provider, self.settings, self.idp.logout_token(iat=int(time.time()) - 3600)
			)

	def test_forged_signature_rejected(self):
		forged = FakeIdP().logout_token()
		with self.assertRaises(OIDCError):
			verify_logout_token(self.provider, self.settings, forged)
