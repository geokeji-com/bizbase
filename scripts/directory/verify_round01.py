#!/usr/bin/env python3
"""公开合成检查或完整本地验收；完整模式不得静默跳过真实数据或浏览器。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

import bootstrap as infra


def public_checks():
    infra.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/directory/unit", "-v"])
    infra.run([sys.executable, "-m", "compileall", "-q", "apps/bizbase", "scripts/directory"])
    for file in [*Path(infra.ROOT / "apps/bizbase").rglob("*.js"), *Path(infra.ROOT / "prototypes/directory").glob("*.js"), *Path(infra.ROOT / "tests/directory/browser").glob("*.mjs")]:
        infra.run(["node", "--check", str(file)])
    infra.run(["git", "diff", "--check"])


def preserved_original():
    for line in (infra.PRIVATE / "original-runtime.txt").read_text().splitlines():
        name, identifier, image, *mounts = line.split()
        info = json.loads(infra.run(["docker", "inspect", name], capture=True))[0]
        assert info["Id"] == identifier and info["Image"] == image, "Original runtime identity changed"
        actual = sorted(f'{m.get("Name", "")}:{m["Destination"]}' for m in info["Mounts"])
        assert actual == sorted(mounts), "Original mounts changed"
        assert info["State"]["Running"], "Original service stopped"
    with urllib.request.urlopen("http://localhost:8080/login", timeout=15) as response:
        assert response.status == 200


def private_scan():
    data = json.loads((infra.PRIVATE / "snapshot-s01.json").read_text())
    credentials = json.loads((infra.PRIVATE / "credentials.json").read_text())
    forbidden = []
    for customer in data["customers"]:
        forbidden.extend([customer["customer_id"], customer["name"]])
    for subject in data["subjects"]:
        forbidden.extend([subject["subject_id"], subject["name"]])
    for account in credentials["accounts"].values():
        forbidden.extend([account["password"], account["api_key"], account["api_secret"]])
    forbidden += [v for k, v in infra.load_env().items() if "PASSWORD" in k]
    for directory in ("apps/bizbase", "deploy/local-directory", "scripts/directory", "prototypes/directory", "tests/directory", "docs/cycle/rounds/01"):
        for file in (infra.ROOT / directory).rglob("*"):
            if file.is_file() and not {"node_modules", "__pycache__"}.intersection(file.parts):
                raw = file.read_bytes()
                assert not any(value.encode() in raw for value in forbidden), f"Private material in public source: {file.relative_to(infra.ROOT)}"
    # 镜像中的 App 源码与本机一致，挂载数据只在私有只读卷；不从站点或源文件扫描出内容。
    import site_ops
    image_clean = site_ops.execute('''
from pathlib import Path
root=Path("/home/frappe/frappe-bench/apps/bizbase")
assert root.is_dir()
bad=[]
for file in root.rglob("*"):
    if file.is_file() and "__pycache__" not in file.parts:
        raw=file.read_bytes()
        if any(value.encode() in raw for value in payload["forbidden"]): bad.append(str(file.relative_to(root)))
result={"clean":not bad,"bad_paths":bad}
''', {"forbidden": forbidden})
    assert image_clean["clean"], "Private material baked into app image"


def full_checks():
    infra.load_env()
    infra.validate_config()
    assert (infra.PRIVATE / "snapshot-s01.json").is_file(), "Real snapshot is required"
    assert (infra.ROOT / "tests/directory/browser/node_modules/playwright-core").is_dir(), "Install pinned browser dependencies"
    preserved_original()
    build = json.loads((infra.PRIVATE / "build.json").read_text())
    container = infra.compose("ps", "-q", "backend", capture=True).strip()
    info = json.loads(infra.run(["docker", "inspect", container], capture=True))[0]
    assert info["Image"] == build["image_id"], "Running artifact differs from recorded build"
    assert any(m["Destination"] == "/run/bizbase-directory" and not m["RW"] for m in info["Mounts"])
    restore = infra.PRIVATE / "last-restore.json"
    pending_restore = json.loads(restore.read_text()) if restore.exists() else {}
    restoring = pending_restore.get("business_reverification_required", False)
    if restoring:
        from site_ops import directory_fingerprint
        assert pending_restore["image_id"] == info["Image"]
        assert directory_fingerprint() == pending_restore["expected_directory_fingerprint"], "Restored state differs before any seed or migration"
        # 先用恢复前的凭据做只读查询；禁止 seed 掩盖授权、版本或账号丢失。
        from http_checks import Client
        creds = json.loads((infra.PRIVATE / "credentials.json").read_text())
        for actor, token in (("reader", False), ("client", True)):
            status, payload = Client(creds["accounts"][actor], token=token).directory()
            assert status == 200 and payload["message"]["items"], "Restored credentials or scope unusable"
        print("Restored directory state and credentials verified before mutation")
    migration = infra.compose("exec", "-T", "backend", "bench", "--site", infra.SITE, "migrate", capture=True)
    infra.private_write(infra.PRIVATE / "evidence/migration.txt", migration)
    print("Isolated migrations applied")
    infra.compose("exec", "-T", "backend", "bench", "--site", infra.SITE, "clear-cache")
    if not restoring:
        from seed_demo import seed
        seed()
    output = infra.compose("exec", "-T", "backend", "bench", "--site", infra.SITE, "run-tests", "--app", "bizbase", capture=True)
    infra.private_write(infra.PRIVATE / "evidence/integration.txt", output)
    assert "Ran 4 tests" in output and "Ran 15 tests" in output and "FAILED" not in output and "skipped=" not in output, "Required integration test evidence absent"
    print("Frappe integration suite passed")
    from http_checks import verify
    checks = verify()
    infra.run(["node", "tests/directory/browser/acceptance.mjs"])
    private_scan()
    preserved_original()
    result = {"passed": True, "verified_at": datetime.now(timezone.utc).isoformat(), "image_id": info["Image"], "build": build, "http_checks": checks, "private_material_scan": "passed", "original_runtime": "preserved", "browser": "passed"}
    directory = infra.PRIVATE / "evidence"
    directory.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    infra.private_write(directory / f"run-{stamp}.json", json.dumps(result, indent=2) + "\n")
    infra.private_write(directory / "latest-run.json", json.dumps(result, indent=2) + "\n")
    if restore.exists():
        record = json.loads(restore.read_text())
        if record["image_id"] == info["Image"]:
            record.update(business_reverification_required=False, verified_at=result["verified_at"])
            infra.private_write(restore, json.dumps(record, indent=2) + "\n")
    print("Round 01 full local acceptance passed; private evidence saved")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", action="store_true", help="Only public synthetic checks; never counts as full acceptance")
    args = parser.parse_args()
    public_checks()
    if not args.public:
        full_checks()
    else:
        print("Public checks passed; real-site acceptance was not run")


if __name__ == "__main__":
    main()
