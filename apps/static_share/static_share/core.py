"""与 Frappe 无关的纯逻辑：令牌签名、安全解压、路径解析。可在无站点环境下单测。"""

import base64
import hashlib
import hmac
import os
import posixpath
import shutil
import stat
import tempfile
import time
import zipfile

MAX_FILES = 5000
MAX_TOTAL_BYTES = 200 * 1024 * 1024
IGNORED_PREFIXES = ("__MACOSX/",)
IGNORED_NAMES = (".DS_Store", "Thumbs.db")
HTML_SUFFIXES = (".html", ".htm")


class UnsafeArchiveError(ValueError):
	"""压缩包包含不安全或超限内容。"""


class NoEntryError(ValueError):
	"""找不到可作为首页的 HTML。"""


# ---------- 签名令牌 ----------


def _b64(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign(key: bytes, kind: str, name: str, epoch: str, ttl: int, now: float | None = None) -> str:
	"""签发 `<过期时间36进制>.<签名>`，只在路径或 cookie 中使用，不含任何可读业务信息。"""
	exp = int((now if now is not None else time.time()) + ttl)
	exp36 = _to36(exp)
	mac = hmac.new(key, f"{kind}|{name}|{epoch}|{exp36}".encode(), hashlib.sha256).digest()
	return f"{exp36}.{_b64(mac)[:32]}"


def verify(key: bytes, token: str, kind: str, name: str, epoch: str, now: float | None = None) -> bool:
	if not isinstance(token, str) or len(token) > 64 or not token.isascii() or token.count(".") != 1:
		return False
	exp36, sig = token.split(".")
	try:
		exp = int(exp36, 36)
	except ValueError:
		return False
	if exp < (now if now is not None else time.time()):
		return False
	mac = hmac.new(key, f"{kind}|{name}|{epoch}|{exp36}".encode(), hashlib.sha256).digest()
	return hmac.compare_digest(_b64(mac)[:32], sig)


def _to36(n: int) -> str:
	digits = "0123456789abcdefghijklmnopqrstuvwxyz"
	out = ""
	while n:
		n, r = divmod(n, 36)
		out = digits[r] + out
	return out or "0"


def access_epoch(*parts) -> str:
	"""访问设置的指纹。任何一项改变，旧令牌与密码 cookie 全部失效。"""
	return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:16]


# ---------- 解压与入口 ----------


def member_name(info: zipfile.ZipInfo) -> str:
	"""未标记 UTF-8 的条目：Python 按 cp437 解码；还原原始字节后依次尝试 UTF-8（macOS）和 GBK（Windows 中文）。"""
	if info.flag_bits & 0x800:
		return info.filename
	raw = info.filename.encode("cp437", errors="replace")
	for enc in ("utf-8", "gbk"):
		try:
			return raw.decode(enc)
		except UnicodeDecodeError:
			continue
	return info.filename


def _safe_member_name(name: str) -> str | None:
	"""返回规范化的相对路径；需要忽略的条目返回 None；不安全时抛错。"""
	if "\\" in name or "\x00" in name:
		raise UnsafeArchiveError(f"文件名不合法：{name}")
	if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
		raise UnsafeArchiveError(f"不允许绝对路径：{name}")
	norm = posixpath.normpath(name)
	if norm == ".." or norm.startswith("../"):
		raise UnsafeArchiveError(f"不允许跳出目录：{name}")
	if name.startswith(IGNORED_PREFIXES) or posixpath.basename(norm) in IGNORED_NAMES:
		return None
	return norm


