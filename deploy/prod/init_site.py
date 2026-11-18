"""One-shot bootstrap for the pre-provisioned PostgreSQL site; never create/drop a DB or role."""

import hashlib
import json
import os
import re
import sys
import traceback
from pathlib import Path

import frappe
from redis import Redis
from frappe.installer import install_app, make_site_dirs
from frappe.migrate import SiteMigration
from frappe.utils.password import check_password
from frappe.utils.scheduler import enable_scheduler
from frappe.utils.synchronization import filelock

SITE = "bizbase.geokeji.com"
APPS = ("frappe", "geo_operations", "yishan_id_login")
SEED_HASH = "b35b740c07c0450f6d93ad4ec07d7e68057ea81caa6efbbcd7cd2bb28c2bbb35"


class PreflightError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise PreflightError(message)


def bootstrap():
    os.chdir("/home/frappe/frappe-bench/sites")
    require(Path(SITE, "site_config.json").is_file(), "Missing site_config.json")
    common = json.loads(Path('common_site_config.json').read_text())
    # Logical DBs 0/1 on the managed instance belong to other workloads.
    for key, expected in (("redis_cache", 2), ("redis_queue", 4)):
        client = Redis.from_url(common[key], socket_timeout=6)
        try:
            require(client.connection_pool.connection_kwargs.get('db') == expected,
                    "Unexpected Redis logical database")
            require(client.dbsize() == 0, "Allocated Redis database not empty; refusing to initialize")
        finally:
            client.close()
    frappe.init(SITE)
    conf = frappe.conf
    require(frappe.__version__ == "16.56.0", "Unreviewed Frappe version")
    require((conf.db_type, conf.db_name, conf.db_user, conf.db_schema) ==
            ("postgres", "bizbase", "bizbase_app", "bizbase_app"), "Unexpected database configuration")
    require(set(frappe.get_all_apps()) == set(APPS), "Unexpected apps.txt")
    password = Path("/run/secrets/bizbase_admin").read_text().rstrip("\r\n")
    require(len(password) >= 16, "Missing or short administrator secret")
    seed = Path(frappe.__file__).parent / "database/postgres/framework_postgres.sql"
    raw = seed.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SEED_HASH, "Unreviewed bootstrap SQL")
    # The reviewed seed contains only unqualified table/index creation once DROP lines are omitted.
    sql, drops = re.subn(r'^DROP TABLE IF EXISTS "[^"\n]+";\s*$', '', raw.decode(), flags=re.M)
    require(drops == 11, "Unexpected bootstrap statements")

    make_site_dirs()
    with filelock("bench_new_site", timeout=1):
        frappe.connect()
        scope = frappe.db.sql("""select current_database(), current_user, current_schema(),
            pg_get_userbyid(nspowner), has_schema_privilege(current_user,'public','CREATE')
            from pg_namespace where nspname=current_schema()""")
        require(scope == [("bizbase", "bizbase_app", "bizbase_app", "bizbase_app", False)] or
                tuple(scope) == (("bizbase", "bizbase_app", "bizbase_app", "bizbase_app", False),),
                "Connected to unexpected database/schema or public writable")
        count = frappe.db.sql("select count(*) from pg_class where relnamespace=current_schema()::regnamespace")[0][0]
        require(count == 0, "Schema is not empty; refusing to rerun initialization")
        frappe.flags.in_install_db = True
        frappe.cache.delete_keys("")
        # Use Frappe's scoped connection rather than the default psql restore (which uses a separate search_path).
        frappe.db._cursor.execute(sql)
        frappe.db.create_auth_table()
        frappe.db.create_global_search_table()
        frappe.db.create_user_settings_table()
        frappe.flags.in_install_db = False
        frappe.conf.admin_password = password
        for app in APPS:
            install_app(app, set_as_patched=True)
        enable_scheduler()
        frappe.db.commit()
    frappe.destroy()
    SiteMigration().run(SITE)
    frappe.init(SITE)
    frappe.connect()
    check_password("Administrator", password)
    require(set(frappe.get_installed_apps()) == set(APPS), "Installed apps mismatch")
    require(frappe.db.exists("Workspace", "geo_operations"), "Missing GEO workspace")
    n = frappe.db.sql("select count(*) from pg_tables where schemaname=current_schema()")[0][0]
    print(f"Site initialized and migrated: {n} tables, {len(APPS)} apps, Administrator verified.")


if __name__ == "__main__":
    try:
        bootstrap()
    except PreflightError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        # Framework/driver exceptions can contain connection URLs: never echo their text or frame locals.
        for frame in traceback.extract_tb(exc.__traceback__):
            print(f"{frame.name} ({Path(frame.filename).name}:{frame.lineno})", file=sys.stderr)
        sys.exit(f"Initialization failed: {type(exc).__name__}")
    finally:
        frappe.destroy()
