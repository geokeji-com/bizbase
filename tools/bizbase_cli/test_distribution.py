"""Exercise release bytes, installation and collision handling in an empty employee home."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / 'apps/file_share/file_share/public/agent'


class StandaloneRelease(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix='employee with spaces ')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        XDG_CONFIG_HOME=str(self.home / 'config'), CLAUDE_CONFIG_DIR=str(self.home / '.claude'))
        self.env.pop('BIZBASE_SITE', None)
        self.setup = [sys.executable, '-I', str(PUBLIC / 'bizbase.pyz'), 'install', '--site']

    def execute(self, args, **kwargs):
        return subprocess.run(args, cwd=self.home, env=self.env, capture_output=True, text=True, **kwargs)

    def test_manifest_matches_reproducible_source(self):
        manifest = json.loads((PUBLIC / 'manifest.json').read_text())
        archive = (PUBLIC / manifest['filename']).read_bytes()
        self.assertEqual(hashlib.sha256(archive).hexdigest(), manifest['sha256'])
        self.assertEqual(len(archive), manifest['size'])
        self.execute([sys.executable, '-I', str(ROOT / 'scripts/build_share_agent.py'), '--check'], check=True)

    def test_clean_user_install_switch_site_and_repeat_without_path(self):
        record = json.loads(self.execute([*self.setup, 'https://a.example'], check=True).stdout)
        for path in record['skills']:
            self.assertIn(json.dumps(record['command'], ensure_ascii=False), Path(path).read_text(encoding='utf-8'))
        self.assertEqual(record, json.loads(self.execute([*self.setup, 'https://a.example'], check=True).stdout))
        for args in ([*record['command'], '--json', 'whoami'], [record['launcher'], '--json', 'whoami']):
            if os.name == 'nt' and args[0] == record['launcher']:
                args = [os.environ['COMSPEC'], '/c', *args]
            self.assertEqual(json.loads(self.execute(args).stdout)['error']['code'], 'not_logged_in')
        self.assertEqual(json.loads(self.execute([*self.setup, 'https://b.example'], check=True).stdout)['site'], 'https://b.example')
        self.assertEqual(json.loads(self.execute([*record['command'], '--site', 'untrusted', '--json', 'whoami']).stdout)['error']['code'], 'invalid_site')
        self.env['BIZBASE_SITE'] = 'untrusted'
        self.assertEqual(json.loads(self.execute([*record['command'], '--json', 'whoami']).stdout)['error']['code'], 'invalid_site')

    def test_declines_conflicting_skill_before_writing_any_files(self):
        dest = self.home / '.agents/skills/bizbase-share/SKILL.md'
        dest.parent.mkdir(parents=True)
        dest.write_text('existing instructions')
        self.assertNotEqual(self.execute([*self.setup, 'https://site.example']).returncode, 0)
        self.assertFalse((self.home / '.local/share/bizbase-agent/bizbase.pyz').exists())
        self.assertEqual(dest.read_text(), 'existing instructions')

    def test_cleartext_non_loopback_refused_before_install(self):
        self.assertNotEqual(self.execute([*self.setup, 'http://site.example']).returncode, 0)
        self.assertFalse((self.home / '.local').exists())
