"""File-share CLI transport. Credentials are per origin and never follow redirects."""

import hashlib
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import stat
import sys
import tempfile
import time
import webbrowser
from contextlib import ExitStack
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ClientError(Exception):
    def __init__(self, message, *, status=0, code="client_error"):
        super().__init__(message)
        self.status = status
        self.code = code


class _RefuseRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def origin(site):
    error = ClientError("站点必须是 HTTPS 源地址；本机回环地址支持 HTTP", code="invalid_site")
    if not isinstance(site, str) or not site or re.search(r"[\x00-\x20\x7f\\%?#]", site):
        raise error
    try:
        parsed = urlsplit(site)
        host, port = parsed.hostname, parsed.port
        if not host or not re.fullmatch(r"[a-zA-Z0-9.:-]+", host) or parsed.username is not None or parsed.path not in ("", "/"):
            raise error
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise error
        host = f"[{host}]" if ":" in host else host
        suffix = f":{port}" if port is not None and port != {"https": 443, "http": 80}[parsed.scheme] else ""
        return f"{parsed.scheme}://{host}{suffix}"
    except ValueError as exc:
        raise error from exc


def _multipart(stream, payload, path):
    name = path.name
    if re.search(r'[\x00-\x1f\x7f"\\]', name):
        raise ClientError("请更改报告文件名，移除引号、反斜杠和控制字符")
    boundary = secrets.token_hex(32)
    for field, value in payload.items():
        if not re.fullmatch(r"[A-Za-z0-9_]+", field):
            raise ClientError("请求字段名无效")
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        stream.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode())
    stream.write(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
    with path.open("rb") as source:
        shutil.copyfileobj(source, stream)
    stream.write(f'\r\n--{boundary}--\r\n'.encode())
    length = stream.tell()
    stream.seek(0)
    return {"Content-Type": "multipart/form-data; boundary=" + boundary, "Content-Length": str(length)}


class Client:
    def __init__(self, site):
        self.site = origin(site)
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        self.path = base / "bizbase" / (hashlib.sha256(self.site.encode()).hexdigest() + ".token")
        self.opener = build_opener(_RefuseRedirect())

    def _token(self):
        try:
            with os.fdopen(os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))) as f:
                mode = os.fstat(f.fileno())
                if not stat.S_ISREG(mode.st_mode) or (os.name == "posix" and mode.st_mode & 0o077):
                    raise ClientError("请将本站点凭证文件设为仅本人可读写，再运行 bizbase login")
                token = f.read(64).strip()
                if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
                    raise ClientError("本地凭证无效，请重新运行 bizbase login", code="invalid_token")
                return token
        except FileNotFoundError as exc:
            raise ClientError("请先对当前站点运行 bizbase login", code="not_logged_in") from exc

    def _save(self, token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise ClientError("授权响应无效，请重试", code="invalid_response")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(token + "\n")
            os.replace(temp, self.path)
        finally:
            Path(temp).unlink(missing_ok=True)

    def _post(self, method, payload=None, *, token=None, file=None):
        payload = {} if payload is None else payload
        with ExitStack() as stack:
            headers = {"Accept": "application/json"}
            if token:
                headers["X-BizBase-Share-Token"] = token
            if file is not None:
                body = stack.enter_context(tempfile.TemporaryFile())
                headers.update(_multipart(body, payload, Path(file)))
            else:
                body = json.dumps(payload, ensure_ascii=False).encode()
                headers["Content-Type"] = "application/json"
            req = Request(f"{self.site}/api/method/file_share.{method}", data=body, headers=headers, method="POST")
            try:
                with self.opener.open(req, timeout=60) as response:
                    result = json.load(response)
                if not isinstance(result, dict) or "message" not in result:
                    raise ValueError()
                return result["message"]
            except HTTPError as exc:
                exc.close()
                # The framework error body may echo confidential arguments or a traceback.
                codes = {401: ("unauthorized", "请运行 bizbase login 后重试"),
                         403: ("forbidden", "请核对本人权限、授权状态或重新运行 bizbase login"),
                         404: ("not_found", "请核对记录、命令和站点版本"),
                         409: ("conflict", "请检查当前版本、域名状态及请求 ID 后重试"),
                         413: ("file_too_large", "请减小报告文件后重试"),
                         417: ("validation_error", "请核对请求参数、报告版本及入口配置"),
                         429: ("rate_limited", "调用过于频繁，请稍后重试")}
                code, advice = codes.get(exc.code, ("http_error", "请检查站点与输入，使用原请求 ID 核对写入结果"))
                raise ClientError(f"HTTP {exc.code}，{advice}", status=exc.code, code=code) from None
            except (URLError, OSError, http.client.HTTPException) as exc:
                raise ClientError("连接中断，请检查站点连接。写入重试请沿用原请求 ID", code="network_error") from exc
            except (ValueError, UnicodeError) as exc:
                raise ClientError("站点未返回预期的 JSON 响应，请核对地址", code="invalid_response") from exc

    def login(self):
        verifier = secrets.token_urlsafe(32)
        challenge = hashlib.sha256(verifier.encode()).hexdigest()
        device_label = os.environ.get("BIZBASE_DEVICE_LABEL") or socket.gethostname().split(".")[0] or "员工终端"
        self._post("cli_auth.begin", {"challenge": challenge, "device_label": device_label[:100]})
        url = f"{self.site}/file-share-authorize?challenge={challenge}"
        print(f"请在浏览器核对代码 {challenge[:8].upper()}，再确认授权。\n{url}", file=sys.stderr, flush=True)
        webbrowser.open(url)
        end = time.monotonic() + 300
        while time.monotonic() < end:
            result = self._post("cli_auth.exchange", {"verifier": verifier})
            if result.get("state") == "pending":
                time.sleep(2)
                continue
            self._save(result.get("token"))
            return self.call("whoami")
        raise ClientError("授权请求已过期，请重新运行 bizbase login", code="expired")

    def logout(self):
        result = self._post("cli_auth.revoke", token=self._token())
        self.path.unlink(missing_ok=True)
        return result

    def call(self, method, payload=None, *, file=None):
        if method not in {"whoami", "domains", "list_reports", "get_report", "upload", "publish", "close"}:
            raise ClientError("未知文件分享命令")
        return self._post(f"api.{method}", payload, token=self._token(), file=file)
