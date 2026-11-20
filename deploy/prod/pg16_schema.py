"""Root-only ECS helper. See OPERATIONS.md for usage and permissions."""

import argparse
import configparser
import hashlib
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path('/var/backups/bizbase-pg16')
CONFIG = Path('/etc/bizbase/connections.ini')
IMAGE = 'postgres:16-alpine'
SOURCE = 'bizbase_app'
TARGET = 'bizbase_rehearsal'
# CLI stdout carries the archive or SQL. Keep it out of Docker's logging driver.
CONTAINER = ['docker', 'run', '--rm', '--pull=never', '--log-driver=none']
PSQL = ['psql', '-XqAtw', '-v', 'ON_ERROR_STOP=1', '-P', 'pager=off']
PORTABLE = ['--no-owner', '--no-acl', '--no-tablespaces', '--no-comments', '--no-security-labels']
GUARD = """SET search_path = pg_catalog;
SET row_security = off;
DO $$ BEGIN
 IF current_setting('server_version_num')::int / 10000 <> 16 THEN
   RAISE EXCEPTION 'PG16 required';
 END IF;
END $$;
"""
REMOTE_GUARD = GUARD + """DO $$ BEGIN
 IF current_database() <> 'bizbase' OR current_user <> 'bizbase_app' THEN
   RAISE EXCEPTION 'wrong identity';
 END IF;
END $$;
"""


class Stop(Exception):
    pass


def run(args, stage, **kwargs):
    kwargs.setdefault('stdout', subprocess.PIPE)
    result = subprocess.run(args, stderr=subprocess.DEVNULL, **kwargs)
    if result.returncode:
        raise Stop(stage)
    return result.stdout


