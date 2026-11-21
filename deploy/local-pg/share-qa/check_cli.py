"""Exercise the employee CLI and its HTTP API on the disposable PostgreSQL site."""
import html
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
from wsgiref.simple_server import WSGIRequestHandler, make_server

import frappe
import requests
from frappe.app import application
from werkzeug.middleware.shared_data import SharedDataMiddleware
from werkzeug.test import Client

SITE = 'share-qa.test'
DOMAINS = ('company.example', 'channel-a.example')
CLI = '/qa-tools/bizbase'
USERS = ('share-author@example.test', 'share-peer@example.test')


@contextmanager
def db():
    frappe.init(site=SITE, sites_path=os.getcwd())
    frappe.connect()
    frappe.set_user('Administrator')
    try:
        yield
        frappe.db.commit()
    finally:
        frappe.destroy()


def fixtures():
    password = secrets.token_urlsafe(28)
    with db():
        for email in USERS:
            if not frappe.db.exists('User', email):
                frappe.get_doc(dict(doctype='User', email=email, first_name=email.split('@')[0],
                                    send_welcome_email=0, roles=[dict(role='Desk User')])).insert()
                frappe.get_doc(dict(doctype='Employee', name=email, user_id=email, status='Active')).db_insert()
            from frappe.utils.password import update_password
            update_password(email, password)
    return password


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        # Avoid printing authorization URLs or synthetic credentials in the test transcript.
        pass


