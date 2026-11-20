"""Root-only ECS rehearsal. Never uses deploy.sh, a live site mount or production Redis.

Usage (on ECS via rtk proxy ssh): python3 -I rehearse_routes.py SNAPSHOT_SITES [--approved AUDIT_DIR --geo-sha256 DIGEST]
The matching restored schema must already exist. A failed apply is NOT resumable.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import ipaddress
import socket
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path("/var/lib/bizbase-rehearsals")
LIVE = Path("/var/lib/bizbase-prod")
TOOLS = Path(__file__).resolve().parent
BENCH = "/home/frappe/frappe-bench"
SITE = "routes-rehearsal.invalid"
SCHEMA = "bizbase_rehearsal"
OLD, NEW = "bizbase/prod:clarity-kshhri", "bizbase/prod:routes-candidate"
EXTRA = "crm insights bizbase_mgmt sales_board ops_board customer_board".split()
LEGACY = set("frappe erpnext geo_operations yishan_id_login static_share".split())
FINAL = {"frappe", "erpnext", "file_share", "yishan_id", *EXTRA}
FILES = ("rehearsal_checks.py", "preserve_geo.py", "rename_yishan_id.py", "rename_file_share.py")


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def owned(path, folder=False):
    info = path.lstat()
    need((stat.S_ISDIR if folder else stat.S_ISREG)(info.st_mode) and info.st_uid == 0
         and not info.st_mode & 0o077, "not private/root-owned: " + str(path))


def copy_files(src, dst):
    # No symlinks, special files, source ownership, hard links or shared inodes in the clone.
    need(src.is_dir() and src.resolve() == src, "expected regular snapshot folder")
    dst.mkdir(mode=0o700, parents=True)
    for item in src.iterdir():
        mode = item.lstat().st_mode
        target = dst / item.name
        if stat.S_ISDIR(mode):
            copy_files(item, target)
        else:
            need(stat.S_ISREG(mode), "unexpected snapshot file type")
            shutil.copyfile(item, target)


def stage(src, work):
    src = src.resolve(strict=True)
    need(src != LIVE and LIVE not in src.parents and ROOT not in src.parents, "live/work sites forbidden")
    need(any(p.stat().st_uid == 0 and stat.S_IMODE(p.stat().st_mode) == 0o700
             for p in (src, *src.parents)), "snapshot must be inside a root-private directory")
    site = src / "bizbase.geokeji.com"
    conf = {}
    for p in (src / "common_site_config.json", site / "site_config.json"):
        need(p.resolve(strict=True) == p and p.is_file(), "unsafe config path")
        conf.update(json.loads(p.read_text()))
    need((conf.get("db_type"), conf.get("db_name"), conf.get("db_user"), conf.get("db_schema")) ==
         ("postgres", "bizbase", "bizbase_app", "bizbase_app"), "unrecognized checkpoint config")
    need(conf.get("db_password") and conf.get("encryption_key"), "checkpoint missing DB secret or encryption key")
    need(not any(conf.get(k) for k in ("db_ssl_ca", "db_ssl_cert", "db_ssl_key", "db_socket")),
         "custom TLS/socket settings require review; do not downgrade")
    host, port = conf["db_host"], int(conf.get("db_port", 5432))
    need(re.fullmatch(r"[A-Za-z0-9.-]+", host) and 0 < port < 65536, "unexpected RDS endpoint")
    # This VPC-only RDS has TLS disabled. Match the live libpq policy only for RFC1918 endpoints.
    networks = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
    addresses = {ipaddress.ip_address(r[4][0]) for r in socket.getaddrinfo(host, port)}
    need(addresses and all(any(a in n for n in networks) for a in addresses), "expected private RDS endpoint")
    sites = work / "sites"
    dest = sites / SITE
    for kind in ("private", "public"):
        copy_files(site / kind / "files", dest / kind / "files")
    for p in (dest / "locks", dest / "logs", dest / "private/backups", work / "logs"):
        p.mkdir(mode=0o700)
    (sites / "assets").symlink_to(BENCH + "/assets")
    cfg = {k: conf[k] for k in ("db_type", "db_name", "db_user", "db_password", "encryption_key")}
    cfg.update(db_host="rds-only", db_port=15432, db_schema=SCHEMA, maintenance_mode=1,
               mute_emails=1, pause_scheduler=1, disable_scheduler=1, server_script_enabled=0,
               developer_mode=0, host_name="http://" + SITE)
    (dest / "site_config.json").write_text(json.dumps(cfg))
    (sites / "common_site_config.json").write_text(json.dumps(dict(bench_id=work.name, default_site=SITE,
        redis_cache="redis://rehearsal-redis:6379/0", redis_queue="redis://rehearsal-redis:6379/1",
        redis_socketio="redis://rehearsal-redis:6379/1", socketio_port=9000)))
    for p in (sites, *sites.rglob("*"), work / "logs"):
        if not p.is_symlink():
            os.chown(p, 1000, 0)
    return host, port


# Only this transparent TCP forwarder can leave the internal Docker network. It has no mounts,
# credentials or published ports. Listen on the internal address, not the egress interface.
RELAY = """
import asyncio, socket, sys
async def pump(r,w):
    try:
        while data := await r.read(65536):
            w.write(data); await w.drain()
    finally: w.close()
