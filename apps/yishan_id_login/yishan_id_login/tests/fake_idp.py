"""测试用的本地模拟移山 ID：真实 ES384 签名，HTTP 层用桩替代，不发出网络请求。"""

import json
import time
import uuid
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from yishan_id_login.oidc import BACKCHANNEL_EVENT, Settings

ISSUER = "http://127.0.0.1:3901/oidc"
CLIENT_ID = "bizbase-test-client"
REDIRECT_URI = "http://127.0.0.1:8080/api/method/yishan_id_login.auth.callback"
UID = "bb4e3b1f-d297-49ef-b937-7ed240a89a43"


def settings(**overrides) -> Settings:
	values = {"issuer": ISSUER, "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI}
	values.update(overrides)
	return Settings(**values)


class Response:
	def __init__(self, status: int, body):
		self.status_code = status
		self._body = body

	def raise_for_status(self):
		if self.status_code >= 400:
			raise RuntimeError(f"HTTP {self.status_code}")

	def json(self):
		if isinstance(self._body, Exception):
			raise self._body
		return json.loads(json.dumps(self._body))


class FakeIdP:
	"""实现 requests 的 get/post 子集。"""

	def __init__(self):
		self.key = ec.generate_private_key(ec.SECP384R1())
		self.kid = "test-key-1"
		self.status = {"active": True, "current_identity_version": 1}
		self.status_error: Exception | None = None
		self.token_overrides: dict = {}
		self.access_overrides: dict = {}
		self.codes: dict[str, dict] = {}
		self.status_calls = 0

	# ---- 签名 ----
	def jwk(self) -> dict:
		data = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.key.public_key()))
		data.update({"kid": self.kid, "alg": "ES384", "use": "sig"})
		return data

	def sign(self, claims: dict, kid: str | None = None, key=None) -> str:
		return jwt.encode(claims, key or self.key, algorithm="ES384", headers={"kid": kid or self.kid})

	def issue_code(self, nonce: str, challenge: str, **id_extra) -> str:
		code = uuid.uuid4().hex
		self.codes[code] = {"nonce": nonce, "challenge": challenge, "id_extra": id_extra}
		return code

	def tokens_for(self, nonce: str, **id_extra) -> dict:
		now = int(time.time())
		base = {"iss": ISSUER, "sub": "logto-sub-1", "iat": now, "exp": now + 3600}
		id_claims = {**base, "aud": CLIENT_ID, "nonce": nonce, "auth_time": now, "sid": "sid-1", "name": "测试员工"}
		id_claims.update(id_extra)
		access = {
			**base,
			"aud": "http://127.0.0.1:3901/yid/v1",
			"client_id": CLIENT_ID,
			"jti": uuid.uuid4().hex,
			"yishan": {"uid": UID, "identity_version": 1, "principal_class": "STAFF"},
		}
		access.update(self.access_overrides)
		tokens = {"id_token": self.sign(id_claims), "access_token": self.sign(access), "token_type": "Bearer"}
		tokens.update(self.token_overrides)
		return tokens

	def logout_token(self, **overrides) -> str:
		claims = {
			"iss": ISSUER,
			"aud": CLIENT_ID,
			"iat": int(time.time()),
			"jti": uuid.uuid4().hex,
			"sub": "logto-sub-1",
			"sid": "sid-1",
			"events": {BACKCHANNEL_EVENT: {}},
		}
		claims.update(overrides)
		return self.sign({k: v for k, v in claims.items() if v is not None})

	# ---- requests 接口 ----
	def get(self, url, timeout=None, **kwargs):
		if url == f"{ISSUER}/.well-known/openid-configuration":
			return Response(
				200,
				{
					"issuer": ISSUER,
					"authorization_endpoint": f"{ISSUER}/auth",
					"token_endpoint": f"{ISSUER}/token",
					"jwks_uri": f"{ISSUER}/jwks",
					"end_session_endpoint": f"{ISSUER}/session/end",
				},
			)
		if url == f"{ISSUER}/jwks":
			return Response(200, {"keys": [self.jwk()]})
		return Response(404, {})

	def post(self, url, data=None, json=None, headers=None, auth=None, timeout=None):
		if url == f"{ISSUER}/token":
			from yishan_id_login.oidc import pkce_challenge

			grant = self.codes.pop(data.get("code"), None)
			if not grant or pkce_challenge(data["code_verifier"]) != grant["challenge"]:
				return Response(400, {"error": "invalid_grant"})
			if data.get("redirect_uri") != REDIRECT_URI:
				return Response(400, {"error": "invalid_grant"})
			return Response(200, self.tokens_for(grant["nonce"], **grant["id_extra"]))
		if url == "http://127.0.0.1:3901/yid/v1/identity-status:check":
			self.status_calls += 1
			if self.status_error:
				raise self.status_error
			body = dict(self.status)
			body.setdefault("status_expires_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 300)))
			return Response(200, body)
		return Response(404, {})


def query(url: str) -> dict:
	return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
