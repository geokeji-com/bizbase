"""移山 ID（Logto OIDC）协议逻辑。不依赖 Frappe，便于独立测试。

约束来自 yishan-id 的 OIDC 指南与 SDK：Authorization Code + PKCE S256、精确回调，
校验 issuer、audience、签名、nonce 与认证时间；业务身份只用 yishan.uid；
在职状态正结果最多缓存 60 秒。
"""

import base64
import hashlib
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

import jwt
import requests

LEEWAY_SECONDS = 30
HTTP_TIMEOUT_SECONDS = 5
STATUS_TIMEOUT_SECONDS = 2
DISCOVERY_TTL_SECONDS = 3600
POSITIVE_TTL_SECONDS = 60
LOGOUT_TOKEN_MAX_AGE_SECONDS = 300
ALLOWED_ALGORITHMS = ("ES384", "ES256", "RS256", "PS256")
BACKCHANNEL_EVENT = "http://schemas.openid.net/event/backchannel-logout"
YID_UID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
DEFAULT_SCOPES = "openid profile email identity:check"
DEFAULT_DIRECT_SIGN_IN = "social:yishan-feishu"
DEFAULT_MAX_AUTH_AGE_SECONDS = 7200


class OIDCError(Exception):
	"""登录或令牌校验失败。消息不含令牌或密钥。"""


class IdentityInactiveError(OIDCError):
	"""移山 ID 明确答复身份无效、离职或身份版本已变化。"""


class IdentityStatusUnavailableError(OIDCError):
	"""无法确认在职状态（超时、网络错误或响应无效）。"""


@dataclass(frozen=True)
class Settings:
	issuer: str
	client_id: str
	redirect_uri: str
	client_secret: str | None = None
	audience: str | None = None
	status_url: str | None = None
	scopes: str = DEFAULT_SCOPES
	# 让 Logto 直接进入飞书员工连接器；为空时显示移山 ID 的通用登录页。
	direct_sign_in: str | None = DEFAULT_DIRECT_SIGN_IN
	max_auth_age_seconds: int = DEFAULT_MAX_AUTH_AGE_SECONDS

	@property
	def origin(self) -> str:
		scheme, _, rest = self.issuer.partition("://")
		return f"{scheme}://{rest.split('/', 1)[0]}"

	@property
	def api_audience(self) -> str:
		return self.audience or f"{self.origin}/yid/v1"

	@property
	def identity_status_url(self) -> str:
		return self.status_url or f"{self.api_audience}/identity-status:check"


@dataclass(frozen=True)
class Principal:
	yishan_uid: str
	identity_version: int
	issuer: str
	subject: str
	sid: str | None
	name: str | None
	access_token: str
	expires_at: int


@dataclass(frozen=True)
class StatusLease:
	verified_at: float
	expires_at: float


