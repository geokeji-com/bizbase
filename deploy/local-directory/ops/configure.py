"""仅配置新建的 bizbase-r01 卷，不读取现有站点配置。"""

import json
from pathlib import Path

ROOT = Path("/home/frappe/frappe-bench")
SITES = ROOT / "sites"
SITE = "bizbase-acceptance.localhost"

unexpected = [p.name for p in SITES.iterdir() if p.is_dir() and (p / "site_config.json").exists() and p.name != SITE]
if unexpected:
    raise SystemExit("Refusing to configure a volume with a different site")

settings_path = SITES / "common_site_config.json"
settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
settings.update(
    db_host="db",
    db_port=3306,
    redis_cache="redis://redis-cache:6379",
    redis_queue="redis://redis-queue:6379",
    redis_socketio="redis://redis-queue:6379",
    socketio_port=9000,
    default_site=SITE,
)
settings_path.write_text(json.dumps(settings, indent=2) + "\n")
(SITES / "apps.txt").write_text("frappe\nerpnext\ncrm\nbizbase\n")
print("Configured isolated directory site services")
