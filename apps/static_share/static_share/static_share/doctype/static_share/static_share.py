"""分享记录：上传处理、版本、访问设置变更时轮换凭证。"""

import os
import secrets
import shutil
import string

import frappe
from frappe import _
from frappe.model.document import Document

from static_share import core
from static_share.permissions import is_employee, is_manager

ACCESS_FIELDS = ("access_level", "status")
ALPHABET = string.ascii_letters + string.digits
MIN_PASSWORD = 6


def content_base() -> str:
	return frappe.get_site_path("private", "files", ".static_share")


class StaticShare(Document):
	def autoname(self):
		while True:
			name = "".join(secrets.choice(ALPHABET) for _ in range(10))
			if not frappe.db.exists("Static Share", name):
				self.name = name
				return

	def validate(self):
		before = self.get_doc_before_save()
		user = frappe.session.user
		# Frappe checks some permissions against the submitted document. Use the locked DB owner.
		if before and (self.owner != before.owner or (before.owner != user and not is_manager(user))):
			frappe.throw(_("You cannot manage this share"), frappe.PermissionError)
		if not self.name or len(self.name) != 10 or any(c not in ALPHABET for c in self.name):
			frappe.throw(_("Invalid share ID"))
		# Link rows can come from REST as well as Table MultiSelect. Only update this share's rows.
		for field in ("allowed_users", "allowed_roles"):
			trusted_ids = {r.name for r in before.get(field)} if before else set()
			for row in self.get(field):
				if row.name not in trusted_ids:
					row.name = None
		self._validate_versions(before)
		if not is_employee(user):
			# Managers without an Employee record can take down existing material only.
			if not (before and is_manager(user) and self.status == "Disabled" and
					all(self.get(k) == before.get(k) for k in ("upload", "title", "description", "current_version")) and
					not self._access_changed(before, include_status=False)):
				frappe.throw(_("Only active employees with Desk access can publish"), frappe.PermissionError)
		self._validate_access()
		if not before or before.upload != self.upload:
			self._ingest_upload()
		elif not any(v.version == self.current_version for v in self.versions):
			frappe.throw(_("Version {0} does not exist").format(self.current_version))
		self.share_url = f"/file-share/{self.name}"
		if not before or self._access_changed(before) or before.current_version != self.current_version:
			self.access_salt = secrets.token_hex(16)
		else:
			self.access_salt = before.access_salt

	def _validate_versions(self, before):
		# Read-only fields in Desk are still writable in REST payloads. Compare with locked rows,
		# including row identities. Always rebuild the table from the trusted DB representation.
		fields = ("name", "version", "entry", "file_count", "total_size", "source_file", "uploaded_by", "uploaded_on")
		def snapshot(rows):
			return [tuple(str(row.get(k)) for k in fields) for row in rows]
		trusted = before.versions if before else []
		if snapshot(self.versions) != snapshot(trusted):
			frappe.throw(_("Version history is managed by the server"))
		self.set("versions", [row.as_dict() for row in trusted])

	def _validate_access(self):
		if self.access_level == "Password":
			pwd = self.get("password") or ""
			if self.is_dummy_password(pwd) and not self.get_password(raise_exception=False):
				frappe.throw(_("Enter an access password"))
			if not self.is_dummy_password(pwd) and len(pwd) < MIN_PASSWORD:
				frappe.throw(_("Password must be at least {0} characters").format(MIN_PASSWORD))
		if self.access_level == "Specified" and not (self.allowed_users or self.allowed_roles):
			frappe.throw(_("Add at least one allowed user or role"))

	def _access_changed(self, before, include_status=True) -> bool:
		if not before:
			return True
		pwd = self.get("password") or ""
		if pwd and not self.is_dummy_password(pwd):
			return True
		if any(before.get(f) != self.get(f) for f in (ACCESS_FIELDS if include_status else ("access_level",))):
			return True
		users = lambda d: sorted(r.user for r in d.allowed_users)  # noqa: E731
		roles = lambda d: sorted(r.role for r in d.allowed_roles)  # noqa: E731
		return users(before) != users(self) or roles(before) != roles(self)

	def _ingest_upload(self):
		url = self.upload or ""
		if not url.startswith("/private/files/") or "/" in url.removeprefix("/private/files/"):
			frappe.throw(_("Choose a private local source file"))
		name = frappe.db.get_value("File", {"file_url": url, "is_private": 1, "owner": frappe.session.user}, "name")
		if not name:
			frappe.throw(_("You can only publish private files you uploaded yourself"), frappe.PermissionError)
		file = frappe.get_doc("File", name)
		file.check_permission("read")
		source = os.path.realpath(file.get_full_path())
		private = os.path.realpath(frappe.get_site_path("private", "files"))
		if os.path.dirname(source) != private or not os.path.isfile(source):
			frappe.throw(_("Choose a private local source file"))

		version = max((v.version for v in self.versions), default=0) + 1
		root = os.path.join(content_base(), self.name)
		os.makedirs(root, exist_ok=True)
		target = os.path.join(root, str(version))
		if os.path.lexists(target):
			frappe.throw(_("Version directory already exists"))

		lower = url.lower()
		try:
			if lower.endswith(".zip"):
				count, size = core.extract_zip(source, target)
				frappe.db.after_rollback.add(lambda: shutil.rmtree(target, ignore_errors=True))
				entry = core.find_entry(target)
			elif lower.endswith(core.HTML_SUFFIXES):
				with open(source, "rb") as f:
					if os.fstat(f.fileno()).st_size > core.MAX_TOTAL_BYTES:
						frappe.throw(_("File is too large"))
					count, size = core.store_single_html(f.read(), target)
				frappe.db.after_rollback.add(lambda: shutil.rmtree(target, ignore_errors=True))
				entry = "index.html"
			else:
				frappe.throw(_("Only .html, .htm or .zip files can be published"))
		except (core.UnsafeArchiveError, core.NoEntryError) as e:
			frappe.throw(str(e))

		self.append(
			"versions",
			{
				"version": version,
				"entry": entry,
				"file_count": count,
				"total_size": size,
				"source_file": url,
				"uploaded_by": frappe.session.user,
				"uploaded_on": frappe.utils.now_datetime(),
			},
		)
		self.current_version = version

	def entry_for_current(self) -> str | None:
		for v in self.versions:
			if v.version == self.current_version:
				return v.entry
		return None

	def on_trash(self):
		root = os.path.join(content_base(), self.name)
		frappe.db.after_commit.add(lambda: shutil.rmtree(root, ignore_errors=True))
