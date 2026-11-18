#!/usr/bin/env python3
"""BizBase 第 01 轮专用本地环境；不接受其他项目、站点或端口。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "bizbase-r01"
SITE = "bizbase-acceptance.localhost"
PORT = 8081
PRIVATE = Path.home() / ".codex/private/bizbase-round01"
ENV_FILE = PRIVATE / "infra.env"
COMPOSE_FILE = ROOT / "deploy/local-directory/compose.yaml"
BASE = "bizbase/erpnext-crm@sha256:0ffc5fd8061155bbc89c74361ae65b00eea560c36a7828b4e2d5a9012464ffa2"
BASE_ID = "sha256:0ffc5fd8061155bbc89c74361ae65b00eea560c36a7828b4e2d5a9012464ffa2"
BASE_ALIAS = "bizbase/r01-base:sha256-0ffc5fd8061155bbc89c74361ae65b00eea560c36a7828b4e2d5a9012464ffa2"
REDACTIONS: list[str] = []


def private_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(content)
    path.chmod(0o600)


def load_env(create: bool = False) -> dict[str, str]:
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE.chmod(0o700)
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value
    elif create:
        values = {
            "BIZBASE_R01_DB_ROOT_PASSWORD": secrets.token_urlsafe(36),
            "BIZBASE_R01_ADMIN_PASSWORD": secrets.token_urlsafe(36),
        }
        save_env(values)
    else:
        raise SystemExit("Run bootstrap.py build first; private environment is absent")
    REDACTIONS[:] = [v for k, v in values.items() if "PASSWORD" in k]
    return values


def save_env(values: dict[str, str]) -> None:
    private_write(ENV_FILE, "".join(f"{k}={v}\n" for k, v in sorted(values.items())))


def sanitized(text: str) -> str:
    for value in REDACTIONS:
        text = text.replace(value, "[REDACTED]")
    return text


def run(args: list[str], *, capture: bool = False) -> str:
    process = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        output.append(line)
        if not capture:
            print(sanitized(line), end="", flush=True)
    if process.wait():
        if capture:
            print(sanitized("".join(output)[-8000:]), file=sys.stderr)
        raise SystemExit(f"Command failed: {args[0]} {args[1] if len(args) > 1 else ''}")
    return "".join(output)


def compose(*args: str, capture: bool = False) -> str:
    files = ["-f", str(COMPOSE_FILE)]
    if "BIZBASE_R01_RUNTIME_DATA=1" in ENV_FILE.read_text().splitlines():
        files += ["-f", str(ROOT / "deploy/local-directory/compose.data.yaml")]
    return run(["docker", "compose", "--project-name", PROJECT, "--env-file", str(ENV_FILE), *files, *args], capture=capture)


def validate_config() -> None:
    config = json.loads(compose("config", "--format", "json", capture=True))
    assert config["name"] == PROJECT
    for volume in config.get("volumes", {}).values():
        assert not volume.get("external")
        assert volume["name"].startswith(PROJECT + "_")
    for name, service in config["services"].items():
        for published in service.get("ports", []):
            assert name == "frontend"
            assert str(published["published"]) == str(PORT)
            assert published["host_ip"] == "127.0.0.1"
        for mount in service.get("volumes", []):
            if mount["type"] == "bind":
                assert name == "data-init" and mount["read_only"]
                assert mount["target"] in {"/input/snapshot-s01.json", "/input/snapshot-s01.manifest.json"}
                assert Path(mount["source"]).parent == PRIVATE
            elif mount["target"] == "/run/bizbase-directory" and name == "backend":
                assert mount["read_only"]


def check_port() -> None:
    owned = run(["docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--filter", "label=com.docker.compose.service=frontend", "--format", "{{.Names}}"], capture=True).strip()
    if owned:
        return
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", PORT))
        except OSError as error:
            raise SystemExit(f"Port {PORT} is occupied outside this project's frontend: {error}")


def download_build_wheel(requirement: str, destination: Path) -> dict[str, str]:
    if "==" not in requirement:
        raise SystemExit("Build dependencies must have an exact == version")
    name, version = requirement.split("==", 1)
    if name != "flit_core" or not all(ch.isdigit() or ch == "." for ch in version):
        raise SystemExit("Only the reviewed exact flit_core build backend is allowed")
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
        metadata = json.load(response)
    artifact = next(item for item in metadata["urls"] if item["filename"].endswith("py3-none-any.whl"))
    with urllib.request.urlopen(artifact["url"], timeout=60) as response:
        content = response.read()
    digest = hashlib.sha256(content).hexdigest()
    if digest != artifact["digests"]["sha256"]:
        raise SystemExit("Build dependency digest mismatch")
    (destination / artifact["filename"]).write_bytes(content)
    return {"requirement": requirement, "sha256": digest, "filename": artifact["filename"]}


def build() -> None:
    values = load_env(create=True)
    source = ROOT / "apps/bizbase"
    if not (source / "pyproject.toml").exists():
        raise SystemExit("App model scaffold is not ready")
    project = tomllib.loads((source / "pyproject.toml").read_text())
    requirements = project["build-system"]["requires"]
    actual_base = run(["docker", "image", "inspect", BASE_ID, "--format", "{{.Id}}"], capture=True).strip()
    if actual_base != BASE_ID:
        raise SystemExit("Pinned local base image is absent or mismatched")
    run(["docker", "tag", BASE_ID, BASE_ALIAS])
    with tempfile.TemporaryDirectory(prefix="bizbase-r01-build-") as tmp:
        context = Path(tmp)
        shutil.copytree(source, context / "app", ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache"))
        shutil.copytree(ROOT / "deploy/local-directory/ops", context / "ops", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (context / "wheels").mkdir()
        dependencies = [download_build_wheel(req, context / "wheels") for req in requirements]
        digest = hashlib.sha256()
        digest.update((ROOT / "deploy/local-directory/Containerfile").read_bytes())
        for file in sorted(p for p in context.rglob("*") if p.is_file()):
            digest.update(str(file.relative_to(context)).encode() + b"\0" + file.read_bytes())
        source_hash = digest.hexdigest()
        revision = run(["git", "rev-parse", "HEAD"], capture=True).strip()
        if run(["git", "status", "--porcelain", "--", "apps/bizbase", "deploy/local-directory"], capture=True).strip():
            revision += "-dirty"
        image = f"bizbase/directory:r01-{source_hash[:12]}-{revision[:8]}"
        run(["docker", "build", "--pull=false", "--progress=plain", "--build-arg", f"APP_REVISION={revision}", "--build-arg", f"APP_SOURCE_SHA256={source_hash}", "-f", str(ROOT / "deploy/local-directory/Containerfile"), "-t", image, str(context)])
        image_id = run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], capture=True).strip()
        base_layers = json.loads(run(["docker", "image", "inspect", BASE_ID, "--format", "{{json .RootFS.Layers}}"], capture=True))
        image_layers = json.loads(run(["docker", "image", "inspect", image, "--format", "{{json .RootFS.Layers}}"], capture=True))
        if image_layers[:len(base_layers)] != base_layers:
            raise SystemExit("Built image does not descend from the pinned base")
        values["BIZBASE_R01_IMAGE"] = image
        save_env(values)
        record = json.dumps({"image": image, "image_id": image_id, "base": BASE, "revision": revision, "source_sha256": source_hash, "build_dependencies": dependencies}, indent=2) + "\n"
        private_write(PRIVATE / "build.json", record)
        private_write(PRIVATE / "builds" / f"{image_id.removeprefix('sha256:')}.json", record)
        print(f"Prepared {image} ({image_id})")


def wait_http() -> None:
    for _ in range(90):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/login", timeout=5) as response:
                if response.status == 200:
                    print(f"Isolated login reachable at http://127.0.0.1:{PORT}/login")
                    return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit("Isolated login did not become ready; inspect only bizbase-r01 logs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "up", "status", "stop", "backup", "data"])
    args = parser.parse_args()
    if args.action == "build":
        build()
        return
    values = load_env()
    if args.action == "data":
        values.update(
            BIZBASE_R01_RUNTIME_DATA="1",
            BIZBASE_R01_SOURCE_SNAPSHOT=str(PRIVATE / "snapshot-s01.json"),
            BIZBASE_R01_SOURCE_MANIFEST=str(PRIVATE / "snapshot-s01.manifest.json"),
        )
        for key in ("BIZBASE_R01_SOURCE_SNAPSHOT", "BIZBASE_R01_SOURCE_MANIFEST"):
            if not Path(values[key]).is_file():
                raise SystemExit("Approved source files are absent")
        save_env(values)
    validate_config()
    if args.action == "up":
        check_port()
        compose("up", "-d")
        wait_http()
        compose("exec", "-T", "backend", "bench", "--site", SITE, "list-apps")
    elif args.action == "status":
        compose("ps", "-a")
    elif args.action == "stop":
        compose("stop")
    elif args.action == "backup":
        compose("exec", "-T", "backend", "bench", "--site", SITE, "backup", "--with-files")
        destination = PRIVATE / "backups"
        destination.mkdir(mode=0o700, exist_ok=True)
        compose("cp", f"backend:/home/frappe/frappe-bench/sites/{SITE}/private/backups/.", str(destination))
        for file in destination.rglob("*"):
            if file.is_file():
                file.chmod(0o600)
        print("Isolated backup copied to the private round directory")
    elif args.action == "data":
        compose("run", "--rm", "--no-deps", "data-init")
        compose("up", "-d", "--no-deps", "backend")
        print("Private data volume mounted read-only; business activation is a separate step")


if __name__ == "__main__":
    main()
