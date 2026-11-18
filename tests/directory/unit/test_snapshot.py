"""公开 CI 只运行合成快照验证，不连接站点、不读取私有样本。"""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[3] / "apps/bizbase/bizbase/directory/snapshot.py"
SPEC = importlib.util.spec_from_file_location("directory_snapshot_under_test", MODULE)
snapshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)


def fixture():
    return {
        "schema_version": 1,
        "source_system": "synthetic-public-ci",
        "data_as_of": "2026-11-02",
        "customers": [{"customer_id": "customer-1", "name": "合成客户"}],
        "subjects": [{"subject_id": "subject-1", "customer_id": "customer-1", "name": "合成对象", "source_type": None}],
    }


class TestSnapshotSchema(unittest.TestCase):
    def test_complete_snapshot_and_missing_classification(self):
        data = fixture()
        self.assertEqual(snapshot.validate_snapshot(data), data)
        data["subjects"] = []
        self.assertEqual(snapshot.validate_snapshot(data)["subjects"], [])

    def test_exact_keys_reject_sensitive_fields_at_each_level(self):
        for where, key in [("root", "credentials"), ("customers", "parent_id"), ("customers", "tax_number"), ("subjects", "members")]:
            with self.subTest(where=where, key=key):
                data = fixture()
                target = data if where == "root" else data[where][0]
                target[key] = "不应进入快照"
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.validate_snapshot(data)

    def test_missing_required_fields(self):
        for where in ("root", "customers", "subjects"):
            original = fixture() if where == "root" else fixture()[where][0]
            for key in original:
                with self.subTest(where=where, key=key):
                    data = fixture()
                    del (data if where == "root" else data[where][0])[key]
                    with self.assertRaises(snapshot.SnapshotError):
                        snapshot.validate_snapshot(data)

    def test_invalid_version_dates_types_and_source(self):
        cases = [("schema_version", True), ("schema_version", 2), ("schema_version", "1"),
                 ("data_as_of", "2026-02-30"), ("data_as_of", "2026-1-02"),
                 ("data_as_of", 20261102), ("source_system", ""),
                 ("customers", {}), ("subjects", None)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                data = fixture()
                data[key] = value
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.validate_snapshot(data)
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.validate_snapshot(fixture(), expected_source="another-source")

    def test_id_uniqueness_and_foreign_key(self):
        for collection in ("customers", "subjects"):
            data = fixture()
            data[collection].append(copy.deepcopy(data[collection][0]))
            with self.subTest(collection=collection), self.assertRaises(snapshot.SnapshotError):
                snapshot.validate_snapshot(data)
        data = fixture()
        data["subjects"][0]["customer_id"] = "missing-customer"
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.validate_snapshot(data)

    def test_strings_are_strict_and_unknown_type_is_only_null(self):
        for key in ("subject_id", "customer_id", "name", "source_type"):
            for invalid in ("", " leading", "trailing ", "nul\x00value", "line\nvalue", "\ud800", 1, [], "x" * 141):
                with self.subTest(key=key, value=repr(invalid)):
                    data = fixture()
                    data["subjects"][0][key] = invalid
                    with self.assertRaises(snapshot.SnapshotError):
                        snapshot.validate_snapshot(data)


class TestSnapshotFiles(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bb-directory-public-ci-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.root_patch = patch.object(snapshot, "SNAPSHOT_ROOT", str(self.root))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def write(self, raw=None, name="snapshot.json"):
        raw = raw if raw is not None else json.dumps(fixture(), ensure_ascii=False).encode()
        (self.root / name).write_bytes(raw)
        return name, hashlib.sha256(raw).hexdigest()

    def test_round_trip(self):
        self.assertEqual(snapshot.load_snapshot(*self.write()), fixture())

    def test_missing_corrupt_digest_and_duplicate_json_keys(self):
        bad_raw = (b"not-json", b"\xff", b'{"schema_version":1,"schema_version":1}',
                   b'{"schema_version":NaN}', b"[1,2,3]")
        for raw in bad_raw:
            with self.subTest(raw=raw), self.assertRaises(snapshot.SnapshotError):
                snapshot.load_snapshot(*self.write(raw))
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.load_snapshot("absent.json", "0" * 64)
        name, _ = self.write()
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.load_snapshot(name, "0" * 64)

    def test_path_traversal_and_invalid_digests(self):
        name, digest = self.write()
        for invalid in ("../snapshot.json", "/tmp/snapshot.json", "a/../snapshot.json", "x..json", "snapshot.txt", "snapshot.json\x00"):
            with self.subTest(filename=invalid), self.assertRaises(snapshot.SnapshotError):
                snapshot.load_snapshot(invalid, digest)
        for invalid in (None, digest.upper(), digest[:-1], "g" * 64, " " + digest):
            with self.subTest(digest=invalid), self.assertRaises(snapshot.SnapshotError):
                snapshot.load_snapshot(name, invalid)

    def test_symlinks_and_non_regular_files_are_rejected(self):
        name, digest = self.write()
        (self.root / "link.json").symlink_to(self.root / name)
        os.mkfifo(self.root / "pipe.json")
        (self.root / "directory.json").mkdir()
        for invalid in ("link.json", "pipe.json", "directory.json"):
            with self.subTest(filename=invalid), self.assertRaises(snapshot.SnapshotError):
                snapshot.load_snapshot(invalid, digest)
        linked_root = self.root / "root-link"
        linked_root.symlink_to(self.root, target_is_directory=True)
        with patch.object(snapshot, "SNAPSHOT_ROOT", str(linked_root)), self.assertRaises(snapshot.SnapshotError):
            snapshot.load_snapshot(name, digest)

    def test_byte_and_record_limits(self):
        with patch.object(snapshot, "MAX_BYTES", 16), self.assertRaises(snapshot.SnapshotError):
            snapshot.load_snapshot(*self.write())
        with patch.object(snapshot, "MAX_RECORDS", 0), self.assertRaises(snapshot.SnapshotError):
            snapshot.validate_snapshot(fixture())


if __name__ == "__main__":
    unittest.main()
