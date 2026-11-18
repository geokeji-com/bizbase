import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import sync_yishan_id as sync
from yishan_id_login import managed


class AvailabilityTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source = Path(tmp.name, 'connections.ini')
        self.runtime = Path(tmp.name, 'settings.json')
        self.http = Mock()
        self.http.get.return_value.status_code = 200
        self.http.get.return_value.json.return_value = {
            'issuer': sync.ISSUER, 'introspection_endpoint': sync.ISSUER + '/token/introspection'}
        self.http.post.return_value.status_code = 200
        self.http.post.return_value.json.return_value = {'active': False}

    def load(self, ini):
        self.source.write_text(ini)
        os.chmod(self.source, 0o600)
        self.runtime.write_text(json.dumps(sync.snapshot(self.source, self.http)))
        return managed.load(self.runtime, require_verified=True)

    valid = '[yishan_id]\nclient_id = client\nclient_secret = s%:ecret\n'

    def test_missing_empty_invalid(self):
        for ini in ('', '[redis]\npassword=x', '[yishan_id]\nclient_id=x',
                    '[yishan_id]\nclient_id=\nclient_secret=x', self.valid.replace('s%:ecret','   '), '[broken'):
            with self.subTest(ini=ini):
                self.assertIsNone(self.load(ini))
        self.http.get.assert_not_called()

    def test_success_and_expiry(self):
        self.assertEqual(self.load(self.valid).client_id, 'client')
        self.assertEqual(self.http.post.call_args.kwargs['auth'], ('client', 's%:ecret'))
        data = json.loads(self.runtime.read_text())
        data['verified_until'] = 1
        self.runtime.write_text(json.dumps(data))
        self.assertIsNone(managed.load(self.runtime, require_verified=True))

    def test_rejection_outage_and_rotation(self):
        self.assertIsNotNone(self.load(self.valid))
        for status in (401, 403, 503):
            self.http.post.return_value.status_code = status
            self.assertIsNone(self.load(self.valid.replace('s%:ecret', 'replacement')))
        self.http.get.side_effect = requests.Timeout()
        self.assertIsNone(self.load(self.valid))

    def test_untrusted_endpoint_or_malformed_result(self):
        self.http.get.return_value.json.return_value['introspection_endpoint'] = 'https://example.org/check'
        self.assertIsNone(self.load(self.valid))
        self.http.post.assert_not_called()
        self.http.get.return_value.json.return_value['introspection_endpoint'] = sync.ISSUER + '/token/introspection'
        for body in ({}, [], {'active':'false'}):
            self.http.post.return_value.json.return_value = body
            self.assertIsNone(self.load(self.valid))

    def test_guest_login_page_only_adds_verified_provider(self):
        from yishan_id_login import auth

        context = {'for_test': 'login.html', 'provider_logins': [{'name': 'existing'}]}
        with patch.dict(os.environ, {'BIZBASE_YISHAN_ID_CONFIG': str(self.runtime)}), \
             patch.object(auth, 'frappe') as frappe, patch.object(auth, '_', lambda text: text):
            frappe.session.user = 'Guest'
            frappe.local.request.args = {}
            self.assertIsNone(auth.login_page_context(context))
            self.load(self.valid)
            result = auth.login_page_context(context)
            self.assertEqual([p['name'] for p in result['provider_logins']], ['yishan_id', 'existing'])
            self.http.post.return_value.status_code = 401
            self.load(self.valid)
            self.assertIsNone(auth.login_page_context(context))
            self.assertEqual(context['provider_logins'], [{'name': 'existing'}])
