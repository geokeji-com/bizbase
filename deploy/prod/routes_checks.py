"""Checks for routes_window.sh. Host, workstation and container modes import separately."""
import hashlib
import json
import os
import re
import sys
import tarfile
from pathlib import Path

SITE = "bizbase.geokeji.com"
BOARDS = ("bizbase_mgmt", "sales_board", "ops_board", "customer_board")
INVENTORY = set("shares bindings Version Role User logs attachments passwords blocked".split())
HEX = r"[0-9a-f]{64}"


def need(value, message):
    if not value:
        raise SystemExit(message)


def sha(stream):
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        h.update(block)
    return h.hexdigest()


def replay(path, tools, old, new):
    root = Path(path)
    need(root.parent == Path("/var/lib/bizbase-rehearsals") and root.resolve() == root, "invalid replay path")
    for item in (root, root / "apply-ok", root / "review.json"):
        st = item.lstat()
        need(st.st_uid == 0 and not st.st_mode & 0o077 and not item.is_symlink(), "unsafe replay evidence")
    need((root / "apply-ok").is_file(), "completed apply required")
    evidence = json.loads((root / "review.json").read_text())
    for tag, image in (("clarity-kshhri", old), ("routes-candidate", new)):
        need(evidence["images"]["bizbase/prod:" + tag] == image, "image differs from replay: " + tag)
    hashes = evidence["tools"]
    need({"rehearse_routes.py", "rehearsal_checks.py", "rename_yishan_id.py", "rename_file_share.py", "preserve_geo.py"} <= hashes.keys(), "replay must include GEO preservation")
    for name, expected in hashes.items():
        need(Path(name).name == name, "invalid replay tool name")
        with (Path(tools) / name).open("rb") as f:
            need(sha(f) == expected, "script differs from replay: " + name)


def queue():
    # Raw counts avoid RQ registry cleanup and never fetch, deserialize or delete jobs.
    from redis import Redis
    from rq import Queue
    from rq.registry import StartedJobRegistry, DeferredJobRegistry, ScheduledJobRegistry
    sites = Path("/home/frappe/frappe-bench/sites")
    cfg = json.loads((sites / "common_site_config.json").read_text())
    cfg.update(json.loads((sites / SITE / "site_config.json").read_text()))
    need(cfg["bench_id"] == "bizbase-prod", "unexpected queue namespace")
    from urllib.parse import urlsplit
    need(urlsplit(cfg["redis_queue"]).path == "/4", "unexpected queue database")
    conn = Redis.from_url(cfg["redis_queue"], socket_timeout=10)
    names = set(cfg.get("workers", {})) | {"short", "default", "long"}
    prefix = "rq:queue:bizbase-prod:"
    for registered in conn.smembers("rq:queues"):
        key = registered.decode()
        if key.startswith(prefix):
            names.add(key[len(prefix):])
    for name in sorted(names):
        q = Queue("bizbase-prod:" + name, connection=conn)
        counts = [conn.llen(q.key), conn.llen(q.intermediate_queue_key)]
        counts += [conn.zcard(r(queue=q).key) for r in (StartedJobRegistry, DeferredJobRegistry, ScheduledJobRegistry)]
        need(not any(counts), "queue requires operator review: " + name + " " + str(counts))
    print("queue clear")