def private(path, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (path != path.resolve() or not kind(info.st_mode) or info.st_uid != 0
            or info.st_mode & 0o077):
        raise Stop('文件或目录须由 root 独占，且路径不能经过符号链接')


def bind(path, dest):
    return ['--mount', 'type=bind,src={},dst={},readonly'.format(path, dest)]


def remote(auth, readonly):
    private(CONFIG)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(CONFIG, encoding='utf-8')
    pg = cfg['postgres']
    if pg['database'] != 'bizbase' or pg['username'] != SOURCE:
        raise Stop('连接配置的数据库或用户不匹配')
    fields = dict(host=pg['host'], port=str(int(pg['port'])), dbname='bizbase',
                  user=SOURCE, connect_timeout='10', sslmode=pg.get('sslmode', 'prefer'))
    password = pg['password']
    if any(not v or any(c in v for c in '\r\n\x00') for v in [password, *fields.values()]):
        raise Stop('不支持空值或多行连接参数')
    auth.mkdir(mode=0o700)
    (auth / 'service').write_text('[release]\n' + ''.join(f'{k}={v}\n' for k, v in fields.items()))
    (auth / 'pass').write_text('*:*:*:*:' + password.replace('\\', '\\\\').replace(':', '\\:') + '\n')
    args = [*CONTAINER, '-i', '--network', 'host',
            *bind(auth, '/auth'), '-e', 'PGSERVICE=release', '-e', 'PGSERVICEFILE=/auth/service',
            '-e', 'PGPASSFILE=/auth/pass']
    if readonly:
        args += ['-e', 'PGOPTIONS=-c default_transaction_read_only=on']
    return args


@contextmanager
def session(cmd):
    proc = subprocess.Popen(cmd + PSQL, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    try:
        yield proc
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.wait()


def query(proc, sql, stage):
    marker = secrets.token_hex(24).encode()
    proc.stdin.write(sql.encode() + b'\n\\echo ' + marker + b'\n')
    proc.stdin.flush()
    lines = []
    for line in proc.stdout:
        if line.rstrip(b'\n') == marker:
            return lines
        lines.append(line.rstrip(b'\n').decode('ascii'))
    raise Stop(stage)


def counts(proc, schema):
    # Hex identifiers also handle quoted names, delimiters and newlines.
    rows = query(proc, f"""SET search_path = pg_catalog;
SELECT format('SELECT %L || count(*)::text FROM ONLY %I.%I',
              encode(convert_to(relname,'UTF8'),'hex') || '=', '{schema}', relname)
FROM pg_class WHERE relnamespace='{schema}'::regnamespace AND relkind IN ('r','p')
ORDER BY relname COLLATE "C"
\\gexec""", '逐表计数失败')
    if not rows or not all(re.fullmatch(r'[0-9a-f]+=[0-9]+', r) for r in rows):
        raise Stop('未取得完整表计数')
    return rows


# Include table-owned objects (defaults, rules, constraints, indexes, TOAST),
# even when the catalog address itself has no namespace. Check both directions.
DEPENDENCIES = """WITH RECURSIVE members(cls,id) AS (
  SELECT 'pg_namespace'::regclass::oid, to_regnamespace('{schema}')::oid
  UNION
  SELECT d.classid, d.objid FROM pg_depend d JOIN members m
    ON (d.refclassid,d.refobjid)=(m.cls,m.id)
  WHERE m.cls='pg_namespace'::regclass OR d.deptype IN ('a','i','P','S')
), edges AS (
  SELECT d.refclassid cls, d.refobjid id FROM pg_depend d
    JOIN members m ON (m.cls,m.id)=(d.classid,d.objid)
  UNION
  SELECT d.classid, d.objid FROM pg_depend d
    JOIN members m ON (m.cls,m.id)=(d.refclassid,d.refobjid)
), external AS (
  SELECT * FROM edges EXCEPT SELECT * FROM members
)
SELECT EXISTS (SELECT FROM external e,
  LATERAL pg_identify_object(e.cls,e.id,0) o
  WHERE coalesce(o.schema,'') NOT IN ('pg_catalog','pg_toast'))
OR EXISTS (SELECT FROM members m, LATERAL pg_identify_object(m.cls,m.id,0) o
  WHERE o.schema NOT IN (quote_ident('{schema}'),'pg_toast'));
"""


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def backup(work):
    client = remote(work / 'auth', True) + [IMAGE]
    bundle = work / 'bundle'
    bundle.mkdir(mode=0o700)
    archive = bundle / 'bizbase_app.dump'
    with session(client) as proc:
        lines = query(proc, REMOTE_GUARD + "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
                      "SELECT pg_export_snapshot();", '源端版本、身份或快照检查失败')
        if len(lines) != 1 or not re.fullmatch('[0-9A-Fa-f-]+', lines[0]):
            raise Stop('导出快照失败')
        # COUNT holds AccessShare locks through pg_dump, including against TRUNCATE.
        expected = counts(proc, SOURCE)
        with archive.open('xb') as out:
            run(client + ['pg_dump', '-w', '-Fc', '-n', SOURCE, '--snapshot', lines[0]],
                '源端 pg_dump 失败', stdout=out)
            out.flush()
            os.fsync(out.fileno())
        cross = query(proc, DEPENDENCIES.format(schema=SOURCE), '源端依赖检查失败')
        if cross not in (['t'], ['f']):
            raise Stop('源端依赖检查结果无效')
        query(proc, 'COMMIT;', '只读事务结束失败')
    checksum = digest(archive)
    with (bundle / 'manifest.json').open('x') as manifest:
        json.dump(dict(sha256=checksum, counts=expected, cross_schema=cross == ['t']), manifest)
        manifest.write('\n')
        manifest.flush()
        os.fsync(manifest.fileno())
    name = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + secrets.token_hex(4)
    bundle.rename(ROOT / name)
    for directory in (ROOT / name, ROOT):
        fd = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    print('备份目录 {}，SHA-256 {}'.format(ROOT / name, checksum), flush=True)
    return name


@contextmanager
def isolated():
    name = 'bizbase-pg16-' + secrets.token_hex(12)
    run([*CONTAINER, '-d', '--network', 'none', '--name', name,
         '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', IMAGE, 'postgres', '-c', 'listen_addresses='],
        '临时 PG16 启动失败')
    cmd = ['docker', 'exec', '-i', name]
    try:
        for _ in range(90):
            ready = subprocess.run(cmd + ['sh', '-c', 'test "$(cat /proc/1/comm)" = postgres && pg_isready -q'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise Stop('临时 PG16 未就绪')
        run(cmd + PSQL + ['-U', 'postgres'], '临时库初始化失败', input=(
            b'CREATE ROLE archive_owner LOGIN;\nCREATE DATABASE restored OWNER archive_owner TEMPLATE template0;\n'))
        yield ['docker', 'exec', '-i', '-e', 'PGDATABASE=restored', '-e', 'PGUSER=archive_owner', name]
    finally:
        run(['docker', 'rm', '-fv', name], '临时 PG16 清理失败')


# Catalog dependencies do not capture dynamic SQL, text lookups, or arbitrary
# executable expressions. Only transfer declarative tables and their keys.
SAFE_OBJECTS = """SET search_path=pg_catalog;
WITH ns AS (SELECT 'bizbase_rehearsal'::regnamespace AS id),
rels AS (SELECT c.* FROM pg_class c, ns WHERE c.relnamespace=ns.id),
unsupported_defaults AS (
 SELECT d.* FROM pg_attrdef d WHERE adrelid IN (SELECT oid FROM rels)
   AND pg_get_expr(adbin,adrelid) !~ $rx$^(NULL|true|false|-?[0-9]+(\\.[0-9]+)?|'([^']|'')*')(::[a-z][a-z0-9_ .]*(\\([0-9, ]+\\))?(\\[\\])?)?$$rx$
   AND pg_get_expr(adbin,adrelid) NOT IN ('now()', 'CURRENT_TIMESTAMP', 'CURRENT_DATE', 'CURRENT_TIME')
   AND pg_get_expr(adbin,adrelid) NOT IN (SELECT format('nextval(%L::regclass)',oid::regclass::text)
                                          FROM rels WHERE relkind='S')
), partial_indexes AS (
 SELECT i.*, x.relname AS index_name, t.relname AS table_name
 FROM pg_index i JOIN rels x ON x.oid=i.indexrelid JOIN rels t ON t.oid=i.indrelid
 WHERE i.indpred IS NOT NULL
)
SELECT category || '=' || n FROM (VALUES
 ('relation_kind', (SELECT count(*) FROM rels WHERE relkind NOT IN ('r','S','i'))),
 ('row_security', (SELECT count(*) FROM rels WHERE relrowsecurity)),
 ('routine', (SELECT count(*) FROM pg_proc, ns WHERE pronamespace=ns.id)),
 ('user_trigger', (SELECT count(*) FROM pg_trigger WHERE tgrelid IN (SELECT oid FROM rels) AND NOT tgisinternal)),
 ('rewrite_rule', (SELECT count(*) FROM pg_rewrite WHERE ev_class IN (SELECT oid FROM rels))),
 ('check_constraint', (SELECT count(*) FROM pg_constraint, ns WHERE connamespace=ns.id AND contype='c')),
 ('other_constraint', (SELECT count(*) FROM pg_constraint, ns WHERE connamespace=ns.id AND contype NOT IN ('p','u','f','c'))),
 ('expression_index', (SELECT count(*) FROM pg_index WHERE indexrelid IN (SELECT oid FROM rels) AND indexprs IS NOT NULL)),
 ('partial_index', (SELECT count(*) FROM partial_indexes i WHERE NOT (
     i.table_name='tabAutomation Trigger Queue' AND i.index_name='unique_dedup_key'
     AND i.indisunique AND i.indexprs IS NULL AND pg_get_expr(i.indpred,i.indrelid) IN (
     $predicate$(((status)::text = ANY ((ARRAY['Pending'::character varying, 'Scheduled'::character varying])::text[])) AND (resume_run IS NULL))$predicate$,
     -- PG16 reparses the dumped ANY array by casting each member to text.
     $predicate$(((status)::text = ANY (ARRAY[('Pending'::character varying)::text, ('Scheduled'::character varying)::text])) AND (resume_run IS NULL))$predicate$)))),
 ('generated_column', (SELECT count(*) FROM pg_attribute WHERE attrelid IN (SELECT oid FROM rels) AND attgenerated<>'' AND NOT attisdropped)),
 ('custom_column_type', (SELECT count(*) FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid
    WHERE attrelid IN (SELECT oid FROM rels) AND attnum>0 AND NOT attisdropped AND t.typnamespace <> 'pg_catalog'::regnamespace)),
 ('catalog_reference_type', (SELECT count(*) FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid
    WHERE attrelid IN (SELECT oid FROM rels) AND attnum>0 AND NOT attisdropped
      AND t.typname ~ '^_?reg(class|collation|config|dictionary|namespace|oper|operator|proc|procedure|role|type)$')),
 ('unrecognized_default', (SELECT count(*) FROM unsupported_defaults))
 ) AS review(category,n) WHERE n>0
UNION ALL
SELECT 'default_shape(node=' || coalesce(substring(d.adbin::text from '^\\{([A-Z0-9_]+)'), 'other')
    || ',type=' || CASE WHEN t.typnamespace='pg_catalog'::regnamespace AND t.oid<16384 THEN t.typname ELSE 'custom' END
    || ',functions=' || coalesce(f.names,'none') || ')=' || count(*)
FROM unsupported_defaults d JOIN pg_attribute a ON (a.attrelid,a.attnum)=(d.adrelid,d.adnum)
JOIN pg_type t ON t.oid=a.atttypid
CROSS JOIN LATERAL (
 SELECT string_agg(DISTINCT CASE WHEN p.oid<16384 AND p.pronamespace='pg_catalog'::regnamespace
                                 THEN p.proname::text ELSE 'custom' END, ',') AS names
 FROM regexp_matches(d.adbin::text, ':funcid ([0-9]+)', 'g') AS ids(val)
 LEFT JOIN pg_proc p ON p.oid=ids.val[1]::oid
) f
GROUP BY substring(d.adbin::text from '^\\{([A-Z0-9_]+)'), t.typnamespace,t.oid,t.typname,f.names
ORDER BY 1;
"""


def restore_bundle(work, name, mode):
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}', name):
        raise Stop('备份编号无效')
    bundle = ROOT / name
    archive = bundle / 'bizbase_app.dump'
    manifest = bundle / 'manifest.json'
    for path in (bundle, archive, manifest):
        private(path, path == bundle)
    meta = json.loads(manifest.read_text())
    if digest(archive) != meta['sha256']:
        raise Stop('归档 SHA-256 与备份清单不符')
    with isolated() as cmd:
        with archive.open('rb') as src:
            run(cmd + ['pg_restore', '-w', '-1', *PORTABLE, '-d', 'restored'],
                '同一归档在空白 PG16 恢复失败', stdin=src)
        with session(cmd) as proc:
            query(proc, GUARD, '临时实例版本检查失败')
            if counts(proc, SOURCE) != meta['counts']:
                raise Stop('隔离恢复与源快照的逐表计数不符')
            print('隔离恢复通过，已核对 {} 张表。'.format(len(meta['counts'])), flush=True)
            if mode == 'verify':
                return
            if meta['cross_schema'] is not False:
                raise Stop('源端记录了跨 schema 依赖')
            query(proc, 'ALTER SCHEMA bizbase_app RENAME TO bizbase_rehearsal;', '隔离改名失败')
            if query(proc, DEPENDENCIES.format(schema=TARGET), '改名后依赖检查失败') != ['f']:
                raise Stop('改名后仍存在跨 schema 依赖')
            findings = query(proc, SAFE_OBJECTS, '对象检查失败')
            if findings:
                raise Stop('需单独审查的类别及数量：' + ', '.join(findings))
            if mode == 'diagnose':
                print('源端及改名后依赖、对象类别检查通过。')
                return
        stage = work / 'stage'
        stage.mkdir(mode=0o700)
        with (stage / 'rehearsal.dump').open('xb') as out:
            run(cmd + ['pg_dump', '-Fc', '-n', TARGET, *PORTABLE], '改名归档失败', stdout=out)
    write_rehearsal(work, stage, meta['counts'])


def write_rehearsal(work, stage, expected):
    offline = [*CONTAINER, '--network', 'none', *bind(stage, '/work'), IMAGE]
    archive = '/work/rehearsal.dump'
    toc = run(offline + ['pg_restore', '-l', archive], '演练归档目录读取失败')
    entries = []
    schemas = 0
    for line in toc.splitlines():
        if not line or line.startswith(b';'):
            continue
        match = re.fullmatch(rb'\d+; \d+ \d+ (.+)', line)
        if not match:
            raise Stop('演练归档目录格式异常')
        entry = match[1]
        if entry == b'SCHEMA - bizbase_rehearsal archive_owner':
            schemas += 1
        elif re.match(rb'(TABLE|TABLE DATA|SEQUENCE|SEQUENCE SET|SEQUENCE OWNED BY|DEFAULT|INDEX|CONSTRAINT|FK CONSTRAINT) bizbase_rehearsal ', entry):
            entries.append(line)
        else:
            raise Stop('演练归档包含未经审查的对象类别或命名空间')
    if schemas != 1:
        raise Stop('演练归档的 schema 条目无效')
    (stage / 'objects.list').write_bytes(b'\n'.join(entries) + b'\n')
    with (stage / 'restore.sql').open('xb') as sql:
        run(offline + ['pg_restore', *PORTABLE, '-L', '/work/objects.list', '-f', '-', archive],
            '演练 SQL 生成失败', stdout=sql)
    client = remote(work / 'auth-target', False) + bind(stage, '/work') + [IMAGE]
    with session(client) as proc:
        # Serialize concurrent runs on the original namespace tuple. Undo the
        # RESTRICT probe to keep the existing schema OID, grants and owner.
        query(proc, REMOTE_GUARD + """BEGIN;
SET LOCAL lock_timeout='10s';
ALTER SCHEMA bizbase_rehearsal RENAME TO bizbase_rehearsal_empty_guard;
SAVEPOINT empty_check;
DROP SCHEMA bizbase_rehearsal_empty_guard RESTRICT;
ROLLBACK TO empty_check;
ALTER SCHEMA bizbase_rehearsal_empty_guard RENAME TO bizbase_rehearsal;
""", '目标版本、身份、空 schema、权限或锁检查失败')
        query(proc, '\\o /dev/null\n\\i /work/restore.sql\n\\o', '目标演练恢复失败')
        if counts(proc, TARGET) != expected:
            raise Stop('目标演练计数不符，事务回滚')
        query(proc, 'COMMIT;', '目标提交未得到确认，请先核对目标状态')
    print('演练回灌已提交，{} 张表与源快照计数一致。'.format(len(expected)))


def interrupted(signum, frame):
    raise Stop('运行中断，请核对最后报告的阶段')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    sub.add_parser('backup', help='只读备份并打印备份编号')
    for mode, help_text in (('verify', '在断网 PG16 内还原并核对计数'),
                            ('diagnose', '在断网 PG16 内改名并汇总需审查的对象'),
                            ('rehearse', '执行隔离校验后事务化导入空演练 schema')):
        sub.add_parser(mode, help=help_text).add_argument('backup_id')
    args = p.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    os.umask(0o077)
    if os.geteuid() != 0:
        raise Stop('请以 root 身份运行')
    ROOT.mkdir(mode=0o700, exist_ok=True)
    private(ROOT, True)
    with tempfile.TemporaryDirectory(prefix='.work-', dir=ROOT) as tmp:
        work = Path(tmp)
        if args.mode == 'backup':
            backup(work)
        else:
            restore_bundle(work, args.backup_id, args.mode)


if __name__ == '__main__':
    try:
        main()
    except Stop as exc:
        sys.exit('停止：' + str(exc))
    except (OSError, ValueError, KeyError, configparser.Error):
        sys.exit('停止：文件、配置或子进程通信失败。请在宿主核对权限、空间和运行状态。')
