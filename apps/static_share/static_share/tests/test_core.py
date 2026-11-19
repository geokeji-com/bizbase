"""纯逻辑测试：令牌、安全解压、首页查找、路径解析。不需要站点。"""

import io
import os
from pathlib import Path
from unittest.mock import patch
import stat
import tempfile
import unittest
import zipfile

from static_share import core

KEY = b"k" * 32


def make_zip(entries: dict, symlink: str | None = None) -> io.BytesIO:
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as zf:
		for name, data in entries.items():
			zf.writestr(name, data)
		if symlink:
			info = zipfile.ZipInfo(symlink)
			info.external_attr = (stat.S_IFLNK | 0o777) << 16
			zf.writestr(info, "/etc/passwd")
	buf.seek(0)
	return buf


class TestToken(unittest.TestCase):
	def test_roundtrip(self):
		t = core.sign(KEY, "view", "abc", "salt:1", 60, now=1000)
		self.assertTrue(core.verify(KEY, t, "view", "abc", "salt:1", now=1059))

	def test_expired(self):
		t = core.sign(KEY, "view", "abc", "salt:1", 60, now=1000)
		self.assertFalse(core.verify(KEY, t, "view", "abc", "salt:1", now=1061))

	def test_bound_to_share_kind_and_salt(self):
		t = core.sign(KEY, "view", "abc", "salt:1", 60, now=1000)
		for kind, name, epoch in (("pwd", "abc", "salt:1"), ("view", "abd", "salt:1"), ("view", "abc", "salt:2"), ("view", "abc", "other:1")):
			self.assertFalse(core.verify(KEY, t, kind, name, epoch, now=1001), (kind, name, epoch))

	def test_tampered_or_malformed(self):
		t = core.sign(KEY, "view", "abc", "s", 60, now=1000)
		exp, sig = t.split(".")
		self.assertFalse(core.verify(KEY, f"{core._to36(int(exp, 36) + 9999)}.{sig}", "view", "abc", "s", now=1001))
		for bad in ("", "x", "a.b.c", "!!.abc", f"{exp}.报告", 123, None):
			self.assertFalse(core.verify(KEY, bad, "view", "abc", "s", now=1001))
		self.assertFalse(core.verify(b"z" * 32, t, "view", "abc", "s", now=1001))