@contextmanager
def server():
    def app(env, start_response):
        env['HTTP_X_FRAPPE_SITE_NAME'] = SITE
        return application(env, start_response)
    static = SharedDataMiddleware(app, {'/assets': str(Path.cwd() / 'assets')})
    with make_server('127.0.0.1', 0, static, handler_class=QuietHandler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{httpd.server_port}'
        finally:
            httpd.shutdown()
            thread.join(5)


def check_response(r, status=200):
    if r.status_code != status:
        try:
            detail = r.json().get('exc_type')
        except ValueError:
            detail = r.headers.get('content-type')
        raise AssertionError((urlsplit(r.url).path, status, r.status_code, detail))
    return r


class Employee:
    def __init__(self, site, work, email, password):
        self.site = site
        self.email = email
        self.browser = requests.Session()
        self.browser.trust_env = False
        check_response(self.browser.post(site + '/api/method/login', data={'usr': email, 'pwd': password}))
        self.work = work / email
        self.work.mkdir(mode=0o700)
        self.env = {**os.environ, 'XDG_CONFIG_HOME': str(self.work), 'BROWSER': 'false'}
        self.command = [sys.executable, CLI, '--site', self.site]

    def cmd(self, *args, success=True):
        cmd = [*self.command, '--json', *map(str, args)]
        result = subprocess.run(cmd, env=self.env, capture_output=True, text=True, timeout=45)
        record = json.loads(result.stdout)
        assert (result.returncode == 0) == success and record['success'] == success, (
            args[:2], result.returncode, record.get('error'))
        return record.get('data')

    def authorize(self):
        # Exercise CLI login itself. The fixture's browser consumes its authorization URL.
        # A tiny browser launcher hands that URL back without opening a host browser.
        authorize_url = self.work / 'login-url'
        launcher = self.work / 'test-browser'
        launcher.write_text('#!/bin/sh\nprintf "%s" "$1" > "$QA_LOGIN_URL"\n')
        launcher.chmod(0o700)
        env = {**self.env, 'BROWSER': str(launcher) + ' %s', 'QA_LOGIN_URL': str(authorize_url)}
        cmd = [*self.command, '--json', 'login']
        with subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
            try:
                for _ in range(200):
                    if authorize_url.exists() and authorize_url.stat().st_size:
                        break
                    if child.poll() is not None:
                        raise AssertionError(('CLI login exited', child.returncode))
                    threading.Event().wait(0.05)
                url = authorize_url.read_text()
                parts = urlsplit(url)
                assert url.startswith(self.site + '/') and parts.path == '/file-share-authorize'
                page = check_response(self.browser.get(url))
                challenge = parse_qs(parts.query)['challenge'][0]
                assert challenge in page.text
                csrf = re.search(r'data-csrf="([^"]+)"', page.text)
                assert csrf, 'The authorization page must initialize its own CSRF token'
                self.browser.headers.update({'X-Frappe-CSRF-Token': html.unescape(csrf[1])})
                check_response(self.browser.post(self.site + '/api/method/file_share.cli_auth.approve',
                                                 json={'challenge': challenge}))
                out, _ = child.communicate(timeout=20)
                assert child.returncode == 0 and json.loads(out)['success']
            finally:
                if child.poll() is None:
                    child.kill()
        assert self.cmd('whoami')['user'] == self.email
        [credential] = (self.work / 'bizbase').glob('*.token')
        self.token = credential.read_text().strip()

    def rpc(self, method, **fields):
        return requests.post(self.site + '/api/method/file_share.api.' + method,
                             headers={'X-BizBase-Share-Token': self.token}, json=fields, timeout=15)


def body(host, report, version):
    client = Client(application)
    options = dict(base_url='https://' + host, headers={'X-Frappe-Site-Name': SITE})
    path = '/file-share/s/' + report
    response = client.get(path, **options)
    if version is None:
        assert response.status_code == 404, (host, response.status_code)
        return
    assert response.status_code == 200
    src = re.search(r'<iframe src="([^"]+)"', response.get_data(as_text=True))[1]
    asset = client.get(html.unescape(src), **options)
    assert asset.status_code == 200 and f'employee content {version}' in asset.get_data(as_text=True)


def exercise(site, work, password):
    author, peer = [Employee(site, work, u, password) for u in USERS]
    for employee in (author, peer):
        employee.authorize()
    assert set(DOMAINS) <= {d['name'] for d in author.cmd('share', 'domains')}
    first = work / 'first.html'
    first.write_text('<p>employee content 1</p>')
    request_id = str(uuid.uuid4())
    args = ('share', 'upload', first, '--title', 'CLI QA', '--request-id', request_id)
    result = author.cmd(*args)
    report = result['share_id']
    assert result == author.cmd(*args)
    assert result['version'] == 1
    body(DOMAINS[0], report, None)
    assert report in [r['share_id'] for r in author.cmd('share', 'list')]
    assert report not in [r['share_id'] for r in peer.cmd('share', 'list')]
    peer.cmd('share', 'show', report, success=False)
    denied = peer.rpc('close', share_id=report, domain=DOMAINS[0], request_id=str(uuid.uuid4()))
    assert denied.status_code in (403, 404), denied.status_code
    parent = '/api/resource/File%20Share/' + report
    assert check_response(author.browser.get(site + parent)).json()['data']['owner'] == USERS[0]
    assert peer.browser.get(site + parent).status_code in (403, 404)
    scoped = requests.get(site + parent, headers={'X-BizBase-Share-Token': author.token}, timeout=15)
    assert scoped.status_code in (401, 403, 404)

    def publish(domain, version):
        rid = str(uuid.uuid4())
        command = ('share', 'publish', report, '--domain', domain, '--version', version,
                   '--access', 'public', '--request-id', rid)
        published = author.cmd(*command)
        assert published == author.cmd(*command)
        assert published['url'] == f'https://{domain}/file-share/s/{report}'
        return rid

    for domain in DOMAINS:
        publish(domain, 1)
        body(domain, report, 1)
    second = work / 'second.zip'
    with zipfile.ZipFile(second, 'w') as bundle:
        bundle.writestr('index.html', '<p>employee content 2</p>')
    assert author.cmd('share', 'upload', second, '--report', report)['version'] == 2
    body(DOMAINS[0], report, 1)
    eid = publish(DOMAINS[0], 2)
    body(DOMAINS[0], report, 2)
    body(DOMAINS[1], report, 1)
    assert author.rpc('get_report', share_id=report).json()['message'] == author.cmd('share', 'show', report)
    assert author.cmd('share', 'show', report)['versions'] == [1, 2]
    publish(DOMAINS[0], 1)
    body(DOMAINS[0], report, 1)
    author.cmd('share', 'close', report, '--domain', DOMAINS[0])
    body(DOMAINS[0], report, None)
    body(DOMAINS[1], report, 1)
    with db():
        rows = frappe.get_all('File Share Operation', filters={'share_id': report},
                              fields=['request_id', 'actor', 'operation', 'version', 'access_domain', 'creation'])
        assert len(rows) == 7 and all(r.actor == USERS[0] and r.creation for r in rows), rows
        assert any(r.request_id == eid and r.operation == 'publish' and r.version == 2
                   and r.access_domain == DOMAINS[0] for r in rows)
    def password_get(host, code, method='GET', password=None):
        opts = dict(base_url='https://' + host, headers={'X-Frappe-Site-Name': SITE})
        r = guest.open('/file-share/s/' + report, method=method, data={'password': password} if password else {}, **opts)
        assert r.status_code == code, (method, r.status_code, code)

    # Verify that switching the published content does not silently widen the audience.
    assert author.cmd('share', 'publish', report, '--version', '2', '--domain', DOMAINS[0],
                      '--keep-access', success=False) is None
    for mode in ('internal', 'specified'):
        options = ('--user', USERS[1]) if mode == 'specified' else ()
        command = ('share', 'publish', report, '--version', '1', '--domain', DOMAINS[0], '--access', mode, *options)
        assert author.cmd(*command)['access_mode'] == mode.capitalize()
        assert author.cmd('share', 'publish', report, '--version', '2', '--domain', DOMAINS[0],
                          '--keep-access')['access_mode'] == mode.capitalize()
        guest = Client(application)
        password_get(DOMAINS[0], 302)
    guest = Client(application)
    pwd = secrets.token_urlsafe(20)
    check_response(author.rpc('publish', request_id=str(uuid.uuid4()), share_id=report, version=1,
                              domain=DOMAINS[0], access_mode='Password', password=pwd))
    password_get(DOMAINS[0], 401, 'POST', 'wrong-password')
    password_get(DOMAINS[0], 303, 'POST', pwd)
    password_get(DOMAINS[0], 200)
    assert author.cmd('share', 'publish', report, '--version', '2', '--domain', DOMAINS[0],
                      '--keep-access')['access_mode'] == 'Password'
    password_get(DOMAINS[0], 200)
    author.cmd('logout')
    assert author.rpc('whoami').status_code in (401, 403)
    check_response(peer.browser.post(site + '/api/method/logout'))
    assert peer.rpc('whoami').status_code in (401, 403)
    print('PASS employee CLI/API: browser grant, scoped identity, two employees/domains, drafts, '
          'HTML/ZIP, idempotent retries, pinned switch/rollback, selective close, audit and logout')


if __name__ == '__main__':
    os.chdir('sites')
    password = fixtures()
    with server() as origin, TemporaryDirectory() as temp:
        exercise(origin, Path(temp), password)
