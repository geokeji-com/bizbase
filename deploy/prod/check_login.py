"""ECS-only acceptance check via the production TLS endpoint. Never print response bodies."""

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests


BASE = 'https://bizbase.geokeji.com'


def check():
    with requests.Session() as session:
        session.trust_env = False

        def call(method, path, **kwargs):
            response = session.request(method, BASE + path, timeout=20, allow_redirects=False, **kwargs)
            if response.status_code != 200:
                raise RuntimeError(f'{path.split("?")[0]}: HTTP {response.status_code}')
            return response

        index = call('GET', '/login')
        assert 'login' in index.text.lower()
        styles = re.findall(r'href=["\'](/assets/[^"\']+\.css(?:\?[^"\']*)?)["\']', index.text)
        assert styles, 'login stylesheet missing'
        assert 'text/css' in call('GET', styles[0]).headers.get('Content-Type', '')
        password = Path('/etc/bizbase/initial-admin-password').read_text().strip()
        call('POST', '/api/method/login', data={'usr': 'Administrator', 'pwd': password})
        try:
            assert call('GET', '/api/method/frappe.auth.get_logged_user').json()['message'] == 'Administrator'
            desk = call('GET', '/desk/bizbase_mgmt')
            assert 'text/html' in desk.headers.get('Content-Type', '')
            for old, new in (
                ('/file-share', '/desk/file-share'),
                ('/desk/static-share', '/desk/file-share'),
                ('/desk/yishan_id_login/yishan-id-binding', '/desk/yishan-id/yishan-id-binding'),
            ):
                redirect = session.get(BASE + old, timeout=20, allow_redirects=False)
                dest = urlsplit(redirect.headers.get('Location', ''))
                if redirect.status_code != 302 or dest.path != new or (dest.netloc and dest.netloc != urlsplit(BASE).netloc):
                    raise RuntimeError(f'{old}: wrong canonical route')
                call('GET', new)
            call('GET', '/assets/file_share/icon.svg')
            for board in ('bizbase_mgmt', 'sales_board', 'ops_board', 'customer_board'):
                workspace = call('GET', f'/api/resource/Workspace/{board}').json()['data']
                assert workspace['name'] == workspace['module'] == board
        finally:
            # The Desk boot payload sets the CSRF token for authenticated POSTs.
            m = re.search(r'frappe\.csrf_token\s*=\s*["\']([^"\']+)', desk.text) if 'desk' in locals() else None
            headers = {'X-Frappe-CSRF-Token': m[1]} if m else {}
            call('POST', '/api/method/logout', headers=headers)
        print('HTTPS login page, CSS, Administrator session, Desk, canonical routes, four workspaces and logout: OK')


if __name__ == '__main__':
    try:
        check()
    except Exception as exc:
        print('Acceptance check failed:', str(exc) if type(exc) is RuntimeError else type(exc).__name__)
        sys.exit(1)
