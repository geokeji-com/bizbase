"""Mounted read-only in one-shot rehearsal containers. No live-site argument."""
import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path

SITE = 'routes-rehearsal.invalid'
SCHEMA = 'bizbase_rehearsal'
BENCH = Path('/home/frappe/frappe-bench')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import preserve_geo as preservation

BOARDS = preservation.BOARDS
LEGACY = {'frappe', 'erpnext', 'geo_operations', 'yishan_id_login', 'static_share'}
RENAMED = {'frappe', 'erpnext', 'yishan_id', 'file_share'}
SUFFIX = ('', ' Version', ' User', ' Role', ' Access Log')


def need(ok, why):
    if not ok:
        raise preservation.Stop(why)


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def source():
    # No site code imported here. Never scan customer files.
    for root in (BENCH / 'apps', Path('/opt/rehearsal')):
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
            for name in files:
                p = Path(folder, name)
                if p == Path(__file__) or p.suffix not in ('.py', '.sql', '.sh'):
                    continue
                if p.is_file() and b'bizbase_app' in p.read_bytes().lower():
                    raise preservation.Stop('explicit production schema in executable source: ' + str(p))


def scope():
    import frappe
    import psycopg2
    os.chdir(BENCH / 'sites')
    frappe.init(site=SITE)
    c = frappe.conf
    need((c.db_type, c.db_name, c.db_schema, c.db_user, c.db_host, c.maintenance_mode, c.mute_emails,
          c.pause_scheduler, c.redis_cache, c.redis_queue, c.redis_socketio) ==
         ('postgres', 'bizbase', SCHEMA, 'bizbase_app', 'rds-only', 1, 1, 1, 'redis://rehearsal-redis:6379/0',
          'redis://rehearsal-redis:6379/1', 'redis://rehearsal-redis:6379/1'), 'unsafe effective config')
    need(os.environ.get('PGOPTIONS') == '-csearch_path=' + SCHEMA, 'PGOPTIONS missing')
    q = '''select current_database(), current_user, current_schema(), current_schemas(false),
        to_regclass('"tabUser"')::oid = to_regclass(%s)::oid'''
    params = (SCHEMA + '."tabUser"',)
    expected = ('bizbase', 'bizbase_app', SCHEMA, [SCHEMA], True)
    conn = psycopg2.connect(dbname=c.db_name, user=c.db_user, host=c.db_host, port=c.db_port, password=c.db_password)
    try:
        with conn.cursor() as cur:
            cur.execute(q, params)
            need(cur.fetchone() == expected, 'raw libpq schema/relation mismatch')
            # Defaults/FKs/views/triggers must not point back into the live namespace.
            cur.execute('''select exists(select 1 from pg_constraint c join pg_class t on t.oid=c.confrelid
                where c.connamespace=current_schema()::regnamespace and t.relnamespace<>c.connamespace)
                or exists(select 1 from pg_attrdef d join pg_class c on c.oid=d.adrelid
                where c.relnamespace=current_schema()::regnamespace and lower(pg_get_expr(d.adbin,d.adrelid)) like %s)
                or exists(select 1 from pg_views where schemaname=current_schema() and lower(definition) like %s)
                or exists(select 1 from pg_foreign_table t join pg_class c on c.oid=t.ftrelid
                where c.relnamespace=current_schema()::regnamespace)
                or exists(select 1 from pg_trigger t join pg_class c on c.oid=t.tgrelid
                where c.relnamespace=current_schema()::regnamespace and not t.tgisinternal)
                or exists(select 1 from pg_proc where pronamespace=current_schema()::regnamespace
                and (prosecdef or proconfig is not null or lower(prosrc) like %s))''', ('%bizbase_app%',)*3)
            need(cur.fetchone() == (False,), 'unsafe cross-schema object, trigger, default or routine in restored catalog')
    finally:
        conn.close()
    frappe.connect()
    need(tuple(frappe.db.sql(q, params)[0]) == expected, 'Frappe schema/relation mismatch')
    return frappe


def apps(f, expected):
    got = f.get_installed_apps()
    need(len(got) == len(expected) and set(got) == expected, 'installed app list mismatch: ' + str(got))
    need(set(f.get_all('Installed Application', pluck='app_name')) == expected, 'version list mismatch')