async def handle(r,w):
    try:
        rr,ww = await asyncio.open_connection(sys.argv[1],int(sys.argv[2]))
        await asyncio.gather(pump(r,ww),pump(rr,w))
    finally: w.close()
async def main():
    server = await asyncio.start_server(handle,socket.gethostbyname("rds-only"),15432)
    async with server: await server.serve_forever()
asyncio.run(main())
"""


def run(args, work, log):
    def docker(*argv, capture=False, data=None):
        p = subprocess.run(["docker", "--host", "unix:///var/run/docker.sock", *argv],
            input=data, stdin=subprocess.DEVNULL if data is None else None, check=True,
            stderr=log, stdout=subprocess.PIPE if capture else log)
        return p.stdout if capture else None

    host, port = stage(args.snapshot, work)
    tag = work.name
    sites = work / "sites"
    tools = work / "tools"
    tools.mkdir(mode=0o755)
    tools.chmod(0o755)
    hashes = {}
    for name in FILES:
        payload = (TOOLS / name).read_bytes()
        (tools / name).write_bytes(payload)
        (tools / name).chmod(0o444)
        hashes[name] = hashlib.sha256(payload).hexdigest()
    hashes[Path(__file__).name] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    images = {}
    for image in (OLD, NEW, "redis:8.6.5-alpine"):
        image_id, arch = docker("image", "inspect", "--format", "{{.Id}} {{.Architecture}}", image, capture=True).decode().split()
        need(arch == "amd64", "wrong image architecture")
        images[image] = image_id
    def manifest(image, expected):
        raw = docker("run", "--pull=never", "--rm", "--network=none", "--log-driver=none", "--entrypoint=cat",
                     images[image], BENCH + "/sites/apps.txt", capture=True)
        apps = raw.decode().split()
        need(len(apps) == len(expected) and set(apps) == expected, "unexpected image manifest")
        path = sites / "apps.txt"
        path.write_bytes(raw)
        os.chown(path, 1000, 0)
    common = ["--pull=never", "--log-driver=none", "--network", tag, "--cap-drop=ALL", "--security-opt=no-new-privileges"]
    def job(image, executable, *params, capture=False):
        return docker("run", "--rm", *common, "--user=1000:0", "--workdir", BENCH,
            "-e", "PGOPTIONS=-csearch_path=" + SCHEMA, "-e", "PGSSLMODE=prefer", "-e", "PGCONNECT_TIMEOUT=10",
            "-v", f"{sites}:{BENCH}/sites", "-v", f"{work}/logs:{BENCH}/logs", "-v", f"{tools}:/opt/rehearsal:ro",
            "--entrypoint", executable, images[image], *params, capture=capture)
    def check(image, name):
        return job(image, "env/bin/python", "-I", "/opt/rehearsal/rehearsal_checks.py", name)
    def bench(image, *params, capture=False):
        check(image, "scope")
        return job(image, "bench", "--site", SITE, *params, capture=capture)
    with contextlib.ExitStack() as cleanup:
        docker("network", "create", "--internal", tag)
        cleanup.callback(docker, "network", "rm", tag)
        for alias, image, ep, cmd in [
            ("rehearsal-redis", "redis:8.6.5-alpine", "redis-server", ["--save", "", "--appendonly", "no", "--protected-mode", "no"]),
            ("rds-only", OLD, "env/bin/python", ["-I", "-c", RELAY, host, str(port)])]:
            name = tag + "-" + alias
            cid = docker("run", "-d", *common, "--network-alias", alias, "--name", name, "--entrypoint", ep,
                         images[image], *cmd, capture=True).decode().strip()
            cleanup.callback(docker, "rm", "-fv", cid)
            if alias == "rds-only":
                docker("network", "connect", "bridge", cid)
        manifest(OLD, LEGACY)
        for image in (OLD, NEW):
            check(image, "source")
        check(OLD, "before")
        raw = bench(OLD, "uninstall-app", "geo_operations", "--dry-run", capture=True)
        (work / "geo-dry-run.log").write_bytes(raw)
        need(b"Uninstalled App geo_operations" in raw and b"removing Module Def" in raw, "dry run did not complete")
        evidence = dict(images=images, tools=hashes, dry=hashlib.sha256(raw).hexdigest(),
                        baseline=json.loads((sites / SITE / "private/before.json").read_text()))
        (work / "review.json").write_text(json.dumps(evidence, indent=2))
        if args.approved is None:
            return "AUDIT ONLY: review geo-dry-run.log, run.log and review.json privately before --approved"
        prior = args.approved.resolve(strict=True)
        need(prior.parent == ROOT and prior != work, "expected previous audit directory")
        owned(prior, True)
        owned(prior / "audit-ok")
        need(evidence == json.loads((prior / "review.json").read_text()), "evidence changed since audit; stop")
        checksum = evidence['baseline']['geo_archive']
        need(args.geo_sha256 == checksum, "frozen GEO archive differs from reviewed site")
        check(OLD, "scope")
        job(OLD, "env/bin/python", "-I", "/opt/rehearsal/preserve_geo.py", "apply", "--site", SITE, "--sha256", checksum)
        bench(OLD, "uninstall-app", "geo_operations", "--yes", "--no-backup")
        check(OLD, "removed")
        job(OLD, "env/bin/python", "-I", "/opt/rehearsal/rename_yishan_id.py", "--site", SITE)
        # No hook-loading bench command between the two renames.
        job(OLD, "env/bin/python", "-I", "/opt/rehearsal/rename_file_share.py", "--site", SITE)
        manifest(NEW, FINAL)
        check(NEW, "renamed")
        for app in EXTRA:
            bench(NEW, "install-app", app)
        check(NEW, "pre-migrate")
        bench(NEW, "migrate", "--skip-search-index")
        bench(NEW, "clear-cache")
        check(NEW, "after")
        return "ISOLATED MIGRATION PASSED (no workers, traffic or production deployment)"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path)
    p.add_argument("--approved", type=Path, metavar="REVIEWED_AUDIT_DIR")
    p.add_argument("--geo-sha256", help="SHA-256 printed by preserve_geo.py backup for the frozen checkpoint")
    args = p.parse_args()
    if args.approved and not re.fullmatch("[0-9a-f]{64}", args.geo_sha256 or ""):
        p.error("--approved requires --geo-sha256 from the frozen backup")
    if os.geteuid() != 0:
        p.error("requires a root shell on the designated ECS")
    os.umask(0o077)
    ROOT.mkdir(mode=0o700, exist_ok=True)
    owned(ROOT, True)
    with (ROOT / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        work = ROOT / ("routes-" + secrets.token_hex(8))
        work.mkdir()
        print("Private rehearsal directory:", work, flush=True)
        with (work / "run.log").open("ab", buffering=0) as log:
            try:
                result = run(args, work, log)
            except Exception:
                log.write(traceback.format_exc().encode())
                sys.exit("Stopped. Review private run.log; after a partial apply restore the isolated checkpoint, do not retry in place.")
        (work / ("apply-ok" if args.approved else "audit-ok")).touch()
        print(result)


if __name__ == "__main__":
    main()
