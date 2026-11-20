"""Preserve the approved GEO overrides while the site is frozen (PG16).

Host: python3 -I preserve_geo.py backup BACKUP_ID   (beside pg16_schema.py)
Old image, before uninstall: env/bin/python -I preserve_geo.py apply --site SITE --sha256 DIGEST
New image, after installing boards, before and after migrate: same CLI with verify.
DIGEST is the SHA-256 printed by backup. Site archives live outside private/files.
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

GEO = 'geo_operations'
BOARDS = ('bizbase_mgmt', 'sales_board', 'ops_board', 'customer_board')
WIDGETS = ('links', 'shortcuts', 'charts', 'quick_lists', 'number_cards', 'custom_blocks')
SITES = Path('/home/frappe/frappe-bench/sites')
ARCHIVE = 'geo-preservation-v1.json'
REHEARSAL = 'routes-rehearsal.invalid'
# Keep PostgreSQL's JSON representation, including unmodified Long Text and every
# stored column. The same SELECT runs in the offline restore and the site transaction.
CAPTURE = '''SELECT jsonb_build_object('version',1,
 'workspace', (SELECT coalesce(jsonb_agg(w ORDER BY name COLLATE "C"),'[]') FROM "tabCustom Workspace" w
               WHERE workspace='geo_operations' OR name='geo_operations'),
 'roles', (SELECT coalesce(jsonb_agg(r ORDER BY name COLLATE "C"),'[]') FROM "tabHas Role" r
           WHERE parenttype='Custom Workspace' AND parent='geo_operations'),
 'block', (SELECT coalesce(jsonb_agg(b ORDER BY name COLLATE "C"),'[]') FROM "tabBlock Module" b
           WHERE module='geo_operations'))::text'''


class Stop(Exception):
    pass


def need(ok, message):
    if not ok:
        raise Stop(message)


@contextlib.contextmanager
def quiet_framework():
    # Frappe's PG exception handler prints query errors (including row data)
    # before re-raising. Only our own status/error messages may leave the CLI.
    with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        yield


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(raw):
    doc = json.loads(raw)
    need(doc['version'] == 1 and len(doc['workspace']) == len(doc['block']) == 1,
         'expected one legacy customization and one restriction')
    w, b = doc['workspace'][0], doc['block'][0]
    need(w['name'] == w['workspace'] == GEO and not json.loads(w['widgets'] or '{}'), 'unexpected customization')
    content = json.loads(w['content'])
    need(isinstance(content, list) and {part['type'] for part in content} == {'header', 'paragraph'}
         and all(isinstance(part['data']['text'], str) for part in content), 'unexpected layout')
    need(all(r['parentfield'] in ('added_roles', 'removed_roles') for r in doc['roles']), 'unknown role reference')
    need(b['parenttype'] == 'User' and b['parentfield'] == 'block_modules' and b['parent'] and b['module'] == GEO,
         'unexpected module restriction owner or field')
    return doc


def read_private(path):
    st = path.lstat()
    need(path.resolve() == path and stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()
         and stat.S_IMODE(st.st_mode) == 0o600, 'unsafe archive file')
    return path.read_bytes()


def publish(path, raw):
    # No overwrite, including on concurrent runs. An interrupted DB transaction
    # may leave a complete archive which must match the next attempt byte-for-byte.
    need(path.parent.resolve(strict=True) == path.parent, 'unsafe archive directory')
    with tempfile.NamedTemporaryFile(dir=path.parent) as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
        try:
            os.link(out.name, path)
        except FileExistsError:
            pass
        need(read_private(path) == raw, 'archive readback differs')
        directory = os.open(str(path.parent), os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def backup(backup_id):
    # -I omits the script directory. Import only the adjacent, deployed helper.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pg16_schema as pg
    need(os.geteuid() == 0 and re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}', backup_id), 'invalid backup scope')
    bundle = pg.ROOT / backup_id
    dump, manifest = bundle / (pg.SOURCE + '.dump'), bundle / 'manifest.json'
    for path in (pg.ROOT, bundle, dump, manifest):
        pg.private(path, path in (pg.ROOT, bundle))
    meta = json.loads(manifest.read_bytes())
    need(pg.digest(dump) == meta['sha256'], 'frozen dump checksum mismatch')
    with pg.isolated() as cmd:
        with dump.open('rb') as src:
            pg.run(cmd + ['pg_restore', '-w', '-1', *pg.PORTABLE, '-d', 'restored'], 'offline restore failed', stdin=src)
        with pg.session(cmd) as proc:
            need(pg.counts(proc, pg.SOURCE) == meta['counts'], 'restored counts differ')
        raw = pg.run(cmd + pg.PSQL, 'archive extraction failed', input=(
            'SET search_path TO ' + pg.SOURCE + ';\n' + CAPTURE + ';\n').encode()).rstrip(b'\n')
    validate(raw)
    publish(bundle / ARCHIVE, raw)
    print(digest(raw))


def captured(f):
    return f.db.sql(CAPTURE)[0][0].encode('utf-8')


def empty_workspace(f, name):
    ws = f.get_doc('Workspace', name)
    need(ws.module == name and json.loads(ws.content or '[]') == [] and all(not ws.get(k) for k in WIDGETS),
         'unexpected workspace content or module')


def audit(f):
    raw = captured(f)
    doc = validate(raw)
    block = doc['block'][0]
    need(f.db.exists('User', block['parent']), 'restriction owner missing')
    need({(df.fieldname, df.options) for df in f.get_meta('Custom Workspace').get_table_fields()}
         == {('added_roles', 'Has Role'), ('removed_roles', 'Has Role')}, 'unknown customization child table')
    need(not f.db.sql('SELECT 1 FROM "tabBlock Module" WHERE module IN %s LIMIT 1', (BOARDS,)),
         'target restriction already present')
    need(f.get_all('Module Def', filters={'app_name': GEO}, pluck='name') == [GEO]
         and not f.db.exists('DocType', {'module': GEO})
         and f.get_all('Workspace', filters={'module': GEO}, pluck='name') == [GEO], 'unexpected legacy module objects')
    empty_workspace(f, GEO)
    for app in f.get_installed_apps():
        need(GEO not in (f.get_hooks('required_apps', app_name=app) or []), 'app depends on GEO')
    fields = f.db.sql('''select parent,fieldname,options from "tabDocField" where fieldtype='Link'
        union select dt,fieldname,options from "tabCustom Field" where fieldtype='Link' ''')
    tables = set(f.db.get_tables(cached=False))
    for dt, field, target in fields:
        if target not in ('Module Def', 'Workspace', 'Custom Workspace') or 'tab'+dt not in tables or not f.db.has_column(dt, field):
            continue
        hits = f.get_all(dt, filters={field:GEO}, pluck='name')
        if hits:
            need((dt, field, target) in {('Workspace', 'module', 'Module Def'), ('Custom Workspace', 'workspace', 'Workspace')}
                 and hits == [GEO], 'unknown module/workspace link')
    for dt, cols in {'Server Script':['script'], 'Client Script':['script'], 'Report':['query','report_script'],
                     'Custom Field':['options','default'], 'Property Setter':['value'],
                     'Workspace Shortcut':['link_to','url'], 'Workspace Link':['link_to'],
                     'User':['default_app'], 'Block Module':['module']}.items():
        for col in cols:
            if f.db.has_column(dt, col):
                rows = f.get_all(dt, filters={col:['like','%geo_operations%']}, pluck='name')
                need(not rows or (dt, col, rows) == ('Block Module','module',[block['name']]), 'unknown GEO reference')
    need(not f.db.sql('SELECT 1 FROM "tabSingles" WHERE lower(value) LIKE %s LIMIT 1', ('%geo_operations%',)),
         'singleton setting references GEO')
    return raw


def restriction_names(block):
    # Preserve the original row identity. Stable names make partial or colliding
    # target rows distinguishable from a previously committed migration.
    return [block['name']] + [digest((block['name'] + '/' + m).encode())[:20] for m in BOARDS[1:]]


def verified(f, doc):
    need(all(not rows for k, rows in json.loads(captured(f)).items() if k != 'version'), 'legacy rows remain')
    block = doc['block'][0]
    need(f.db.exists('User', block['parent']), 'restriction owner missing')
    rows = f.db.sql('''SELECT name,module,parent,parenttype,parentfield FROM "tabBlock Module"
                       WHERE module IN %s''', (BOARDS,))
    need(set(rows) == {(name, module, block['parent'], 'User', 'block_modules')
         for name, module in zip(restriction_names(block), BOARDS)}, 'target restrictions differ')


def verify_boards(f):
    need(not f.db.exists('Module Def', GEO) and not f.db.exists('Workspace', GEO), 'legacy module still installed')
    for board in BOARDS:
        need(f.db.get_value('Module Def', board, 'app_name') == board and
             not f.db.exists('Custom Workspace', {'workspace': board}), 'target module or customization differs')
        empty_workspace(f, board)


def preserve(f, path, expected, apply):
    f.db.sql("SET LOCAL lock_timeout = '10s'")
    if apply:
        f.db.sql('LOCK TABLE "tabUser", "tabBlock Module", "tabCustom Workspace", "tabHas Role" IN SHARE ROW EXCLUSIVE MODE')
    if apply and f.db.exists('Custom Workspace', {'workspace': GEO}):
        raw = audit(f)
        need(digest(raw) == expected, 'site differs from the frozen archive')
        publish(path, raw)
        doc = validate(raw)
        block = doc['block'][0]
        f.db.delete('Has Role', {'parenttype':'Custom Workspace', 'parent':GEO})
        f.db.delete('Custom Workspace', {'workspace':GEO, 'name':GEO})
        f.db.set_value('Block Module', block['name'], 'module', BOARDS[0], update_modified=False)
        idx = f.db.sql('''SELECT coalesce(max(idx),0) FROM "tabBlock Module"
            WHERE parent=%s AND parenttype='User' AND parentfield='block_modules' ''', (block['parent'],))[0][0]
        for offset, (name, module) in enumerate(zip(restriction_names(block)[1:], BOARDS[1:]), 1):
            f.db.sql('''INSERT INTO "tabBlock Module" (name,module,idx,parent,parenttype,parentfield,
                owner,modified_by,creation,modified,docstatus) SELECT %s,%s,%s,parent,parenttype,parentfield,
                owner,modified_by,creation,modified,docstatus FROM "tabBlock Module" WHERE name=%s''',
                (name, module, idx+offset, block['name']))
    raw = read_private(path)
    need(digest(raw) == expected, 'private archive checksum mismatch')
    verified(f, validate(raw))
    if not apply:
        verify_boards(f)


def site_run(args):
    import frappe
    os.chdir(SITES)
    frappe.init(site=args.site)
    try:
        c = frappe.conf
        rehearsal = args.site == REHEARSAL
        schema = 'bizbase_rehearsal' if rehearsal else c.db_user
        need(c.db_type == 'postgres' and c.db_name == 'bizbase' and c.db_user == c.db_name + '_app'
             and c.db_schema == schema and str(c.maintenance_mode) == '1', 'wrong site config or site not frozen')
        if rehearsal:
            need(c.db_host == 'rds-only' and os.environ.get('PGOPTIONS') == '-csearch_path=' + schema,
                 'wrong rehearsal connection')
        frappe.connect()
        need(tuple(frappe.db.sql('SELECT current_database(),current_user,current_schemas(false)')[0]) ==
             (c.db_name, c.db_user, [schema]), 'wrong database scope')
        frappe.set_user('Administrator')
        apply = args.mode == 'apply'
        preserve(frappe, SITES / args.site / 'private' / ARCHIVE, args.sha256, apply)
        if apply:
            frappe.db.commit()
            frappe.clear_cache()
    except BaseException:
        if getattr(frappe.local, 'db', None):
            frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    sub.add_parser('backup').add_argument('backup_id')
    for mode in ('apply','verify'):
        s = sub.add_parser(mode)
        s.add_argument('--site', choices=('bizbase.geokeji.com', REHEARSAL), required=True)
        s.add_argument('--sha256', required=True)
    args = p.parse_args()
    if args.mode == 'backup':
        backup(args.backup_id)
    else:
        need(re.fullmatch('[a-f0-9]{64}', args.sha256), 'invalid archive digest')
        with quiet_framework():
            site_run(args)
        print('GEO preservation verified', args.mode)


if __name__ == '__main__':
    try:
        main()
    except Stop as exc:
        sys.exit('Stopped: ' + str(exc))
    except Exception as exc:
        # Framework/SQL exceptions can contain record names or archived prose.
        sys.exit('Stopped: ' + type(exc).__name__)
