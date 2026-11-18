"""新建或迁移本轮隔离站点，凭据不进入命令输出。"""

import json
import os
import subprocess
from pathlib import Path

SITE = "bizbase-acceptance.localhost"
SITE_PATH = Path("/home/frappe/frappe-bench/sites") / SITE
SECRETS = [os.environ["BIZBASE_R01_DB_ROOT_PASSWORD"], os.environ["BIZBASE_R01_ADMIN_PASSWORD"]]


def run(*args):
    process = subprocess.run(["bench", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = process.stdout
    for secret in SECRETS:
        output = output.replace(secret, "[REDACTED]")
    print(output, end="", flush=True)
    if process.returncode:
        raise SystemExit(process.returncode)
    return process.stdout


if not (SITE_PATH / "site_config.json").exists():
    run(
        "new-site", SITE, "--db-type", "mariadb", "--db-host", "db",
        "--db-root-username", "root", "--db-root-password", SECRETS[0],
        "--admin-password", SECRETS[1], "--mariadb-user-host-login-scope", "%",
        "--set-default",
    )

installed = json.loads(run("--site", SITE, "list-apps", "--format", "json"))
if isinstance(installed, dict):
    installed = installed.get(SITE, installed)
installed_names = set(installed if isinstance(installed, list) else installed.keys())
for app in ("erpnext", "crm", "bizbase"):
    if app not in installed_names:
        run("--site", SITE, "install-app", app)
run("--site", SITE, "migrate")
run("--site", SITE, "disable-scheduler")
run("--site", SITE, "set-config", "allow_tests", "True", "--parse")
run("--site", SITE, "set-maintenance-mode", "off")
print("Isolated site model installation complete")
