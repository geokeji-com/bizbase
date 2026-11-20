"""Exercise the public renderer, real policy resolution and signatures for three hosts.

No site writes: replace the document store, request context and origin registry only.
"""
import html
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from werkzeug.wrappers import Request

from file_share import publication, serve


class DeliveryTest(unittest.TestCase):
	def setUp(self):
		row = frappe._dict
		self.company, self.partner, self.other = ('company.example', 'a.example', 'b.example')
		self.entries = [row(domain=host, enabled=1, access_mode=mode, version_mode=version,
			pinned_version=2, rule_epoch='r', version_epoch='v', user_list='', role_list='')
			for host, mode, version in [(self.company, 'Inherit', 'Follow'), (self.partner, 'Password', 'Pinned')]]
		self.entries[1].get_password = Mock(return_value='partner password')
		self.doc = SimpleNamespace(name='YDWWBxUtWN', title='十月报告', owner='author', status='Active',
			current_version=4, access_level='Public', access_salt='defaults', allowed_roles=[], allowed_users=[],
			entries=self.entries, versions=[row(version=v, entry='index.html') for v in (2, 4)])
		self.base = '/file-share/s/' + self.doc.name
		self.cfg = {h: row(status='Enabled', domain_epoch='d') for h in (self.company, self.partner, self.other)}
		framework = self.enterContext(patch.object(serve, 'frappe'))
		self.framework = framework
		framework.get_doc.side_effect = lambda *args: self.doc if len(args) == 2 else Mock()
		framework.db.exists.return_value = True
		self.grants = {}
		framework.cache.set_value.side_effect = lambda k, v, **_: self.grants.update({k:v})
		framework.cache.get_value.side_effect = self.grants.get
		framework.cache.get.return_value = 0
		registry = self.enterContext(patch.object(publication, 'frappe'))
		registry._dict = frappe._dict
		registry.db.get_value.side_effect = lambda _, host, *a, **kw: self.cfg.get(host)
		self.enterContext(patch.object(serve, 'is_employee', side_effect=lambda u, **kw: u == 'author'))
		self.enterContext(patch.object(serve, 'live_session_data', return_value={}))
		self.enterContext(patch.object(serve, 'signing_key', return_value=b'test-key'))
		root = Path(self.enterContext(tempfile.TemporaryDirectory()))
		self.enterContext(patch.object(serve, 'content_base', return_value=root))
		for v in (2, 4):
			folder = root / self.doc.name / str(v)
			folder.mkdir(parents=True)
			(folder / 'index.html').write_text(f'content V{v}')

	def request(self, host, path, user='Guest', cookie='', password=None):
		self.framework.session.user = user
		self.framework.request = Request.from_values(path=path, base_url=f'https://{host}',
			headers={'Cookie': cookie}, method='GET' if password is None else 'POST',
			data={} if password is None else {'password': password})
		return serve.ShareRenderer.render(None)

	def asset(self, host, path=None, **kw):
		r = self.request(host, path or self.base, **kw)
		self.assertEqual(r.status_code, 200)
		url = html.unescape(re.search(r'<iframe src="([^"]+)"', r.get_data(as_text=True))[1])
		return url, r.headers.get('Set-Cookie', '').partition(';')[0]

	def test_https_scripts_are_allowed_only_inside_the_sandboxed_report(self):
		wrapper = self.request(self.company, self.base)
		self.assertNotIn('https:', wrapper.headers['Content-Security-Policy'])
		url, cookie = self.asset(self.company)
		content = self.request(self.company, url, cookie=cookie)
		policy = dict(rule.strip().split(' ', 1) for rule in content.headers['Content-Security-Policy'].split(';'))
		assets = f'https://{self.company}{url.rsplit("/", 1)[0]}/'
		self.assertCountEqual(policy['script-src'].split(), ["'unsafe-inline'", assets, 'https:'])
		self.assertEqual(policy['sandbox'], 'allow-scripts')
		for directive in ('default-src', 'connect-src', 'form-action', 'frame-src'):
			self.assertEqual(policy[directive], "'none'")

	def test_company_v4_partner_pinned_v2_switch_and_revocation(self):
		url, cookie = self.asset(self.company)
		self.assertEqual(self.request(self.company, url, cookie=cookie).data, b'content V4')
		self.assertEqual(self.request(self.other, self.base).status_code, 404)
		self.assertEqual(self.request(self.other, url).status_code, 404)
		self.assertEqual(self.request(self.partner, url).status_code, 403)
		self.assertEqual(self.request(self.partner, self.base, password='wrong').status_code, 401)
		auth = self.request(self.partner, self.base, password='partner password')
		self.assertEqual(auth.status_code, 303)
		pwd = auth.headers['Set-Cookie'].partition(';')[0]
		old, cap = self.asset(self.partner, self.base + '?v=4', cookie=pwd)
		self.assertEqual(self.request(self.partner, old, cookie=cap).data, b'content V2')
		self.assertTrue(any(c.args[0].get('access_domain') == self.partner and c.args[0].get('version') == 2
			and c.args[0].get('title_snapshot') == '十月报告' for c in self.framework.get_doc.call_args_list if len(c.args) == 1))
		self.entries[1].pinned_version = 4
		new, cap4 = self.asset(self.partner, cookie=pwd)  # switching versions does not reset the password
		self.assertEqual(self.request(self.partner, old, cookie=cap).status_code, 403)
		self.assertEqual(self.request(self.partner, new, cookie=cap4).data, b'content V4')
		self.entries[1].enabled = 0
		for alias in ('/file-share/s/', '/s/', '/file-share/'):
			self.assertEqual(self.request(self.partner, alias + self.doc.name, cookie=pwd).status_code, 404)
		self.assertEqual(self.request(self.partner, new, cookie=cap4).status_code, 404)
		self.assertEqual(self.request(self.company, url).status_code, 200)

	def test_new_domain_cannot_reuse_primary_tokens_and_global_shutdown_wins(self):
		self.entries[1].access_mode = 'Inherit'
		self.entries[1].version_mode = 'Follow'
		url, _ = self.asset(self.company)
		self.assertEqual(self.request(self.partner, url).status_code, 403)
		own, _ = self.asset(self.partner)
		self.cfg[self.partner].status = 'Disabled'
		self.assertEqual(self.request(self.partner, own).status_code, 404)
		self.assertEqual(self.request(self.company, url).status_code, 200)
		self.doc.status = 'Disabled'
		self.assertEqual(self.request(self.company, url).status_code, 404)

	def test_draft_can_only_be_previewed_by_author(self):
		self.doc.current_version = 0
		self.assertEqual(self.request(self.company, self.base + '?v=2').status_code, 404)
		url, cookie = self.asset(self.company, self.base + '?v=2', user='author')
		self.assertEqual(self.request(self.company, url).status_code, 403)
		self.assertEqual(self.request(self.company, url, cookie=cookie).data, b'content V2')
