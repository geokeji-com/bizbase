"""PostgreSQL/Frappe v16 数据身份迁移，在完整备份且所有读写和后台任务已停止的窗口运行。

在 bench 根目录：env/bin/python - --site SITE < rename_file_share.py
不加载应用 hooks：可紧接旧镜像的移山 ID 改名、更新 sites/apps.txt 前执行（清单与镜像须匹配）。
采用一笔 PG 事务；Frappe 的 DocType.after_rename 会中途 commit 并尝试改源码，不适用。
只迁移表名与有类型的关联，不改业务主键、版本、内容、加密密钥、授权盐、文件或旧票据。
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import psycopg2
from psycopg2 import sql

OLD, NEW = "static_share", "file_share"
MODULE = {"Static Share": "File Share"}
TYPES = {"Static Share" + s: "File Share" + s for s in ("", " Version", " Access Log", " User", " Role")}
APP = {OLD: NEW}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def renamed_path(value):
    """Only owned routes and exact path segments; preserve query strings, fragments and doc IDs."""
    if not isinstance(value, str):
        return value

    return re.sub(r"^/desk/(?:static_share/)?static-share(?=[/?#]|$)", "/desk/file-share", value)


def migrate(conn, schema, maintenance_mode):
    require(str(maintenance_mode) == "1", "开启维护模式、停止后台任务并备份后再迁移")
    require(not conn.autocommit, "迁移需要事务")
    ident = sql.Identifier
    with conn, conn.cursor() as cur:

        def rows(query, params=()):
            cur.execute(query, params)
            return cur.fetchall()

        cur.execute("SET LOCAL lock_timeout = '10s'")
        cur.execute(sql.SQL("SET LOCAL search_path TO {}").format(ident(schema)))
        require(rows("select current_schema()") == [(schema,)], "数据库 schema 不匹配")
        cur.execute('LOCK TABLE "tabDefaultValue", "tabDocType", "tabModule Def" IN SHARE ROW EXCLUSIVE MODE')
        [(installed_row, raw)] = rows(
            'SELECT name,defvalue FROM "tabDefaultValue" WHERE parent=%s AND defkey=%s',
            ("__global", "installed_apps"),
        )
        apps = json.loads(raw)
        columns = defaultdict(set)
        for table, col in rows(
            "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=%s", (schema,)
        ):
            columns[table].add(col)
        mods = rows(
            'SELECT name,module_name,app_name FROM "tabModule Def" WHERE lower(name) IN (%s,%s) OR app_name IN (%s,%s)',
            ("static share", "file share", OLD, NEW),
        )
        names = rows(
            'SELECT name,module,issingle,is_virtual,custom FROM "tabDocType" WHERE module IN (%s,%s) OR lower(name)=ANY(%s)',
            ("Static Share", "File Share", [n.lower() for n in (*TYPES, *TYPES.values())]),
        )
        done = NEW in apps
        source, target = (NEW, OLD) if done else (OLD, NEW)
        expected = set(TYPES.values() if done else TYPES)
        module = "File Share" if done else "Static Share"
        require(
            mods == [(module, module, source)] and apps.count(source) == 1 and target not in apps,
            "安装记录或模块归属冲突",
        )
        require(
            {n for n, *_ in names} == expected
            and all(m == module and not any(flags) for _, m, *flags in names),
            "DocType 的名称、归属或类型冲突",
        )
        require(all("tab" + n in columns for n in expected), "存在缺失的源表")
        # Fail on all relation types (including indexes/views), not just Frappe DocType collisions.
        for n in TYPES if done else TYPES.values():
            require(rows("SELECT to_regclass(%s)", ('"tab' + n + '"',)) == [(None,)], "目标表已存在：" + n)
        require(
            rows('SELECT app_name FROM "tabInstalled Application" WHERE app_name IN (%s,%s)', (OLD, NEW))
            == [(source,)],
            "Installed Application 冲突",
        )
        if done:
            return False

        # Dangling permissions on the target namespace must never become live by renaming a DocType.
        for table, field in [
            ("tabDocShare", "share_doctype"),
            ("tabUser Permission", "allow"),
            ("tabUser Permission", "applicable_for"),
            ("tabCustom DocPerm", "parent"),
            ("tabDocPerm", "parent"),
            ("tabFile", "attached_to_doctype"),
            ("__Auth", "doctype"),
        ]:
            exists = rows(
                sql.SQL("SELECT 1 FROM {} WHERE {}=ANY(%s) LIMIT 1").format(ident(table), ident(field)),
                (list(TYPES.values()),),
            )
            require(not exists, f"新名称存在未归属的授权、凭据或附件：{table}.{field}")

        def replace(table, field, mapping, where=None, params=()):
            require(field in columns[table], f"缺少预期字段：{table}.{field}")
            q = sql.SQL("UPDATE {} SET {}=%s WHERE {}=%s").format(ident(table), ident(field), ident(field))
            if where is not None:
                q += sql.SQL(" AND ") + where
            for old, new in mapping.items():
                cur.execute(q, (new, old, *params))

        # Snapshot effective link/child schemas before changing metadata. Property setters override
        # standard/custom options just as they do when Frappe constructs Meta.
        fields = {
            (dt, f): (ft, opt)
            for dt, f, ft, opt in rows("""
            SELECT parent,fieldname,fieldtype,options FROM "tabDocField" WHERE coalesce(is_virtual,0)=0
            UNION ALL SELECT dt,fieldname,fieldtype,options FROM "tabCustom Field" WHERE coalesce(is_virtual,0)=0""")
        }
        for dt, f, prop, val in rows("""SELECT doc_type,field_name,property,value FROM "tabProperty Setter"
                                      WHERE property IN ('options','fieldtype')"""):
            if (dt, f) in fields:
                ft, opt = fields[dt, f]
                fields[dt, f] = (val, opt) if prop == "fieldtype" else (ft, val)
        singles = {n for (n,) in rows('SELECT name FROM "tabDocType" WHERE issingle=1')}

        def set_field(dt, f, mapping):
            if dt in singles:
                replace("tabSingles", "value", mapping, sql.SQL("doctype=%s AND field=%s"), (dt, f))
            elif f in columns.get("tab" + dt, ()):
                replace("tab" + dt, f, mapping)

        for (dt, f), (ft, opt) in fields.items():
            if ft == "Link" and opt in ("DocType", "Module Def"):
                set_field(dt, f, TYPES if opt == "DocType" else MODULE)
            elif ft == "Dynamic Link" and {f, opt} <= columns.get("tab" + dt, set()):
                # A Dynamic Link's selector is often a Select and not a Link to DocType.
                for selector, mapping in [("DocType", TYPES), ("Module Def", MODULE)]:
                    replace("tab" + dt, f, mapping, sql.SQL("{}=%s").format(ident(opt)), (selector,))
                set_field(dt, opt, TYPES)
            elif (
                ft in ("Table", "Table MultiSelect") and opt and "parenttype" in columns.get("tab" + opt, ())
            ):
                if dt in TYPES:
                    replace("tab" + opt, "parenttype", TYPES)
                elif dt in ("Module Def", "DocType"):
                    replace(
                        "tab" + opt,
                        "parent",
                        MODULE if dt == "Module Def" else TYPES,
                        sql.SQL("parenttype=%s"),
                        (dt,),
                    )
            elif ft == "Autocomplete" and opt == "Installed Applications":
                set_field(dt, f, APP)

        # Raw framework tables and non-Link columns are deliberately handled explicitly.
        for tab, f, mapping in [
            ("__Auth", "doctype", TYPES),
            ("__UserSettings", "doctype", TYPES),
            ("__global_search", "doctype", TYPES),
            ("tabCustom DocPerm", "parent", TYPES),
            ("tabBlock Module", "module", MODULE),
            ("tabDocType", "app", APP),
            ("tabUser", "default_app", APP),
            ("tabInstalled Application", "app_name", APP),
            ("tabModule Def", "module_name", MODULE),
            ("tabModule Def", "app_name", APP),
            ("tabDefaultValue", "defkey", TYPES),
        ]:
            replace(tab, f, mapping)
        for selector, mapping in [("DocType", TYPES), ("Module Def", MODULE)]:
            replace("tabVersion", "docname", mapping, sql.SQL("ref_doctype=%s"), (selector,))
            replace("tabFile", "attached_to_name", mapping, sql.SQL("attached_to_doctype=%s"), (selector,))
            replace("__global_search", "name", mapping, sql.SQL("doctype=%s"), (selector,))
        set_field("System Settings", "default_app", APP)
        for tab in ("tabDocField", "tabCustom Field"):
            replace(tab, "options", TYPES, sql.SQL("fieldtype IN ('Link','Table','Table MultiSelect')"))
        replace("tabProperty Setter", "value", TYPES, sql.SQL("property='options'"))
        for table, field in [("tabDesktop Icon", "link"), ("tabDesktop Icon", "logo_url")]:
            for name, val in rows(
                sql.SQL("SELECT name, {} FROM {} WHERE app=%s").format(ident(field), ident(table)), (NEW,)
            ):
                new = (
                    renamed_path(val)
                    if field == "link"
                    else ("/assets/file_share/icon.svg" if val == "/assets/static_share/icon.svg" else val)
                )
                if val != new:
                    cur.execute(
                        sql.SQL("UPDATE {} SET {}=%s WHERE name=%s").format(ident(table), ident(field)),
                        (new, name),
                    )
        for name, raw in rows(
            'SELECT name,layout FROM "tabDesktop Layout" WHERE layout LIKE %s OR layout LIKE %s',
            ("%static_share%", "%static-share%"),
        ):
            layout = json.loads(raw)
            require(isinstance(layout, list), "无法识别的桌面配置")
            for item in layout:
                if isinstance(item, dict) and item.get("app") == OLD:
                    item["app"] = NEW
                    if item.get("link"):
                        item["link"] = renamed_path(item["link"])
                    if item.get("logo_url") == "/assets/static_share/icon.svg":
                        item["logo_url"] = "/assets/file_share/icon.svg"
            cur.execute(
                'UPDATE "tabDesktop Layout" SET layout=%s WHERE name=%s',
                (json.dumps(layout, ensure_ascii=False), name),
            )
        for name, raw in rows(
            'SELECT name,last_known_versions FROM "tabUser" WHERE last_known_versions LIKE %s',
            ('%"static_share"%',),
        ):
            versions = json.loads(raw)
            if OLD in versions:
                require(NEW not in versions, "用户版本快照同时含新旧名称")
                versions[NEW] = versions.pop(OLD)
                cur.execute(
                    'UPDATE "tabUser" SET last_known_versions=%s WHERE name=%s', (json.dumps(versions), name)
                )

        # Fail closed for nested legacy DocType names in custom scripts/SQL/filters, rather
        # than rewriting string literals inside arbitrary business logic. Site-specific
        # dependencies need explicit review before proceeding with the maintenance window.
        for table, field in [
            ("tabServer Script", "script"),
            ("tabClient Script", "script"),
            ("tabReport", "query"),
        ]:
            if field in columns.get(table, ()):
                hit = rows(
                    sql.SQL("SELECT 1 FROM {} WHERE {} ~ %s LIMIT 1").format(ident(table), ident(field)),
                    (r"\m(Static Share|static_share)\M",),
                )
                require(not hit, f"站点存在引用旧名称的自定义代码，需单独评估：{table}.{field}")

        # Keep the original Patch Log as history. migrate must run the new namespace's
        # file_share.migrate_file_share to canonicalize legacy desktop links and layouts.
        replace("tabModule Def", "name", MODULE)
        replace("tabDocType", "name", TYPES)
        for old, new in TYPES.items():
            cur.execute(sql.SQL("ALTER TABLE {} RENAME TO {}").format(ident("tab" + old), ident("tab" + new)))
            cur.execute(
                sql.SQL("ALTER TABLE {} RENAME CONSTRAINT {} TO {}").format(
                    ident("tab" + new), ident("tab" + old + "_pkey"), ident("tab" + new + "_pkey")
                )
            )
        cur.execute(
            'UPDATE "tabDefaultValue" SET defvalue=%s WHERE name=%s',
            (json.dumps([NEW if a == OLD else a for a in apps]), installed_row),
        )
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True)
    args = parser.parse_args()
    import frappe
    from redis.exceptions import RedisError

    sites = Path("/home/frappe/frappe-bench/sites")
    require(
        Path(args.site).name == args.site and (sites / args.site / "site_config.json").is_file(), "无效站点"
    )
    frappe.init(site=args.site, sites_path=str(sites))
    cfg = frappe.conf
    require(cfg.db_type == "postgres", "仅用于已演练的 PostgreSQL 环境")
    conn = psycopg2.connect(
        dbname=cfg.db_name,
        user=cfg.db_user or cfg.db_name,
        password=cfg.db_password,
        host=cfg.db_host,
        port=cfg.db_port or 5432,
        connect_timeout=10,
    )
    try:
        changed = migrate(conn, cfg.get("db_schema") or "public", cfg.get("maintenance_mode"))
        # The DB transaction is committed. Clear only this site's old installation identity,
        # including on a no-op retry after a Redis outage. Old and new web/jobs stay stopped.
        cached_keys = ("defaults::__global", "all_apps", "app_modules", "installed_app_modules", "app_hooks")
        try:
            frappe.client_cache.delete_value("defaults::__global")
            frappe.client_cache.delete_value("installed_app_modules")
            for key in ("all_apps", "app_modules", "app_hooks"):
                frappe.cache.delete_value(key)
            # Frappe deletion helpers suppress some networking errors: positively verify eviction.
            require(
                not frappe.cache.exists(*(frappe.cache.make_key(key) for key in cached_keys)),
                "数据库已迁移；站点安装缓存未清除，请保持维护状态并重跑脚本",
            )
        except RedisError as error:
            raise SystemExit(
                f"数据库已迁移；站点缓存失效失败（{type(error).__name__}），请保持维护状态并重跑脚本"
            ) from None
        print(
            "文件分享数据身份已迁移。请切换清单、镜像并 migrate / clear-cache。"
            if changed
            else "已迁移，无需重复操作。"
        )
    finally:
        conn.close()
        frappe.destroy()


if __name__ == "__main__":
    try:
        main()
    except psycopg2.Error as error:
        # Do not print driver diagnostics that can include row values or connection details.
        raise SystemExit(
            f"数据库迁移失败（{type(error).__name__} / {error.pgcode or '-'}），请保持维护状态。"
        ) from None
