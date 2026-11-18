"""单请求固定快照版本的只读服务和原子管理命令。"""

import json
import logging
from uuid import uuid4

import frappe

from bizbase.directory import audit, policy, snapshot
from bizbase.directory.errors import DirectoryError

STATE_KEY = "bizbase_directory_state"


def _read_state(lock=False):
    # 读取同一预置行，不能用缓存的 get_global，也不能用会删建行的 set_global。
    rows = frappe.db.sql(
        "SELECT name, defvalue FROM `tabDefaultValue` WHERE parent = %s AND defkey = %s"
        + (" FOR UPDATE" if lock else ""), ("__global", STATE_KEY), as_dict=True,
    )
    if len(rows) != 1:
        raise DirectoryError("SOURCE_UNAVAILABLE")
    try:
        state = json.loads(rows[0]["defvalue"], object_pairs_hook=snapshot._unique_object)
        if not isinstance(state, dict) or set(state) != {"enabled", "active"} or type(state["enabled"]) is not bool:
            raise ValueError()
        active = state["active"]
        if active is not None:
            if not isinstance(active, dict) or set(active) != {"filename", "sha256", "source_system", "data_as_of"}:
                raise ValueError()
            if not (snapshot.valid_filename(active["filename"]) and snapshot.valid_digest(active["sha256"])
                    and snapshot.valid_text(active["source_system"]) and snapshot.valid_date(active["data_as_of"])):
                raise ValueError()
        if state["enabled"] and active is None:
            raise ValueError()
    except (ValueError, TypeError):
        raise DirectoryError("SOURCE_UNAVAILABLE") from None
    return rows[0]["name"], state


def _load_active(active):
    try:
        data = snapshot.load_snapshot(active["filename"], active["sha256"])
        if data["source_system"] != active["source_system"] or data["data_as_of"] != active["data_as_of"]:
            raise snapshot.SnapshotError()
        return data
    except snapshot.SnapshotError:
        raise DirectoryError("SOURCE_UNAVAILABLE") from None


def _validate_arguments(action, query, source_system, customer_id, extra):
    allowed = {"cmd", "query"}
    if action == "list_subjects":
        allowed |= {"source_system", "customer_id"}
    elif action != "list_customers":
        raise DirectoryError("INVALID_ARGUMENT")
    supplied = set(getattr(frappe.local, "form_dict", {}) or {}) | set(extra or {})
    request = getattr(frappe.local, "request", None)
    if request is not None:
        # Frappe 会提前移除 ajax 的 `_`；在本入口仍按严格白名单拒绝。
        for collection in (request.args, request.form):
            supplied |= set(collection)
            if any(len(collection.getlist(key)) != 1 for key in collection):
                raise DirectoryError("INVALID_ARGUMENT")
        if request.is_json and request.get_data():
            try:
                body = json.loads(request.get_data(), object_pairs_hook=snapshot._unique_object)
            except (ValueError, TypeError, RecursionError):
                raise DirectoryError("INVALID_ARGUMENT") from None
            if not isinstance(body, dict):
                raise DirectoryError("INVALID_ARGUMENT")
            supplied |= set(body)
    if supplied - allowed or set(extra or {}) - {"cmd"}:
        raise DirectoryError("INVALID_ARGUMENT")
    if query is not None and (not isinstance(query, str) or len(query) > 200
                              or any(ord(c) < 32 or ord(c) == 127 for c in query)):
        raise DirectoryError("INVALID_ARGUMENT")
    if action == "list_subjects" and not all(snapshot.valid_text(value) for value in (source_system, customer_id)):
        raise DirectoryError("INVALID_ARGUMENT")
    return (query or "").strip().casefold()


def _meta(active, request_id):
    return {"mode": "snapshot", "source_system": active["source_system"],
            "version": active["sha256"], "data_as_of": active["data_as_of"], "request_id": request_id}


def _error_response(error, request_id):
    frappe.local.response["http_status_code"] = error.status
    # 原生日志写入失败可能通过 frappe.throw 留下 message_log；不把底层错误带出业务边界。
    frappe.local.message_log = []
    for key in ("exc", "exc_type", "exception", "_server_messages", "_debug_messages"):
        frappe.local.response.pop(key, None)
    return error.response(request_id)