def geo(f):
    raw = preservation.audit(f)
    for dt,col in (('Server Script','script'),('Report','query')):
        need(not f.get_all(dt, filters={col:['like','%bizbase_app%']}, limit=1), 'site code references live schema')
    return raw


def sha_file(p):
    need(p.resolve(strict=True) == p and p.is_file(), 'unsafe or missing attachment')
    h = hashlib.sha256()
    with p.open('rb') as s:
        for block in iter(lambda:s.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def snapshot(f, new, archive):
    prefix = 'File Share' if new else 'Static Share'
    module = 'yishan_id' if new else 'yishan_id_login'
    app = 'file_share' if new else 'static_share'
    canonical = {prefix+s:'share'+s for s in SUFFIX} | {module:'identity', app:'share-app'}
    need(f.db.get_value('Module Def',module,'app_name') == module and
         f.db.get_value('Module Def',prefix,'app_name') == app and
         f.db.get_value('DocType','Yishan ID Binding','module') == module, 'renamed metadata mismatch')
    need(set(f.get_all('DocType', filters={'module':prefix}, pluck='name')) == {prefix+s for s in SUFFIX}, 'share DocTypes mismatch')
    result = {}
    def save(key, rows):
        result[key] = {'count':len(rows), 'digest':digest(rows)}
    save('bindings', f.db.sql('SELECT name,yishan_uid,"user",enabled FROM "tabYishan ID Binding" ORDER BY name'))
    for suffix, cols in [('', 'name,owner,title,status,current_version,access_level,access_salt,upload'),
                         (' Version', 'name,parent,parentfield,parenttype,version,entry,source_file,file_count,total_size'),
                         (' Role','name,parent,parentfield,parenttype,role'), (' User','name,parent,parentfield,parenttype,"user"'),
                         (' Access Log','name,share,share_owner,viewer,result,version')]:
        rows = f.db.sql(f'SELECT {cols} FROM "tab{prefix+suffix}" ORDER BY name')
        if suffix in (' Version',' User',' Role'):
            need(all(row[3] == prefix for row in rows), 'wrong child parenttype')
            rows = [r[:3]+r[4:] for r in rows]
        save('shares'+suffix,rows)
    def normalize(rows, idx):
        return [tuple(canonical.get(v,v) if i == idx else v for i,v in enumerate(r)) for r in rows]
    save('files',normalize(f.db.sql('SELECT name,file_url,is_private,attached_to_doctype,attached_to_name FROM "tabFile" ORDER BY name'),3))
    # These exact identities are checked separately against the frozen restriction.
    block = preservation.validate(archive)['block'][0]
    handled = tuple(preservation.restriction_names(block)) if new else (block['name'],)
    save('blocks',normalize(f.db.sql('SELECT name,parent,module FROM "tabBlock Module" WHERE name NOT IN %s ORDER BY name', (handled,)),2))
    result['geo_archive'] = preservation.digest(archive)
    save('user defaults',normalize(f.db.sql('SELECT name,default_app FROM "tabUser" ORDER BY name'),1))
    save('system default',normalize([(f.db.get_single_value('System Settings','default_app'),)],0))
    save('share passwords',f.db.sql('SELECT name,fieldname,password,encrypted FROM "__Auth" WHERE doctype=%s ORDER BY name,fieldname',(prefix,)))
    save('record grants',f.db.sql('SELECT name,"user",share_name,everyone,read,write,share FROM "tabDocShare" WHERE share_doctype=%s ORDER BY name',(prefix,)))
    for dt in ('Company','Employee','Customer','Supplier','Sales Invoice','GL Entry','Item','Lead','Opportunity'):
        save(dt,f.db.sql(f'SELECT name FROM "tab{dt}" ORDER BY name'))
    for key,n in (('bindings',33),('shares',1),('shares Version',1)):
        need(result[key]['count'] == n, 'checkpoint count changed; re-inventory: '+key)
    root = BENCH / 'sites' / SITE
    attachments = {}
    for name,version,entry,url in f.db.sql(f'SELECT parent,version,entry,source_file FROM "tab{prefix} Version"'):
        need(re.fullmatch(r'[A-Za-z0-9]{10}',name) and Path(url).parent.as_posix() == '/private/files', 'non-local share source')
        tree = root / 'private/files/.static_share' / name / str(version)
        need((tree/entry).resolve(strict=True).is_relative_to(tree) and (tree/entry).is_file(), 'missing/unsafe entry')
        for p in [root/url.lstrip('/'), *(p for p in tree.rglob('*') if p.is_file())]:
            attachments[str(p.relative_to(root))] = sha_file(p)
    save('share content',sorted(attachments.items()))
    save('share visibility',access(f,prefix,app,new))
    return result


def access(f, dt, app, new):
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request
    view = importlib.import_module(app+'.serve')
    accounts = sorted(set(f.get_all('User',filters={'enabled':1,'user_type':'System User'},pluck='name')) | {'Guest','Administrator'})
    shares = [f.get_doc(dt,n) for n in f.get_all(dt,pluck='name')]
    rows, ordinary = [], 0
    for u in accounts:
        f.set_user(u)
        f.local.request = Request(EnvironBuilder(path='/').get_environ())
        manager = u == 'Administrator' or 'System Manager' in f.get_roles()
        binding = bool(f.has_permission('Yishan ID Binding','read'))
        need(binding == manager,'binding data permission drift')
        if u not in ('Guest','Administrator') and not manager:
            ordinary += 1
        if new:
            for board in BOARDS:
                need(bool(importlib.import_module(board).can_access_app()) == manager, 'board permission mismatch')
        try:
            visible = set(f.get_list(dt,pluck='name',limit_page_length=0))
        except f.PermissionError:
            visible = set()
        for s in shares:
            allowed = bool(f.has_permission(dt,'read',doc=s))
            decision = view.viewer_decision(s,u)
            need(allowed == (s.name in visible), 'list/document permissions disagree')
            if u == 'Guest':
                need(not allowed and decision == {'Password':'password','Public':'view','Internal':'login','Specified':'login'}[s.access_level], 'anonymous share rules changed')
            if u == 'Administrator':
                need(allowed,'Administrator cannot read share')
            rows.append((u,s.name,binding,allowed,decision))
    f.set_user('Administrator')
    need(ordinary > 0,'no ordinary enabled Desk user for denial test')
    return rows


def insights(f):
    from insights.insights.doctype.insights_data_source_v3.connectors.frappe_db import get_sitedb_connection
    d = f.get_doc('Insights Data Source v3','Site DB')
    need(d.database_type == 'PostgreSQL' and not d.connection_string and d.schema in (None,'',SCHEMA) and
         d.host in (None,'','rds-only') and d.username in (None,'','bizbase_app'), 'unexpected Insights connection override')
    conn = get_sitedb_connection()
    try:
        row = conn.raw_sql('SELECT current_database(),current_schema(),count(*) FROM "tabYishan ID Binding"').fetchone()
        need(tuple(row) == ('bizbase',SCHEMA,33),'Insights sees wrong schema or actual binding table')
    finally:
        conn.disconnect()


def main(mode):
    if mode == 'source':
        return source()
    f = scope()
    baseline = BENCH / 'sites' / SITE / 'private/before.json'
    try:
        if mode == 'before':
            apps(f,LEGACY)
            archive = geo(f)
            baseline.write_text(json.dumps(snapshot(f,False,archive),sort_keys=True))
        elif mode == 'removed':
            apps(f,LEGACY-{'geo_operations'})
            need(not f.db.exists('Module Def','geo_operations') and not f.db.exists('Workspace','geo_operations'),'GEO not removed')
        elif mode == 'renamed':
            apps(f,RENAMED)
        elif mode in ('pre-migrate', 'after'):
            apps(f,RENAMED|{'crm','insights',*BOARDS})
            before = json.loads(baseline.read_text())
            path = baseline.parent / preservation.ARCHIVE
            preservation.preserve(f, path, before['geo_archive'], apply=False)
            if mode == 'pre-migrate':
                return
            after = snapshot(f,True,preservation.read_private(path))
            need(after == before,'data/permissions changed: '+str([k for k in before if before[k] != after.get(k)]))
            insights(f)
        else:
            need(mode == 'scope','unknown mode')
    finally:
        f.db.rollback()
        f.destroy()


if __name__ == '__main__':
    try:
        with preservation.quiet_framework():
            main(sys.argv[1])
    except preservation.Stop as exc:
        sys.exit(str(exc))
    except Exception as exc:
        sys.exit('Stopped: ' + type(exc).__name__)
    print('Verified', sys.argv[1], SCHEMA)
