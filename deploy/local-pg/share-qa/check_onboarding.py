"""Verify employee distribution and independently revocable terminals on the disposable site."""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

import frappe

from check_cli import Employee, USERS, check_response, db, fixtures, server


def installed(site, root, email, password):
    root.mkdir()
    employee = Employee(site, root, email, password)
    employee.env.update(HOME=str(employee.work), XDG_DATA_HOME=str(employee.work / 'data'))
    # Each employee starts with a blank home and no checkout. Fetch both files as Guest.
    base = site + '/assets/file_share/agent/'
    manifest = check_response(requests.get(base + 'manifest.json', timeout=10)).json()
    assert manifest['filename'] == 'bizbase.pyz'
    blob = check_response(requests.get(base + manifest['filename'], timeout=10)).content
    assert hashlib.sha256(blob).hexdigest() == manifest['sha256']
    source = root / manifest['filename']
    source.write_bytes(blob)
    def install():
        result = subprocess.run([sys.executable, '-I', str(source), 'install', '--site', site],
                                env=employee.env, cwd=root, text=True, capture_output=True, check=True)
        return json.loads(result.stdout)
    first = install()
    assert first['site'] == site and install()['command'] == first['command']
    assert all(Path(f).is_file() and 'whoami' in Path(f).read_text() for f in first['skills'])
    source.unlink()
    employee.command = first['command']
    employee.authorize()
    return employee


def records(session, site):
    r = session.get(site + '/api/resource/File%20Share%20Grant', params={
        'fields': json.dumps(['name', 'employee', 'device_label', 'revoked_at']), 'limit_page_length': 100})
    return check_response(r).json()['data']


def binding_revocation(terminal, admin):
    # Supply a synthetic, already verified provider lease; no request goes to the real IdP.
    uid = str(uuid.uuid4())
    with db():
        frappe.get_doc(dict(doctype='Yishan ID Binding', yishan_uid=uid, enabled=1,
                            user=terminal.email)).insert()
        sid = terminal.browser.cookies.get('sid')
        sessions = frappe.qb.DocType('Sessions')
        raw = frappe.qb.from_(sessions).select(sessions.sessiondata).where(sessions.sid == sid).run()[0][0]
        data = frappe.parse_json(raw)
        now = time.time()
        data.update(yid_uid=uid, yid_verified_at=now, yid_token_exp=now + 240, yid_lease_until=now + 240)
        frappe.qb.update(sessions).set(sessions.sessiondata, frappe.as_json(data)).where(sessions.sid == sid).run()
    assert terminal.cmd('whoami')['user'] == terminal.email
    check_response(admin.put(terminal.site + '/api/resource/Yishan%20ID%20Binding/' + uid, json={'enabled': 0}))
    assert terminal.cmd('whoami', success=False) is None


def run(site, root, password):
    page = check_response(requests.get(site + '/file-share-setup', timeout=10)).text
    assert all(text in page for text in ('移山 ID', '绑定', 'manifest.json', 'bizbase.pyz'))
    a = installed(site, root / 'first', USERS[0], password)
    first = {r['name'] for r in records(a.browser, site) if not r['revoked_at']}
    b = installed(site, root / 'second', USERS[0], password)
    second = {r['name'] for r in records(b.browser, site) if not r['revoked_at']} - first
    assert len(second) == 1
    target = second.pop()
    assert a.cmd('whoami') == b.cmd('whoami') == {'user': USERS[0]}
    peer = installed(site, root / 'peer', USERS[1], password)
    assert all(r['employee'] == USERS[1] for r in records(peer.browser, site))
    disable = site + '/api/method/file_share.cli_auth.disable_grant'
    for stranger in (requests.Session(), peer.browser):
        assert stranger.post(disable, json={'name': target}).status_code in (401, 403, 404)
    admin = requests.Session()
    check_response(admin.post(site + '/api/method/login', data={'usr': 'Administrator', 'pwd': os.environ['QA_DB_PASSWORD']}))
    desk = check_response(admin.get(site + '/desk/file-share-grant')).text
    token = re.search(r'frappe\.csrf_token\s*=\s*["\']([^"\']+)', desk)[1]
    admin.headers['X-Frappe-CSRF-Token'] = token
    assert set(USERS) <= {r['employee'] for r in records(admin, site)}
    check_response(admin.post(disable, json={'name': target}))
    check_response(admin.post(disable, json={'name': target}))
    assert b.cmd('whoami', success=False) is None and a.cmd('whoami')['user'] == USERS[0]
    assert peer.cmd('whoami')['user'] == USERS[1]
    assert any(r['name'] == target and r['revoked_at'] for r in records(admin, site))
    binding_revocation(a, admin)
    peer.cmd('logout')
    print('PASS anonymous first-party download + checksum + fresh home install + upgrade; '
          'two active terminals; ordinary/admin scope, targeted revocation and audit')


if __name__ == '__main__':
    os.chdir('sites')
    pwd = fixtures()
    with TemporaryDirectory() as temp, server() as origin:
        run(origin, Path(temp), pwd)
