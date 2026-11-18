"""固定私有根下的完整快照验证；本模块不依赖 Frappe。"""

import hashlib
import json
import os
import re
import stat
from datetime import date

SNAPSHOT_ROOT = "/run/bizbase-directory"
MAX_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 100_000


class SnapshotError(ValueError):
    """仅暴露固定文本，不包含文件路径或原始内容。"""

    def __init__(self):
        super().__init__("目录快照不可用")


def _keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise SnapshotError()


def valid_text(value, limit=140):
    return (
        isinstance(value, str)
        and 0 < len(value) <= limit
        and value == value.strip()
        and not any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    )


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def valid_filename(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,190}\.json", value)) and ".." not in value


def valid_digest(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def validate_snapshot(data, expected_source=None):
    """严格校验完整 schema 与外键，成功返回原 dict；失败抛 SnapshotError。"""
    _keys(data, ("schema_version", "source_system", "data_as_of", "customers", "subjects"))
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise SnapshotError()
    if not valid_text(data["source_system"]) or not valid_date(data["data_as_of"]):
        raise SnapshotError()
    if expected_source is not None and data["source_system"] != expected_source:
        raise SnapshotError()
    for collection in ("customers", "subjects"):
        if not isinstance(data[collection], list) or len(data[collection]) > MAX_RECORDS:
            raise SnapshotError()
    customers = set()
    for customer in data["customers"]:
        _keys(customer, ("customer_id", "name"))
        if not all(valid_text(customer[key]) for key in customer) or customer["customer_id"] in customers:
            raise SnapshotError()
        customers.add(customer["customer_id"])
    subjects = set()
    for subject in data["subjects"]:
        _keys(subject, ("subject_id", "customer_id", "name", "source_type"))
        if not all(valid_text(subject[key]) for key in ("subject_id", "customer_id", "name")):
            raise SnapshotError()
        if subject["source_type"] is not None and not valid_text(subject["source_type"]):
            raise SnapshotError()
        if subject["subject_id"] in subjects or subject["customer_id"] not in customers:
            raise SnapshotError()
        subjects.add(subject["subject_id"])
    return data


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SnapshotError()
        value[key] = item
    return value


def load_snapshot(filename, sha256):
    """仅读固定根的普通文件；单个 fd 固定字节及版本，拒绝符号链接。"""
    if not valid_filename(filename) or not valid_digest(sha256):
        raise SnapshotError()
    root_fd = file_fd = None
    try:
        root_fd = os.open(SNAPSHOT_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        file_fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise SnapshotError()
        with os.fdopen(file_fd, "rb") as source:
            file_fd = None
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != sha256:
            raise SnapshotError()
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=lambda _value: (_ for _ in ()).throw(SnapshotError()))
        return validate_snapshot(data)
    except (OSError, ValueError, TypeError, RecursionError):
        raise SnapshotError() from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if root_fd is not None:
            os.close(root_fd)
