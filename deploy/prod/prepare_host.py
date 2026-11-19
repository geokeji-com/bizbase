"""First install only. Run as root on the BizBase ECS, never on the workstation."""

import configparser
import json
import os
import secrets
import stat
from pathlib import Path
from urllib.parse import quote


SITE = 'bizbase.geokeji.com'
DATA = Path('/var/lib/bizbase-prod')
SECRETS = Path('/etc/bizbase')
UID = 1000  # frappe in the upstream image


def create(path, text, owner=UID, mode=0o600):
    with path.open('x') as f:
        os.fchmod(f.fileno(), mode)
        os.fchown(f.fileno(), owner, 0)
        f.write(text + '\n')


def main():
    os.umask(0o077)
    src = SECRETS / 'connections.ini'
    if src.is_symlink() or src.stat().st_uid != 0 or stat.S_IMODE(src.stat().st_mode) & 0o077:
        raise SystemExit('connections.ini must be root-owned, mode 0600')
    cfg = configparser.ConfigParser(interpolation=None)
    with src.open() as f:
        cfg.read_file(f)
    pg, redis = cfg['postgres'], cfg['redis']
    if pg['database'] != 'bizbase' or pg['username'] != 'bizbase_app':
        raise SystemExit('Unexpected database or schema owner')
    tls = redis.getboolean('tls', False) or redis.getboolean('ssl', False)
    url = '{}://{}:{}@{}:{}'.format('rediss' if tls else 'redis',
                                    quote(redis.get('username', ''), safe=''),
                                    quote(redis['password'], safe=''), redis['host'], int(redis['port']))
    common = dict(bench_id='bizbase-prod', redis_cache=url+'/2', redis_queue=url+'/4',
                  redis_socketio=url+'/4', socketio_port=9000, default_site=SITE,
                  chromium_path='/usr/lib/chromium/chromium-headless-shell')
    site = dict(db_type='postgres', db_name=pg['database'], db_schema='bizbase_app',
                db_user=pg['username'], db_password=pg['password'], db_host=pg['host'],
                db_port=int(pg['port']), host_name='https://'+SITE, developer_mode=0)
    sites = DATA / 'sites'
    admin = SECRETS / 'initial-admin-password'
    if DATA.exists() or admin.exists():
        raise SystemExit('Refusing to overwrite an existing installation')
    DATA.mkdir(mode=0o700)
    for folder in (sites, sites / SITE, DATA / 'logs'):
        folder.mkdir(mode=0o700)
        os.chown(folder, UID, 0)
    (sites / 'assets').symlink_to('/home/frappe/frappe-bench/assets')
    create(sites / 'apps.txt', 'frappe\nerpnext\ngeo_operations\nyishan_id_login\nstatic_share')
    create(sites / 'common_site_config.json', json.dumps(common, indent=2))
    create(sites / SITE / 'site_config.json', json.dumps(site, indent=2))
    # The parent is root-only on the host. Mount this file only for the init job.
    create(admin, secrets.token_urlsafe(32), mode=0o400)
    print('Site configuration staged; generated password retained on this host only.')


if __name__ == '__main__':
    main()