def read_directory(action, *, query=None, source_system=None, customer_id=None, extra=None):
    """只能由只读 RPC 调用：审计持久化会提交当前事务。"""
    request_id = uuid4().hex
    user = policy.actor()
    version = None
    result = None
    error = None
    try:
        needle = _validate_arguments(action, query, source_system, customer_id, extra)
        try:
            policy.require_reader()
        except DirectoryError:
            raise DirectoryError("NOT_FOUND" if action == "list_subjects" else "FORBIDDEN") from None
        grants = policy.allowed_references(user)
        if action == "list_subjects":
            if not any(g["source_system"] == source_system and g["source_customer_id"] == customer_id for g in grants):
                raise DirectoryError("NOT_FOUND")
        elif not grants:
            raise DirectoryError("FORBIDDEN")
        _, state = _read_state()
        if not state["enabled"]:
            raise DirectoryError("DIRECTORY_DISABLED")
        active = state["active"]
        version = active["sha256"]
        if action == "list_subjects" and active["source_system"] != source_system:
            raise DirectoryError("NOT_FOUND")
        allowed = {g["source_customer_id"] for g in grants if g["source_system"] == active["source_system"]}
        if not allowed:
            raise DirectoryError("FORBIDDEN")
        data = _load_active(active)
        customers = {c["customer_id"]: c for c in data["customers"] if c["customer_id"] in allowed}
        if action == "list_customers":
            if not customers:
                raise DirectoryError("FORBIDDEN")
            items = [{"customer_id": c["customer_id"], "name": c["name"]}
                     for c in customers.values()
                     if not needle or needle in c["name"].casefold() or needle in c["customer_id"].casefold()]
            result = {"items": items, "meta": _meta(active, request_id)}
        else:
            if customer_id not in customers:
                raise DirectoryError("NOT_FOUND")
            items = [{key: s[key] for key in ("subject_id", "customer_id", "name", "source_type")}
                     for s in data["subjects"] if s["customer_id"] == customer_id
                     and (not needle or needle in s["name"].casefold() or needle in s["subject_id"].casefold())]
            result = {"items": items, "meta": _meta(active, request_id),
                      "customer": {"customer_id": customer_id, "name": customers[customer_id]["name"]}}
    except DirectoryError as exc:
        error = exc
    except Exception:
        # DB/配置/解析未知故障均失败关闭，不把异常文本或 traceback 输出给请求方。
        error = DirectoryError("SOURCE_UNAVAILABLE")
        audit.rollback_safely()
        logging.getLogger("bizbase.directory").error("directory_read_unavailable request_id=%s", request_id)
    try:
        audit.persist(actor=user, action=action, outcome=error.code if error else ("success" if result["items"] else "empty"),
                      request_id=request_id, version=version, count=len(result["items"]) if result else 0)
    except DirectoryError as exc:
        error = exc
    if error:
        return _error_response(error, request_id)
    frappe.local.response["http_status_code"] = 200
    return result


def _update_state(name, state):
    frappe.db.sql("UPDATE `tabDefaultValue` SET defvalue = %s WHERE name = %s",
                  (json.dumps(state, ensure_ascii=False, separators=(",", ":")), name))


def _prepare_references(data):
    for customer in data["customers"]:
        existing = frappe.db.sql(
            "SELECT name, display_name FROM `tabBB Customer Reference` WHERE source_system = %s AND source_customer_id = %s",
            (data["source_system"], customer["customer_id"]), as_dict=True,
        )
        if existing:
            if existing[0]["display_name"] != customer["name"]:
                doc = frappe.get_doc(policy.REFERENCE, existing[0]["name"])
                doc.display_name = customer["name"]
                doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({"doctype": policy.REFERENCE, "source_system": data["source_system"],
                            "source_customer_id": customer["customer_id"], "display_name": customer["name"]}).insert(ignore_permissions=True)


def _management_failure(exc, *, actor, action, request_id, version):
    audit.rollback_safely()
    error = exc if isinstance(exc, DirectoryError) else DirectoryError("SOURCE_UNAVAILABLE")
    audit.persist(actor=actor, action=action, outcome=error.code, request_id=request_id, version=version)
    raise error from None


def activate(filename, sha256):
    """bench / 配置管理员内部命令：准备全部引用后原子启用。不是 whitelisted API。"""
    request_id = uuid4().hex
    user = policy.actor()
    version = sha256 if snapshot.valid_digest(sha256) else None
    try:
        policy.require_manager()
        data = snapshot.load_snapshot(filename, sha256)
        row_name, _ = _read_state(lock=True)
        _prepare_references(data)
        active = {"filename": filename, "sha256": sha256,
                  "source_system": data["source_system"], "data_as_of": data["data_as_of"]}
        _update_state(row_name, {"enabled": True, "active": active})
        audit.persist(actor=user, action="activate", outcome="activated", request_id=request_id,
                      version=sha256, count=len(data["customers"]), commit=False)
        frappe.db.commit()
        return {"enabled": True, "meta": _meta(active, request_id)}
    except Exception as exc:
        _management_failure(exc, actor=user, action="activate", request_id=request_id, version=version)


def set_enabled(enabled):
    """与版本切换锁住同一状态行；关闭保留已有版本和引用。"""
    request_id = uuid4().hex
    user = policy.actor()
    version = None
    try:
        policy.require_manager()
        if type(enabled) is not bool:
            raise DirectoryError("INVALID_ARGUMENT")
        row_name, state = _read_state(lock=True)
        if state["active"]:
            version = state["active"]["sha256"]
        if enabled:
            if state["active"] is None:
                raise DirectoryError("SOURCE_UNAVAILABLE")
            _load_active(state["active"])
        state["enabled"] = enabled
        _update_state(row_name, state)
        audit.persist(actor=user, action="set_enabled", outcome="enabled" if enabled else "disabled",
                      request_id=request_id, version=version, commit=False)
        frappe.db.commit()
        return {"enabled": enabled, "request_id": request_id,
                "meta": _meta(state["active"], request_id) if state["active"] else None}
    except Exception as exc:
        _management_failure(exc, actor=user, action="set_enabled", request_id=request_id, version=version)
