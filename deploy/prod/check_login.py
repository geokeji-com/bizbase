"""ECS-only acceptance check via the production TLS endpoint. Never print response bodies."""

import re
import sys
from pathlib import Path

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
            desk = call('GET', '/desk/geo_operations')
            assert 'text/html' in desk.headers.get('Content-Type', '')
            workspace = call('GET', '/api/resource/Workspace/geo_operations').json()['data']
            assert workspace['name'] == workspace['module'] == 'geo_operations'
        finally:
            # The Desk boot payload sets the CSRF token for authenticated POSTs.
            m = re.search(r'frappe\.csrf_token\s*=\s*["\']([^"\']+)', desk.text) if 'desk' in locals() else None
            headers = {'X-Frappe-CSRF-Token': m[1]} if m else {}
            call('POST', '/api/method/logout', headers=headers)
        print('HTTPS login page, CSS, Administrator session, Desk, GEO workspace and logout: OK')


if __name__ == '__main__':
    try:
        check()
    except Exception as exc:
        print('Acceptance check failed:', str(exc) if type(exc) is RuntimeError else type(exc).__name__)
        sys.exit(1)