def b64url(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def random_token() -> str:
	return secrets.token_urlsafe(32)


def new_pkce() -> tuple[str, str]:
	"""返回 (code_verifier, code_challenge)，challenge 方法为 S256。"""
	verifier = secrets.token_urlsafe(64)
	return verifier, pkce_challenge(verifier)


def pkce_challenge(verifier: str) -> str:
	return b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _is_loopback_http(url: str) -> bool:
	return url.startswith(("http://127.0.0.1:", "http://localhost:"))


def validate_settings(settings: Settings) -> None:
	for field in ("issuer", "client_id", "redirect_uri"):
		if not getattr(settings, field):
			raise OIDCError(f"yishan_id_{field} 未配置")
	# 只有本机模拟身份服务可以用 http；真实环境必须 https。
	for url in (settings.issuer, settings.redirect_uri, settings.api_audience, settings.identity_status_url):
		if not (url.startswith("https://") or _is_loopback_http(url)):
			raise OIDCError("移山 ID 相关地址必须使用 HTTPS")


def _yishan_claim(claims: dict, key: str):
	nested = claims.get("yishan")
	if isinstance(nested, dict) and key in nested:
		return nested[key]
	return claims.get(f"yishan.{key}", claims.get(f"yishan_{key}"))


class Provider:
	"""discovery 与 JWKS 缓存。未知 kid 时刷新一次 JWKS，以支持签名密钥轮换。"""

	def __init__(self, http=requests):
		self.http = http
		self._metadata: dict[str, tuple[dict, float]] = {}
		self._jwks: dict[str, dict] = {}

	def metadata(self, issuer: str) -> dict:
		now = time.time()
		cached = self._metadata.get(issuer)
		if cached and now < cached[1]:
			return cached[0]
		url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
		try:
			response = self.http.get(url, timeout=HTTP_TIMEOUT_SECONDS)
			response.raise_for_status()
			metadata = response.json()
		except Exception as e:
			raise OIDCError("无法读取移山 ID discovery") from e
		if metadata.get("issuer") != issuer:
			raise OIDCError("discovery 中的 issuer 与配置不一致")
		for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
			if not metadata.get(key):
				raise OIDCError(f"discovery 缺少 {key}")
		self._metadata[issuer] = (metadata, now + DISCOVERY_TTL_SECONDS)
		return metadata

	def signing_key(self, issuer: str, token: str) -> tuple[jwt.PyJWK, str]:
		try:
			header = jwt.get_unverified_header(token)
		except jwt.InvalidTokenError as e:
			raise OIDCError("令牌格式无效") from e
		alg, kid = header.get("alg"), header.get("kid")
		if alg not in ALLOWED_ALGORITHMS or not kid:
			raise OIDCError("令牌签名算法或 kid 不被接受")
		jwks_uri = self.metadata(issuer)["jwks_uri"]
		key = self._find_key(jwks_uri, kid, refresh=False) or self._find_key(jwks_uri, kid, refresh=True)
		if not key:
			raise OIDCError("签名密钥不在 JWKS 中")
		try:
			return jwt.PyJWK(key, algorithm=alg), alg
		except jwt.PyJWKError as e:
			raise OIDCError("签名密钥与算法不匹配") from e

	def _find_key(self, jwks_uri: str, kid: str, refresh: bool) -> dict | None:
		if refresh or jwks_uri not in self._jwks:
			try:
				response = self.http.get(jwks_uri, timeout=HTTP_TIMEOUT_SECONDS)
				response.raise_for_status()
				self._jwks[jwks_uri] = response.json()
			except Exception as e:
				raise OIDCError("无法读取移山 ID 签名密钥") from e
		return next((k for k in self._jwks[jwks_uri].get("keys", []) if k.get("kid") == kid), None)

	def decode(self, settings: Settings, token: str, audience: str, required: list[str]) -> dict:
		key, alg = self.signing_key(settings.issuer, token)
		try:
			return jwt.decode(
				token,
				key,
				algorithms=[alg],
				issuer=settings.issuer,
				audience=audience,
				leeway=LEEWAY_SECONDS,
				options={"require": required},
			)
		except jwt.InvalidTokenError as e:
			raise OIDCError(f"令牌校验失败：{type(e).__name__}") from e


def authorization_url(provider: Provider, settings: Settings, state: str, nonce: str, verifier: str) -> str:
	params = {
		"client_id": settings.client_id,
		"redirect_uri": settings.redirect_uri,
		"response_type": "code",
		"scope": settings.scopes,
		"resource": settings.api_audience,
		"state": state,
		"nonce": nonce,
		"code_challenge": pkce_challenge(verifier),
		"code_challenge_method": "S256",
		"max_age": str(settings.max_auth_age_seconds),
	}
	if settings.direct_sign_in:
		params["direct_sign_in"] = settings.direct_sign_in
	return f"{provider.metadata(settings.issuer)['authorization_endpoint']}?{urlencode(params)}"


def exchange_code(provider: Provider, settings: Settings, code: str, verifier: str, nonce: str) -> Principal:
	"""用授权码换取令牌并校验，返回员工身份。"""
	data = {
		"grant_type": "authorization_code",
		"code": code,
		"redirect_uri": settings.redirect_uri,
		"code_verifier": verifier,
		"resource": settings.api_audience,
	}
	auth = None
	if settings.client_secret:
		auth = (settings.client_id, settings.client_secret)
	else:
		data["client_id"] = settings.client_id
	try:
		response = provider.http.post(
			provider.metadata(settings.issuer)["token_endpoint"],
			data=data,
			auth=auth,
			timeout=HTTP_TIMEOUT_SECONDS,
		)
		response.raise_for_status()
		tokens = response.json()
	except OIDCError:
		raise
	except Exception as e:
		raise OIDCError("授权码兑换失败") from e
	if not isinstance(tokens.get("id_token"), str) or not isinstance(tokens.get("access_token"), str):
		raise OIDCError("令牌响应缺少 id_token 或 access_token")
	id_claims = provider.decode(
		settings, tokens["id_token"], settings.client_id, ["exp", "iat", "iss", "sub", "aud"]
	)
	access_claims = provider.decode(
		settings, tokens["access_token"], settings.api_audience, ["exp", "iat", "iss", "sub", "aud"]
	)
	return principal_from_claims(settings, id_claims, access_claims, tokens["access_token"], nonce)


def principal_from_claims(
	settings: Settings, id_claims: dict, access_claims: dict, access_token: str, nonce: str, now=None
) -> Principal:
	now = time.time() if now is None else now
	if not nonce or not secrets.compare_digest(str(id_claims.get("nonce", "")), nonce):
		raise OIDCError("nonce 不匹配")
	auth_time = id_claims.get("auth_time")
	if not isinstance(auth_time, int) or now - auth_time > settings.max_auth_age_seconds + LEEWAY_SECONDS:
		raise OIDCError("移山 ID 认证时间过早，请重新登录")
	# 共享 API audience 的其他客户端令牌不能用于本站。
	if access_claims.get("client_id") != settings.client_id:
		raise OIDCError("access_token 不属于本站客户端")
	if "azp" in access_claims and access_claims["azp"] != settings.client_id:
		raise OIDCError("access_token 的 azp 与本站客户端不一致")
	if id_claims["iss"] != access_claims["iss"] or id_claims["sub"] != access_claims["sub"]:
		raise OIDCError("id_token 与 access_token 不属于同一身份")
	uid = _yishan_claim(access_claims, "uid")
	if not isinstance(uid, str) or not YID_UID_PATTERN.match(uid):
		raise OIDCError("access_token 缺少有效的 yishan.uid")
	id_uid = _yishan_claim(id_claims, "uid")
	if id_uid is not None and id_uid != uid:
		raise OIDCError("id_token 与 access_token 的 yishan.uid 不一致")
	version = _yishan_claim(access_claims, "identity_version")
	if isinstance(version, bool) or not isinstance(version, int) or version < 1:
		raise OIDCError("access_token 缺少有效的 yishan.identity_version")
	principal_class = _yishan_claim(access_claims, "principal_class")
	if principal_class not in (None, "STAFF"):
		raise OIDCError("只允许移山员工身份登录")
	return Principal(
		yishan_uid=uid,
		identity_version=version,
		issuer=access_claims["iss"],
		subject=access_claims["sub"],
		sid=id_claims.get("sid") if isinstance(id_claims.get("sid"), str) else None,
		name=id_claims.get("name") if isinstance(id_claims.get("name"), str) else None,
		access_token=access_token,
		expires_at=int(access_claims["exp"]),
	)


def check_identity_status(
	provider: Provider, settings: Settings, uid: str, identity_version: int, access_token: str, now=None
) -> StatusLease:
	"""用员工本人的 access token 查询在职状态，返回正结果租约。"""
	now = time.time() if now is None else now
	try:
		response = provider.http.post(
			settings.identity_status_url,
			json={"yid_uid": uid, "identity_version": identity_version},
			headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
			timeout=STATUS_TIMEOUT_SECONDS,
		)
		response.raise_for_status()
		body = response.json()
	except Exception as e:
		raise IdentityStatusUnavailableError("无法查询移山 ID 在职状态") from e
	if not isinstance(body, dict) or not isinstance(body.get("active"), bool):
		raise IdentityStatusUnavailableError("在职状态响应无效")
	current_version = body.get("current_identity_version")
	if isinstance(current_version, bool) or not isinstance(current_version, int):
		raise IdentityStatusUnavailableError("在职状态响应无效")
	if not body["active"] or current_version != identity_version:
		raise IdentityInactiveError(str(body.get("reason") or "inactive"))
	try:
		remote_expiry = datetime.fromisoformat(str(body["status_expires_at"]).replace("Z", "+00:00")).timestamp()
	except (KeyError, ValueError) as e:
		raise IdentityStatusUnavailableError("在职状态有效期无效") from e
	if remote_expiry <= now:
		raise IdentityStatusUnavailableError("在职状态有效期已过")
	return StatusLease(verified_at=now, expires_at=min(now + POSITIVE_TTL_SECONDS, remote_expiry))


def verify_logout_token(provider: Provider, settings: Settings, token: str, now=None) -> dict:
	"""校验后端通知退出的 logout_token，返回 claims（含 sub、可选 sid、jti）。"""
	now = time.time() if now is None else now
	claims = provider.decode(settings, token, settings.client_id, ["iat", "iss", "aud", "jti"])
	if "nonce" in claims:
		raise OIDCError("logout_token 不得包含 nonce")
	events = claims.get("events")
	if not isinstance(events, dict) or not isinstance(events.get(BACKCHANNEL_EVENT), dict):
		raise OIDCError("logout_token 缺少退出事件")
	if not isinstance(claims.get("sub"), str) and not isinstance(claims.get("sid"), str):
		raise OIDCError("logout_token 缺少 sub 或 sid")
	if abs(now - claims["iat"]) > LOGOUT_TOKEN_MAX_AGE_SECONDS:
		raise OIDCError("logout_token 已过期")
	return claims
