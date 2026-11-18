#!/usr/bin/env python3
"""本轮隔离站点的可核对检查点；恢复要求当前镜像与检查点完全一致。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import bootstrap as infra

CHECKPOINTS = infra.PRIVATE / "checkpoints"
CONTAINER_ROOT = "/tmp/bizbase-r01-recovery"


def backend_identity() -> tuple[str, str]:
    active = infra.compose("ps", "--services", "--status", "running", capture=True).splitlines()
    if any(service in active for service in ("worker", "scheduler")):
        raise SystemExit("Stop this project's workers and scheduler before checkpoint/recovery")
    container = infra.compose("ps", "-q", "backend", capture=True).strip()
    if not container:
        raise SystemExit("The isolated backend is not running")
    details = json.loads(infra.run(["docker", "inspect", container], capture=True))[0]
    labels = details["Config"]["Labels"]
    if labels.get("com.docker.compose.project") != infra.PROJECT:
        raise SystemExit("Backend does not belong to the isolated project")
    return container, details["Image"]


def mounted_snapshot_digests() -> dict[str, str]:
    script = "import hashlib,json,pathlib; p=pathlib.Path('/run/bizbase-directory'); print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.glob('snapshot*.json')) if f.is_file()}))"
    return json.loads(infra.compose("exec", "-T", "backend", "env/bin/python", "-c", script, capture=True))


def checkpoint() -> Path:
    _, image_id = backend_identity()
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = CHECKPOINTS / identifier
    destination.mkdir(parents=True, mode=0o700)
    container_path = f"{CONTAINER_ROOT}/{identifier}"
    infra.compose("exec", "-T", "backend", "mkdir", "-p", container_path)
    infra.compose("exec", "-T", "backend", "bench", "--site", infra.SITE,
                  "backup", "--with-files", "--ignore-backup-conf", "--backup-path", container_path)
    infra.compose("cp", f"backend:{container_path}/.", str(destination))
    files = {}
    for file in destination.iterdir():
        if not file.is_file():
            raise SystemExit("Unexpected directory in site backup")
        file.chmod(0o600)
        files[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    if len(files) != 4 or not any(name.endswith("-database.sql.gz") for name in files):
        raise SystemExit("Expected database, configuration, public and private files")
    metadata = {"project": infra.PROJECT, "site": infra.SITE, "image_id": image_id,
                "created_at": identifier, "files": files,
                "private_snapshot_digests": mounted_snapshot_digests()}
    from site_ops import directory_fingerprint
    metadata["directory_fingerprint"] = directory_fingerprint()
    metadata["local_credentials"] = {}
    for name in ("credentials.json", "client.json", "login.txt"):
        original = infra.PRIVATE / name
        if original.is_file():
            copied = destination / name
            copied.write_bytes(original.read_bytes())
            copied.chmod(0o600)
            metadata["local_credentials"][name] = hashlib.sha256(copied.read_bytes()).hexdigest()
    infra.private_write(destination / "checkpoint.json", json.dumps(metadata, indent=2) + "\n")
    print(f"Verified checkpoint: {destination}")
    return destination


def verify(identifier: str) -> tuple[Path, dict]:
    if not re.fullmatch(r"\d{8}T\d{12}Z", identifier):
        raise SystemExit("Use a checkpoint ID produced by this script")
    directory = CHECKPOINTS / identifier
    metadata = json.loads((directory / "checkpoint.json").read_text())
    if metadata["project"] != infra.PROJECT or metadata["site"] != infra.SITE:
        raise SystemExit("Checkpoint belongs to another project or site")
    _, current_image = backend_identity()
    if metadata["image_id"] != current_image:
        raise SystemExit("Restore requires the exact checkpoint image; image switching is a separate operation")
    if metadata["private_snapshot_digests"] != mounted_snapshot_digests():
        raise SystemExit("Mounted immutable snapshots differ from the checkpoint")
    for name, digest in metadata["files"].items():
        if Path(name).name != name or hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise SystemExit("Checkpoint file digest mismatch")
    for name, digest in metadata.get("local_credentials", {}).items():
        if name not in {"credentials.json", "client.json", "login.txt"} or hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise SystemExit("Checkpoint local credentials digest mismatch")
    print("Checkpoint identity, image and all file digests match")
    return directory, metadata


def restore(identifier: str, values: dict[str, str]) -> None:
    directory, metadata = verify(identifier)
    checkpoint()  # 先备份当前状态；失败则不开始恢复。
    container, _ = backend_identity()
    # 使用现有 sites 卷暂存；一次性恢复容器看不到旧 backend 的 /tmp。
    target = f"/home/frappe/frappe-bench/sites/{infra.SITE}/private/restore-staging/{identifier}"
    infra.compose("exec", "-T", "backend", "mkdir", "-p", target)
    infra.compose("cp", str(directory) + "/.", f"backend:{target}")
    # docker cp 的文件所有者可能是 root；只调整本次明确指定的暂存目录。
    infra.run(["docker", "exec", "--user", "0:0", container, "chown", "-R", "1000:1000", target])
    infra.run(["docker", "exec", "--user", "0:0", container, "chmod", "700", target])
    # 凭据通过 stdin 传入，命令文本、终端与恢复记录均不包含其值。
    saved_config = json.loads(next(directory.glob("*-site_config_backup.json")).read_text())
    infra.REDACTIONS.extend(str(value) for key, value in saved_config.items()
                            if "password" in key or "key" in key)
    script = r'''
import json, pathlib, subprocess, sys
request = json.load(sys.stdin)
site = "bizbase-acceptance.localhost"
root = pathlib.Path(request["path"])
config_path = pathlib.Path("sites") / site / "site_config.json"
config = next(root.glob("*-site_config_backup.json"))
current = json.loads(config_path.read_text())
saved = json.loads(config.read_text())
if current.get("db_name") != saved.get("db_name"):
    raise SystemExit("Backup database identity differs from this site")
def run(*args):
    result = subprocess.run(["bench", "--site", site, *args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout.replace(request["password"], "[REDACTED]"), end="")
    if result.returncode:
        raise SystemExit(result.returncode)
run("restore", str(next(root.glob("*-database.sql.gz"))),
    "--db-root-username", "root", "--db-root-password", request["password"],
    "--with-public-files", str(next(f for f in root.glob("*-files.tar") if not f.name.endswith("-private-files.tar"))),
    "--with-private-files", str(next(root.glob("*-private-files.tar"))))
config_path.write_text(json.dumps(saved, indent=2) + "\n")
config_path.chmod(0o600)
run("migrate")
run("disable-scheduler")
run("set-maintenance-mode", "off")
'''
    # 将本次恢复镜像锁为已验证的 ID，防止环境文件或标签漂移；其余配置和卷沿用 backend。
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", prefix="restore-image-",
                                     dir=infra.PRIVATE, delete=False) as override:
        json.dump({"services": {"backend": {"image": metadata["image_id"]}}}, override)
        override_path = Path(override.name)
    files = ["-f", str(infra.COMPOSE_FILE)]
    if values.get("BIZBASE_R01_RUNTIME_DATA") == "1":
        files += ["-f", str(infra.ROOT / "deploy/local-directory/compose.data.yaml")]
    command = ["docker", "compose", "--project-name", infra.PROJECT, "--env-file", str(infra.ENV_FILE),
               *files, "-f", str(override_path), "run", "--rm", "--no-deps", "-T",
               "--name", "bizbase-r01-restore", "--entrypoint", "/home/frappe/frappe-bench/env/bin/python",
               "backend", "-c", script]
    try:
        # stop 等待进程退出后才返回；超过宽限时间时 Docker 终止残留进程。
        # 后端彻底退出后才恢复数据库，避免已接收请求在恢复期间提交写入。
        infra.compose("stop", "--timeout", "30", "frontend", "websocket", "backend")
        running = infra.compose("ps", "--services", "--status", "running", capture=True).splitlines()
        if any(service in running for service in ("frontend", "websocket", "backend", "worker", "scheduler")):
            raise SystemExit("A business process is still running; refusing to restore")
        process = subprocess.run(command,
                                 input=json.dumps({"path": target, "password": values["BIZBASE_R01_DB_ROOT_PASSWORD"]}),
                                 cwd=infra.ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(infra.sanitized(process.stdout), end="")
        if process.returncode:
            raise SystemExit("Restore failed; all application services remain stopped and the pre-restore checkpoint is retained")
        for name in metadata.get("local_credentials", {}):
            infra.private_write(infra.PRIVATE / name, (directory / name).read_text())
        # 一次性容器已经退出且移除，才恢复原有服务；不运行 up 或重复安装流程。
        infra.compose("start", "backend", "websocket", "frontend")
        infra.wait_http()
    except BaseException:
        infra.compose("stop", "frontend", "websocket", "backend")
        raise
    finally:
        override_path.unlink(missing_ok=True)
    infra.private_write(infra.PRIVATE / "last-restore.json", json.dumps({
        "checkpoint": identifier, "image_id": metadata["image_id"],
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "business_reverification_required": True,
        "expected_directory_fingerprint": metadata["directory_fingerprint"],
    }, indent=2) + "\n")
    print("Database, site configuration and files restored; rerun business and permission acceptance")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "verify", "restore"])
    parser.add_argument("checkpoint", nargs="?")
    args = parser.parse_args()
    values = infra.load_env()
    infra.validate_config()
    if args.action == "backup":
        checkpoint()
    elif not args.checkpoint:
        parser.error("verify/restore require a checkpoint ID")
    elif args.action == "verify":
        verify(args.checkpoint)
    else:
        restore(args.checkpoint, values)


if __name__ == "__main__":
    main()