def business(side):
    import frappe
    import types
    # D one-shots take stdin. Load the two replay-pinned modules without a host write mount.
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as source:
        for item in source:
            name = Path(item.name).stem
            need(name in ("preserve_geo", "rehearsal_checks") and item.isfile(), "unexpected replay module")
            module = types.ModuleType(name)
            module.__file__ = item.name
            sys.modules[name] = module
            exec(compile(source.extractfile(item).read(), item.name, "exec"), module.__dict__)
    import preserve_geo as geo
    import rehearsal_checks as checks
    checks.SITE = SITE
    os.chdir("/home/frappe/frappe-bench/sites")
    frappe.init(site=SITE)
    frappe.connect()
    try:
        frappe.set_user("Administrator")
        new = side == "new"
        checks.apps(frappe, checks.RENAMED | {"crm", "insights", *BOARDS} if new else checks.LEGACY)
        raw = geo.read_private(Path.cwd() / SITE / "private" / geo.ARCHIVE) if new else geo.audit(frappe)
        if new:
            geo.verified(frappe, geo.validate(raw))
            geo.verify_boards(frappe)
        data = checks.snapshot(frappe, new, raw)
        def fingerprint(values):
            return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        files = []
        root = Path(SITE)
        for folder in (root / "private/files", root / "public/files"):
            need(folder.is_dir(), "missing site files directory")
            for item in sorted(folder.rglob("*")):
                need(not item.is_symlink(), "symlink in file tree requires review")
                if item.is_file():
                    with item.open("rb") as f:
                        files.append((str(item.relative_to(root)), sha(f)))
        print(json.dumps(dict(replay=data, files=fingerprint(files)), sort_keys=True))
    finally:
        frappe.db.rollback()
        frappe.destroy()


def compare(folder):
    p = Path(folder)
    def inventory(side):
        parsed = {}
        for line in (p / (side + ".inventory")).read_text().splitlines():
            label, n, h = line.split()
            need(label not in parsed and n.isdigit() and re.fullmatch(HEX, h), "invalid inventory row")
            parsed[label] = (n, h)
        need(parsed.keys() == INVENTORY, "incomplete inventory")
        return parsed
    def permissions(side):
        obj = json.loads((p / (side + ".business")).read_text())
        need(obj.keys() == {"replay", "files"} and re.fullmatch(HEX, obj["files"]) and {"share visibility", "record grants", "geo_archive", "blocks", "share content"} <= obj["replay"].keys(), "incomplete business checks")
        return obj
    for read in (inventory, permissions):
        a, b = read("old"), read("new")
        need(a == b, "offline mismatch: " + ", ".join(k for k in a if a[k] != b[k]))
    h = hashlib.sha256()
    for name in ("id", "old.inventory", "new.inventory", "old.business", "new.business", "preview.ok"):
        data = (p / name).read_bytes()
        h.update(len(data).to_bytes(8, "big") + data)
    print(h.hexdigest())


def archive(backup_id, baseline_file):
    # Only read members, never extract a production backup onto the workstation.
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as t:
        sums = {}; receipt = None; expected = None
        for item in t:
            need(item.isfile() and item.name not in sums, "unexpected archive member")
            f = t.extractfile(item)
            if item.name == "SHA256SUMS":
                need(item.size < 8192, "invalid checksum list")
                raw = f.read(); expected = raw.decode().splitlines()
                sums[item.name] = hashlib.sha256(raw).hexdigest()
            elif item.name == "id":
                raw = f.read(128); need(raw == (backup_id + "\n").encode(), "wrong archived backup id")
                sums[item.name] = hashlib.sha256(raw).hexdigest()
            elif item.name == "receipt":
                raw = f.read(128); receipt = raw.decode().strip()
                need(re.fullmatch(HEX, receipt), "invalid archive receipt")
                sums[item.name] = hashlib.sha256(raw).hexdigest()
            else:
                sums[item.name] = sha(f)
    # Consume tar padding as well so a valid openssl producer never receives SIGPIPE.
    while sys.stdin.buffer.read(1024 * 1024):
        pass
    sums.pop("SHA256SUMS", None)
    need(set(sums) == {"id", "bizbase_app.dump", "manifest.json", "geo-preservation-v1.json", "sites.tar", "host.tar", "old.inventory", "receipt"}, "incomplete coordinated archive")
    need(expected and sorted(expected) == sorted(h + "  " + n for n, h in sums.items()), "archive digest mismatch")
    Path(baseline_file).write_text(sums["old.inventory"] + "\n")
    print(receipt)


if __name__ == "__main__":
    {"queue": queue, "business": business, "replay": replay, "compare": compare, "archive": archive}[sys.argv[1]](*sys.argv[2:])
