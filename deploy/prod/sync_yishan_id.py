"""Publish only the BizBase OIDC configuration; never expose the source INI to containers."""

import configparser
import json
import os
import secrets
import stat
import tempfile
import time
from pathlib import Path

import requests

SOURCE = Path('/etc/bizbase/connections.ini')
TARGET = Path('/etc/bizbase/yishan-runtime/settings.json')
ISSUER = 'https://id.geokeji.com/oidc'
CALLBACK = 'https://bizbase.geokeji.com/api/method/yishan_id_login.auth.callback'


def snapshot(source, http):
    cfg = configparser.ConfigParser(interpolation=None, default_section='__no_defaults__')
    try:
        with open(source, encoding='utf-8', opener=os_no_follow) as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
                return {}
            cfg.read_file(f)
        client = cfg['yishan_id']['client_id'].strip()
        secret = cfg['yishan_id']['client_secret'].strip()
    except (OSError, UnicodeError, KeyError, configparser.Error):
        return {}
    if not client or not secret:
        return {}
    result = dict(issuer=ISSUER, redirect_uri=CALLBACK, client_id=client, client_secret=secret, verified_until=0)
    try:
        discovery = http.get(ISSUER + '/.well-known/openid-configuration', timeout=4, allow_redirects=False)
        metadata = discovery.json() if discovery.status_code == 200 else {}
        # Never send the secret to a different origin or a redirected endpoint.
        endpoint = ISSUER + '/token/introspection'
        if not isinstance(metadata, dict) or metadata.get('issuer') != ISSUER or metadata.get('introspection_endpoint') != endpoint:
            return result
        response = http.post(endpoint, auth=(client, secret), data={'token': secrets.token_urlsafe(32)},
                             timeout=4, allow_redirects=False)
        # RFC 7662: authenticated request for an unknown token. No user token needed.
        if response.status_code == 200 and response.json().get('active') is False:
            result['verified_until'] = int(time.time()) + 150
    except (requests.RequestException, ValueError, AttributeError, UnicodeError):
        pass
    return result


def os_no_follow(path, flags):
    return os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)


def publish(data):
    TARGET.parent.mkdir(mode=0o711, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=TARGET.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            json.dump(data, f)
            f.flush()
            os.fchown(f.fileno(), 1000, 0)
            os.replace(temp, TARGET)
        finally:
            temp.unlink(missing_ok=True)


if __name__ == '__main__':
    with requests.Session() as http:
        http.trust_env = False
        publish(snapshot(SOURCE, http))