def extract_zip(zip_path: str, target_dir: str) -> tuple[int, int]:
	"""安全解压到 target_dir（必须尚不存在）。返回（文件数, 总字节数）。"""
	files = 0
	total = 0
	tmp = tempfile.mkdtemp(prefix=".extract-", dir=os.path.dirname(target_dir))
	try:
		with zipfile.ZipFile(zip_path) as zf:
			entries = zf.infolist()
			if len(entries) > MAX_FILES:
				raise UnsafeArchiveError(f"压缩包条目数超过 {MAX_FILES}")
			for info in entries:
				if info.is_dir():
					continue
				if stat.S_ISLNK(info.external_attr >> 16):
					raise UnsafeArchiveError(f"不允许符号链接：{info.filename}")
				rel = _safe_member_name(member_name(info))
				if rel is None:
					continue
				files += 1
				dest = os.path.join(tmp, rel)
				if os.path.exists(dest):
					raise UnsafeArchiveError(f"压缩包中有重复路径：{rel}")
				os.makedirs(os.path.dirname(dest), exist_ok=True)
				# 按实际解出的字节计数，不信任压缩包头部声明的大小
				with zf.open(info) as src, open(dest, "wb") as out:
					while chunk := src.read(64 * 1024):
						total += len(chunk)
						if total > MAX_TOTAL_BYTES:
							raise UnsafeArchiveError(f"解压后超过 {MAX_TOTAL_BYTES // 1024 // 1024} MB")
						out.write(chunk)
		if files == 0:
			raise NoEntryError("压缩包是空的")
		os.replace(tmp, target_dir)
	except (FileExistsError, NotADirectoryError, IsADirectoryError) as e:
		shutil.rmtree(tmp, ignore_errors=True)
		raise UnsafeArchiveError("压缩包里的文件与目录重名") from e
	except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as e:
		shutil.rmtree(tmp, ignore_errors=True)
		raise UnsafeArchiveError("不是有效的 ZIP 文件") from e
	except BaseException:
		shutil.rmtree(tmp, ignore_errors=True)
		raise
	return files, total


def store_single_html(content: bytes, target_dir: str) -> tuple[int, int]:
	if len(content) > MAX_TOTAL_BYTES:
		raise UnsafeArchiveError(f"HTML 超过 {MAX_TOTAL_BYTES // 1024 // 1024} MB")
	tmp = tempfile.mkdtemp(prefix=".extract-", dir=os.path.dirname(target_dir))
	try:
		with open(os.path.join(tmp, "index.html"), "wb") as f:
			f.write(content)
		os.replace(tmp, target_dir)
	except BaseException:
		shutil.rmtree(tmp, ignore_errors=True)
		raise
	return 1, len(content)


def find_entry(root: str) -> str:
	"""首页查找顺序：根目录 index.html → 唯一顶层文件夹里的 index.html → 根目录唯一 HTML。"""
	if os.path.isfile(os.path.join(root, "index.html")):
		return "index.html"
	entries = [e for e in os.listdir(root) if not e.startswith(".")]
	dirs = [e for e in entries if os.path.isdir(os.path.join(root, e))]
	files = [e for e in entries if os.path.isfile(os.path.join(root, e))]
	if len(dirs) == 1 and not files and os.path.isfile(os.path.join(root, dirs[0], "index.html")):
		return f"{dirs[0]}/index.html"
	html = [f for f in files if f.lower().endswith(HTML_SUFFIXES)]
	if len(html) == 1:
		return html[0]
	raise NoEntryError("找不到首页：请在压缩包根目录放 index.html")


# ---------- 请求路径解析 ----------


def resolve_request(root: str, rel: str) -> tuple[str, str | None]:
	"""
	把请求的相对路径解析到磁盘文件。
	返回 ("file", 绝对路径)、("redirect", 新相对路径) 或 ("missing", None)。
	Frappe 路由可能去掉 `.html` 后缀和末尾斜杠，这里按“原样 → 加 .html → 目录首页”的顺序补回。
	"""
	rel = rel.strip("/")
	if rel and any(part in ("..", ".", "") or "\x00" in part or "\\" in part for part in rel.split("/")):
		return "missing", None
	real_root = os.path.realpath(root)

	def inside(p: str) -> str | None:
		rp = os.path.realpath(p)
		return rp if rp == real_root or rp.startswith(real_root + os.sep) else None

	base = os.path.join(root, rel) if rel else root
	path = inside(base)
	if path and os.path.isfile(path):
		return "file", path
	for suffix in (".html", ".htm"):
		cand = inside(base + suffix) if rel else None
		if cand and os.path.isfile(cand):
			return "file", cand
	if path and os.path.isdir(path) and os.path.isfile(os.path.join(path, "index.html")):
		# 跳到 <目录>/index，让页面内相对路径以该目录为基准
		return "redirect", f"{rel}/index" if rel else "index"
	return "missing", None
