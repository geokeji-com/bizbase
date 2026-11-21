"""BizBase 管理看板安装身份迁移。旧镜像、停写检查点后运行；详见 management-board-migration.md。"""
import argparse
import json
import re
from pathlib import Path

import psycopg2
from psycopg2 import sql

OLD, NEW = 'bizbase_mgmt', 'management_board'
TYPES = ('Module Def', 'Workspace', 'Custom Workspace')
ROUTE = re.compile(r'^/desk/(?:bizbase_mgmt|bizbase-mgmt)(?=/?(?:[?#]|$))')


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def migrate(conn, schema, maintenance):
    need(str(maintenance) == '1' and not conn.autocommit, '需要维护模式和数据库事务')
    ident = sql.Identifier
    with conn, conn.cursor() as cur:
        def rows(query, args=()):
            cur.execute(query, args)
            return cur.fetchall()

        cur.execute("SET LOCAL lock_timeout = '10s'")
        cur.execute(sql.SQL('SET LOCAL search_path TO {}').format(ident(schema)))
        need(rows('SELECT current_schema()') == [(schema,)], '数据库 schema 不符')
        cur.execute('LOCK TABLE "tabDefaultValue", "tabModule Def", "tabWorkspace" IN SHARE ROW EXCLUSIVE MODE')
        [(key, raw)] = rows('SELECT name, defvalue FROM "tabDefaultValue" WHERE parent=%s AND defkey=%s',
                            ('__global', 'installed_apps'))
        apps = json.loads(raw)
        done = NEW in apps
        src, absent = (NEW, OLD) if done else (OLD, NEW)
        pair = ([OLD, NEW],)
        need(isinstance(apps, list) and apps.count(src) == 1 and absent not in apps, '已安装应用冲突')
        need(rows('SELECT app_name FROM "tabInstalled Application" WHERE app_name=ANY(%s)', pair) == [(src,)],
             'Installed Application 不符')
        need(rows('SELECT name,module_name,app_name FROM "tabModule Def" WHERE name=ANY(%s) OR app_name=ANY(%s)',
                  pair * 2) == [(src, src, src)], 'Module Def 冲突')
        need(rows('SELECT name,module,label,title,public,standard FROM "tabWorkspace" WHERE name=ANY(%s)', pair)
             == [(src, src, src, src, 1, 1)], '标准工作区不符')
        need(not rows('''SELECT 1 FROM "tabWorkspace" WHERE name=%s AND
                          (coalesce(is_hidden,0)<>0 OR coalesce(hide_custom,0)<>0 OR coalesce(for_user,'')<>''
                           OR coalesce(restrict_to_domain,'')<>'' OR coalesce(content,'[]')::jsonb<>'[]'::jsonb)''',
                      (src,)), '标准工作区存在本地内容或访问限制；先按定制工作区演练保留')
        need(not rows('SELECT 1 FROM "tabWorkspace" WHERE lower(replace(name,\'_\',\'-\'))=%s AND name<>%s',
                      ('management-board', src)), '目标工作区 URL 与现有工作区冲突')
        custom = rows('SELECT name,workspace FROM "tabCustom Workspace" WHERE name=ANY(%s) OR workspace=ANY(%s)',
                      pair * 2)
        need(custom in ([], [(src, src)]), '工作区自定义冲突')
        need(rows('SELECT role FROM "tabHas Role" WHERE parenttype=%s AND parent=%s', ('Workspace', src))
             == [('System Manager',)], '标准工作区授权与候选源码不符，先核对定制权限')

        def move(table, field, where=sql.SQL('TRUE'), args=()):
            # Never revive a dangling destination grant/link, including child table ownership.
            t, f = ident(table), ident(field)
            cond = sql.SQL('{}=%s AND ').format(f) + where
            need(not rows(sql.SQL('SELECT 1 FROM {} WHERE ').format(t) + cond + sql.SQL(' LIMIT 1'),
                          (absent, *args)), f'悬空或冲突引用：{table}.{field}')
            if not done:
                cur.execute(sql.SQL('UPDATE {} SET {}=%s WHERE ').format(t, f) + cond, (NEW, OLD, *args))

        # Effective field types, including site custom fields and Property Setters.
        fields = {(dt, f): [ft, opt] for dt, f, ft, opt in rows('''
            SELECT parent,fieldname,fieldtype,options FROM "tabDocField" WHERE coalesce(is_virtual,0)=0
            UNION ALL SELECT dt,fieldname,fieldtype,options FROM "tabCustom Field" WHERE coalesce(is_virtual,0)=0''')}
        for dt, f, prop, val in rows('''SELECT doc_type,field_name,property,value FROM "tabProperty Setter"
                                       WHERE property IN ('fieldtype','options')'''):
            if (dt, f) in fields:
                fields[dt, f][1 if prop == 'options' else 0] = val
        columns = set(rows('SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=%s', (schema,)))
        singles = {dt for dt, in rows('SELECT name FROM "tabDocType" WHERE issingle=1')}
        # Deduplicate equivalent selectors (some framework references also have explicit legacy handling).
        fixed = {('tab' + dt, f) for dt, f in [('Block Module','module'), ('User','default_app'),
                 ('DocType','app'), ('Workspace Sidebar','module'), ('Installed Application','app_name'),
                 ('User Invitation','app_name')]}
        for (dt, f), (ft, opt) in fields.items():
            table = 'tab' + dt
            if (ft == 'Link' and opt in TYPES) or (ft == 'Autocomplete' and opt == 'Installed Applications'):
                if dt in singles:
                    move('tabSingles', 'value', sql.SQL('doctype=%s AND field=%s'), (dt, f))
                elif (table, f) in columns:
                    fixed.add((table, f))
            elif ft == 'Dynamic Link' and (table, f) in columns and (table, opt) in columns:
                move(table, f, sql.SQL('{}=ANY(%s)').format(ident(opt)), (list(TYPES),))
        # The System Settings field is Select on some deployments.
        if fields.get(('System Settings', 'default_app')) != ['Autocomplete', 'Installed Applications']:
            move('tabSingles', 'value', sql.SQL('doctype=%s AND field=%s'), ('System Settings', 'default_app'))
        for table, field in fixed:
            move(table, field)
        for table, col in columns:
            if col == 'parenttype' and (table, 'parent') in columns:
                move(table, 'parent', sql.SQL('parenttype=ANY(%s)'), (list(TYPES),))
        for table, field, selector in [('tabFile','attached_to_name','attached_to_doctype'),
                ('tabVersion','docname','ref_doctype'), ('__global_search','name','doctype')]:
            # Metadata may already have handled some of these links.
            if fields.get((table.removeprefix('tab'), field)) != ['Dynamic Link', selector]:
                move(table, field, sql.SQL('{}=ANY(%s)').format(ident(selector)), (list(TYPES),))

        for table, field in [('tabDesktop Icon','link'), ('tabWorkspace Shortcut','url'),
                             ('tabWorkspace Sidebar Item','url'), ('tabWorkspace','external_link')]:
            for name, value in rows(sql.SQL('SELECT name,{} FROM {} WHERE {} LIKE %s').format(
                    ident(field), ident(table), ident(field)), ('/desk/bizbase%',)):
                path = ROUTE.sub('/desk/management-board', value)
                if path != value:
                    need(not done, '旧路由仍然存在')
                    cur.execute(sql.SQL('UPDATE {} SET {}=%s WHERE name=%s').format(ident(table), ident(field)),
                                (path, name))
        old_logo, new_logo = f'/assets/{OLD}/icon.svg', f'/assets/{NEW}/icon.svg'
        if not done:
            cur.execute('UPDATE "tabDesktop Icon" SET logo_url=%s WHERE logo_url=%s', (new_logo, old_logo))
        for name, raw in rows('SELECT name,layout FROM "tabDesktop Layout" WHERE layout LIKE %s OR layout LIKE %s',
                              ('%bizbase_mgmt%', '%bizbase-mgmt%')):
            layout = json.loads(raw)
            need(isinstance(layout, list), '不认识的桌面布局')
            for item in layout:
                if isinstance(item, dict):
                    if item.get('app') == OLD:
                        item['app'] = NEW
                    if isinstance(item.get('link'), str):
                        item['link'] = ROUTE.sub('/desk/management-board', item['link'])
                    if item.get('logo_url') == old_logo:
                        item['logo_url'] = new_logo
            if layout != json.loads(raw):
                need(not done, '旧桌面布局仍然存在')
                cur.execute('UPDATE "tabDesktop Layout" SET layout=%s WHERE name=%s',
                            (json.dumps(layout, ensure_ascii=False), name))
        for name, raw in rows('SELECT name,last_known_versions FROM "tabUser" WHERE last_known_versions LIKE %s',
                              ('%"bizbase_mgmt"%',)):
            versions = json.loads(raw)
            if OLD in versions:
                need(not done and NEW not in versions, '用户版本快照冲突')
                versions[NEW] = versions.pop(OLD)
                cur.execute('UPDATE "tabUser" SET last_known_versions=%s WHERE name=%s', (json.dumps(versions), name))
        # Site-specific code and opaque workspace configuration must be reviewed, not string-replaced.
        for table, field in [('tabServer Script','script'), ('tabClient Script','script'), ('tabReport','query'),
                             ('tabReport','report_script'), ('tabWorkspace','content'), ('tabCustom Workspace','content'),
                             ('tabCustom Workspace','widgets')]:
            need(not rows(sql.SQL('SELECT 1 FROM {} WHERE {} ~ %s LIMIT 1').format(ident(table), ident(field)),
                          (r'\m(bizbase_mgmt|bizbase-mgmt)\M',)), f'需人工评估旧引用：{table}.{field}')
        if done:
            return False
        for table, field in [('tabModule Def','module_name'), ('tabModule Def','app_name'), ('tabModule Def','name'),
                             ('tabWorkspace','title'), ('tabWorkspace','label'), ('tabWorkspace','name'),
                             ('tabCustom Workspace','name')]:
            cur.execute(sql.SQL('UPDATE {} SET {}=%s WHERE name=%s').format(ident(table), ident(field)), (NEW, OLD))
        cur.execute('UPDATE "tabDefaultValue" SET defvalue=%s WHERE name=%s',
                    (json.dumps([NEW if app == OLD else app for app in apps]), key))
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True)
    site = parser.parse_args().site
    import frappe
    sites = Path('/home/frappe/frappe-bench/sites')
    need(Path(site).name == site and (sites / site / 'site_config.json').is_file(), '无效站点')
    frappe.init(site=site, sites_path=str(sites))
    cfg = frappe.conf
    try:
        need(cfg.db_type == 'postgres', '仅支持 PostgreSQL')
        conn = psycopg2.connect(dbname=cfg.db_name, user=cfg.db_user or cfg.db_name, password=cfg.db_password,
                                host=cfg.db_host, port=cfg.db_port or 5432, connect_timeout=10)
        try:
            changed = migrate(conn, cfg.db_schema or 'public', cfg.maintenance_mode)
        finally:
            conn.close()
        # Retry even on no-op: a prior attempt may have committed before Redis became available.
        keys = ('defaults::__global', 'installed_app_modules', 'all_apps', 'app_modules', 'app_hooks')
        for k in keys:
            frappe.client_cache.delete_value(k)
        need(not frappe.cache.exists(*(frappe.cache.make_key(k) for k in keys)), '安装缓存未失效；保持停写并重试')
        print('管理看板身份已迁移，待切换清单及镜像。' if changed else '已迁移，已复核身份并刷新安装缓存。')
    finally:
        frappe.destroy()


if __name__ == '__main__':
    try:
        main()
    except psycopg2.Error as exc:
        raise SystemExit(f'数据库迁移失败（{type(exc).__name__}/{exc.pgcode}）；保持维护状态。') from None
