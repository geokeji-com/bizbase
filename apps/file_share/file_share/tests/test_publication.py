"""Publisher-side policy, migration and domain lifecycle, without a live site."""

from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from file_share import migrate_publication, publication as pub
from file_share.file_share.doctype.file_share_domain.file_share_domain import FileShareDomain


class Row(dict):
	__getattr__ = dict.get
	__setattr__ = dict.__setitem__
	set = dict.__setitem__

	def is_dummy_password(self, pwd):
		return bool(pwd) and set(pwd) == {"*"}

	def get_password(self, key, raise_exception=False):
		return self.get("stored_pwd")


def entry(**kw):
	return Row(dict(name="row-1", domain="a.example.com", enabled=1, access_mode="Inherit",
		version_mode="Follow", rule_epoch="r", version_epoch="v", legacy_domain_epoch="legacy") | kw)


def share(*rows, version=2, status="Active"):
	return Row(entries=rows, current_version=version, versions=[Row(version=1), Row(version=2)], status=status)


def throw(msg, *args):
	raise ValueError(msg)


class PublicationTest(TestCase):
	def setUp(self):
		p = patch.object(pub, "frappe")
		self.addCleanup(p.stop)
		self.f = p.start()
		self.f.throw.side_effect = throw
		self.f.db.get_value.return_value = "Enabled"

	def test_origin_is_an_exact_authority(self):
		self.assertEqual(pub.parse_origin("HTTPS://A.Example.com:443/"), ("a.example.com", "https://a.example.com"))
		self.assertEqual(pub.parse_origin("http://127.0.0.1:8080")[0], "127.0.0.1:8080")
		for invalid in ("https://*.example.com", "https://u@a.example.com", "https://a.example.com/p", "http://a.example.com", "https://a.example.com:99999"):
			with self.subTest(invalid=invalid), self.assertRaises(ValueError):
				pub.parse_origin(invalid)

	def test_first_publication_requires_enabled_domain_but_draft_and_withdrawal_allowed(self):
		with self.assertRaisesRegex(ValueError, "至少"):
			pub.validate_entries(share(), None, True)
		pub.validate_entries(share(version=0), None, True)
		pub.validate_entries(share(entry(enabled=0)), share(entry()), False)
		self.f.db.get_value.return_value = "Pending"
		with self.assertRaisesRegex(ValueError, "已接入"):
			pub.validate_entries(share(entry()), None, True)

	def test_duplicates_fixed_versions_and_independent_specified_users(self):
		with self.assertRaisesRegex(ValueError, "一次"):
			pub.validate_entries(share(entry(), entry()), None, True)
		with self.assertRaisesRegex(ValueError, "已有的版本"):
			pub.validate_entries(share(entry(version_mode="Pinned", pinned_version=99)), None, True)
		with self.assertRaisesRegex(ValueError, "指定用户"):
			pub.validate_entries(share(entry(access_mode="Specified")), None, True)
		self.f.db.exists.return_value = True
		r = entry(access_mode="Specified", user_list="u@example.com\nu@example.com", role_list="Sales")
		pub.validate_entries(share(r), None, True)
		self.assertEqual(r.user_list, "u@example.com")
		self.f.db.exists.assert_any_call("User", "u@example.com")
		self.f.db.exists.assert_any_call("Role", "Sales")

	def test_new_rows_cannot_use_other_report_passwords_or_ids(self):
		r = entry(name="foreign-id", access_mode="Password", password="*****")
		with self.assertRaisesRegex(ValueError, "独立密码"):
			pub.validate_entries(share(r), None, False)
		self.assertNotEqual(r.name, "foreign-id")
		r.password = "s"
		with self.assertRaisesRegex(ValueError, "至少 6"):
			pub.validate_entries(share(r), None, False)

	def test_version_changes_rotate_assets_without_resetting_login_or_other_domains(self):
		old_follow = entry(access_mode="Password", password="*****", stored_pwd="sixchars")
		old_pin = entry(name="row-2", domain="b.example.com", version_mode="Pinned", pinned_version=1)
		new_follow, new_pin = Row(old_follow), Row(old_pin)
		pub.validate_entries(share(new_follow, new_pin), share(old_follow, old_pin, version=1), False)
		self.assertEqual(new_follow.rule_epoch, old_follow.rule_epoch)
		self.assertNotEqual(new_follow.version_epoch, old_follow.version_epoch)
		self.assertFalse(new_follow.legacy_domain_epoch)
		self.assertEqual(new_pin.version_epoch, old_pin.version_epoch)
		new_follow.password = "different"
		pub.validate_entries(share(new_follow), share(old_follow), False)
		self.assertNotEqual(new_follow.rule_epoch, old_follow.rule_epoch)

	def test_global_disable_and_reenable_rotate_independent_epoch(self):
		old = Row(status="Enabled", origin="https://a.example.com", domain_epoch="first")
		d = Row(name="a.example.com", origin=old.origin, status="Disabled")
		d._origin = lambda: pub.parse_origin(d.origin)
		d.get_doc_before_save = lambda: old
		FileShareDomain.validate(d)
		self.assertNotEqual(d.domain_epoch, old.domain_epoch)
		old.status, old.domain_epoch = d.status, d.domain_epoch
		d.status = "Enabled"
		FileShareDomain.validate(d)
		self.assertNotEqual(d.domain_epoch, old.domain_epoch)
		old.status, old.domain_epoch = d.status, d.domain_epoch
		FileShareDomain.validate(d)
		self.assertEqual(d.domain_epoch, old.domain_epoch)

	def test_patch_requires_known_original_origin_for_existing_reports(self):
		with patch.object(migrate_publication, "frappe") as f:
			f.conf = {}; f.local.site = "other.site"; f.db.count.return_value = 1; f.throw.side_effect = throw
			with self.assertRaisesRegex(ValueError, "file_share_primary_origin"):
				migrate_publication.execute()
			f.get_doc.assert_not_called()

	def test_patch_only_binds_unmigrated_reports_and_does_not_reopen_withdrawals(self):
		with patch.object(migrate_publication, "frappe") as f:
			f.conf = {"file_share_primary_origin": "https://primary.example.com"}
			f.get_all.return_value = [Row(name="old", share_url="/s/old"), Row(name="new", share_url="/file-share/s/new")]
			stored = set(); inserts = []
			def exists(dt, filters):
				return dt == pub.DOMAIN or filters["parent"] in stored
			def get_doc(fields):
				inserts.append(fields)
				return Mock(db_insert=lambda: stored.add(fields["parent"]))
			f.db.exists.side_effect = exists; f.get_doc.side_effect = get_doc
			f.db.get_value.return_value = "initial"
			# Keep the SQL builder out of this lifecycle test; actual SQL is exercised on site.
			with patch.object(migrate_publication, "Concat", MagicMock()):
				migrate_publication.execute(); migrate_publication.execute()
			self.assertEqual([(r["parent"], r["domain"], r["access_mode"], r["version_mode"], r["legacy_domain_epoch"]) for r in inserts],
				[("old", "primary.example.com", "Inherit", "Follow", "initial")])