class TestExtract(unittest.TestCase):
	def setUp(self):
		self.base = self.enterContext(tempfile.TemporaryDirectory())
		self.target = os.path.join(self.base, "1")

	def test_single_html_size_limit(self):
		with patch.object(core, "MAX_TOTAL_BYTES", 1), self.assertRaises(core.UnsafeArchiveError):
			core.store_single_html(b"hi", self.target)
		self.assertEqual(os.listdir(self.base), [])

	def test_normal_zip_with_assets(self):
		z = make_zip({"index.html": "<h1>hi</h1>", "css/a.css": "body{}", "__MACOSX/._x": "junk", ".DS_Store": "x"})
		count, size = core.extract_zip(z, self.target)
		self.assertEqual(count, 2)
		self.assertEqual(core.find_entry(self.target), "index.html")
		self.assertFalse(os.path.exists(os.path.join(self.target, "__MACOSX")))

	def test_rejects_traversal(self):
		for name in ("../evil.html", "a/../../evil.html", "/abs.html", "a\\..\\b.html"):
			with self.subTest(name=name):
				z = make_zip({name: "x"})
				with self.assertRaises(core.UnsafeArchiveError):
					core.extract_zip(z, os.path.join(self.base, name.replace("/", "_").replace("\\", "_")))
		self.assertEqual([e for e in os.listdir(self.base) if not e.startswith(".")], [])
		self.assertEqual([e for e in os.listdir(self.base) if e.startswith(".extract-")], [])

	def test_rejects_conflicting_entries(self):
		for names in (("index.html", "./index.html"), ("report", "report/index.html")):
			with self.subTest(names=names), self.assertRaises(core.UnsafeArchiveError):
				core.extract_zip(make_zip(dict.fromkeys(names, "x")), self.target)
			self.assertEqual(os.listdir(self.base), [])

	def test_entry_limit_counts_ignored_entries(self):
		archive = make_zip({"index.html": "ok", "__MACOSX/x": "ignored"})
		with patch.object(core, "MAX_FILES", 1), self.assertRaises(core.UnsafeArchiveError):
			core.extract_zip(archive, self.target)
		self.assertEqual(os.listdir(self.base), [])

	def test_rejects_symlink(self):
		z = make_zip({"index.html": "x"}, symlink="link")
		with self.assertRaises(core.UnsafeArchiveError):
			core.extract_zip(z, self.target)
		self.assertFalse(os.path.exists(self.target))

	def test_rejects_zip_bomb_by_actual_bytes(self):
		z = make_zip({"index.html": "x", "big.bin": b"\0" * 2048})
		old = core.MAX_TOTAL_BYTES
		core.MAX_TOTAL_BYTES = 1024
		try:
			with self.assertRaises(core.UnsafeArchiveError):
				core.extract_zip(z, self.target)
		finally:
			core.MAX_TOTAL_BYTES = old
		self.assertFalse(os.path.exists(self.target))

	def test_rejects_non_zip_and_empty(self):
		bad = os.path.join(self.base, "x.zip")
		Path(bad).write_bytes(b"not a zip")
		with self.assertRaises(core.UnsafeArchiveError):
			core.extract_zip(bad, self.target)
		with self.assertRaises(core.NoEntryError):
			core.extract_zip(make_zip({"__MACOSX/a": "x"}), self.target)

	def test_gbk_filename_from_windows_zip(self):
		# Python 写非 ASCII 文件名时总会用 UTF-8 并打标记；这里先写占位名，再换成 GBK 原始字节，
		# 模拟 Windows 中文系统打出的、未打 UTF-8 标记的压缩包。
		buf = io.BytesIO()
		with zipfile.ZipFile(buf, "w") as zf:
			zf.writestr("XXXX.html", "<p>x</p>")
		data = buf.getvalue().replace(b"XXXX.html", "报告.html".encode("gbk"))
		path = os.path.join(self.base, "gbk.zip")
		with open(path, "wb") as f:
			f.write(data)
		core.extract_zip(path, self.target)
		self.assertEqual(core.find_entry(self.target), "报告.html")


class TestEntry(unittest.TestCase):
	def build(self, files):
		root = self.enterContext(tempfile.TemporaryDirectory())
		for f in files:
			p = os.path.join(root, f)
			os.makedirs(os.path.dirname(p), exist_ok=True)
			Path(p).write_text("x")
		return root

	def test_order(self):
		self.assertEqual(core.find_entry(self.build(["index.html", "other.html"])), "index.html")
		self.assertEqual(core.find_entry(self.build(["report/index.html", "report/a.css"])), "report/index.html")
		self.assertEqual(core.find_entry(self.build(["周报.html", "a.png"])), "周报.html")
		with self.assertRaises(core.NoEntryError):
			core.find_entry(self.build(["a.html", "b.html"]))


class TestResolve(unittest.TestCase):
	def setUp(self):
		self.root = self.enterContext(tempfile.TemporaryDirectory())
		for f in ("index.html", "page.html", "sub/index.html", "css/a.css"):
			p = os.path.join(self.root, f)
			os.makedirs(os.path.dirname(p), exist_ok=True)
			Path(p).write_text("x")
		outside = self.enterContext(tempfile.TemporaryDirectory())
		Path(outside, "secret").write_text("s")
		os.symlink(os.path.join(outside, "secret"), os.path.join(self.root, "leak"))

	def test_resolution(self):
		r = self.root
		self.assertEqual(core.resolve_request(r, "css/a.css"), ("file", os.path.realpath(os.path.join(r, "css/a.css"))))
		self.assertEqual(core.resolve_request(r, "page")[0], "file")  # nginx 去掉了 .html
		self.assertEqual(core.resolve_request(r, "sub"), ("redirect", "sub/index"))
		self.assertEqual(core.resolve_request(r, "sub/index")[0], "file")
		self.assertEqual(core.resolve_request(r, "")[0], "redirect")

	def test_blocks_escape(self):
		for rel in ("../x", "sub/../../x", "./index.html", "leak", "a\\b", "a\x00b"):
			self.assertEqual(core.resolve_request(self.root, rel), ("missing", None), rel)


if __name__ == "__main__":
	unittest.main()
