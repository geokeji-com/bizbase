"""Local state-machine tests: simulated Docker, Nginx and HTTP; no host deployment."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("deploy.sh")
MOCK = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['MOCK_ROOT']); prog = pathlib.Path(sys.argv[0]).name; a = sys.argv[1:]
state = root/'docker.json'; services = json.loads(state.read_text()); jobs = ['worker', 'scheduler']; web = ['frontend', 'backend', 'websocket']
def fail(cond):
    if cond: sys.exit(1)
with (root/'trace').open('a') as trace:
    trace.write(json.dumps([prog, *a]) + '\n')
if prog == 'curl':
    if any('public.invalid' in x for x in a): fail((root/'bad-edge').exists())
    if any(x.endswith('/login') for x in a): print('<link href="/assets/desk.css">')
elif prog in ('nginx', 'sleep'): pass
elif a[0] == 'ps':
    selectors = [v.split('=', 2)[2] for v in a if v.startswith('label=com.docker.compose.project=')]
    project = selectors[0] if selectors else None
    sv = [v.split('=', 2)[2] for v in a if v.startswith('label=com.docker.compose.service=')]
    for (p, rows) in services.items():
        if project and p != project: continue
        for name, running in rows.items():
            if (running or '-aq' in a) and (not sv or name == sv[0]): print(p+'-'+name+'-1')
elif a[:2] == ['image','inspect']: print('linux/amd64' if 'Architecture' in a[3] else 'new-id')
elif a[0] == 'inspect': print('old-id')
elif a[0] == 'run' and a[-1] == 'sites/apps.txt': print('frappe\nfile_share' if 'new-id' in a or 'candidate' in a else 'frappe\nstatic_share')
elif a[:2] == ['network','inspect']: print('127.0.0.1')
elif a[0] == 'compose':
    i = a.index('-p'); p = a[i+1]; args = a[i+2:]; svc = services.setdefault(p,{})
    if args[0] == 'stop':
        for s in jobs+web:
            if s in args and s in svc: svc[s]=False
    elif args[0] == 'create': svc['backend']=False
    elif args[0] == 'up':
        for s in jobs+web:
            if s in args: svc[s]=True
    elif args[0] == 'run':
        if 'migrate' in args: fail((root/'bad-migrate').exists())
    elif args[0] != 'exec': raise RuntimeError(args)
    state.write_text(json.dumps(services))
else: raise RuntimeError((prog,a))
'''


class MaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for cmd in ('docker', 'nginx', 'curl', 'sleep'):
            path = self.root/cmd
            path.write_text(MOCK); path.chmod(0o755)
        self.upstream = self.root/'upstream'
        self.upstream.write_text('server 127.0.0.1:3180;\n')
        (self.root/'apps.txt').write_text('frappe\nstatic_share\n')
        self.sv = self.root/'docker.json'
        self.sv.write_text(json.dumps({'bizbase-prod': {s: True for s in ('backend', 'frontend', 'websocket', 'scheduler', 'worker')}, 'unrelated': {'backend': True}}))
        self.env = dict(os.environ, PATH=str(self.root)+':'+os.environ['PATH'], MOCK_ROOT=str(self.root),
                        BIZBASE_DIR=str(self.root), BIZBASE_SITES_DIR=str(self.root), BIZBASE_UPSTREAM_FILE=str(self.upstream),
                        BIZBASE_EDGE_URL='https://public.invalid/ping', BIZBASE_EDGE_RESOLVE='')

    def call(self, *args, ok=True):
        p = subprocess.run(['bash', str(SCRIPT), *args], capture_output=True, text=True, env=self.env)
        self.assertEqual(p.returncode == 0, ok, (args, p.stderr, p.stdout))
        self.assertTrue(json.loads(self.sv.read_text())['unrelated']['backend'])
        return p

    def d(self, *args, **kw):
        return self.call('maintenance', *args, **kw)

    def test_full_window_and_no_implicit_old_rollback(self):
        self.d('begin', 'candidate')
        self.d('publish', ok=False)
        self.call('release', 'candidate', ok=False)
        self.call('rollback', '--force', ok=False)
        self.call('compose', 'up', ok=False)
        self.d('freeze'); self.d('old', 'bench', ok=False)
        self.assertFalse(any(json.loads(self.sv.read_text())['bizbase-prod'].values()))
        self.d('checkpoint', 'backup-ticket-123')
        self.d('new', 'bench', ok=False); self.d('old', 'env/bin/python', '-')
        self.d('manifest'); self.d('old', 'bench', ok=False)
        self.assertEqual((self.root/'apps.txt').read_text().splitlines(), ['frappe','file_share'])
        self.d('new', 'bench')
        (self.root/'bad-migrate').touch(); self.d('migrate', ok=False); self.d('preview', ok=False)
        (self.root/'bad-migrate').unlink(); self.d('migrate'); self.d('preview')
        self.assertIn('3180', self.upstream.read_text())
        self.assertNotIn('worker', json.loads(self.sv.read_text())['bizbase-prod-blue'])
        (self.root/'bad-edge').touch(); self.d('publish', ok=False)
        self.assertIn('3181', self.upstream.read_text())
        self.assertFalse(json.loads(self.sv.read_text())['bizbase-prod-blue']['frontend'])
        self.call('rollback','--force',ok=False)
        (self.root/'bad-edge').unlink(); self.d('publish')
        self.assertEqual((self.root/'slots/active').read_text().strip(), 'blue')
        self.assertTrue(json.loads(self.sv.read_text())['bizbase-prod-blue']['worker'])
        self.assertFalse((self.root/'slots/previous').exists()); self.call('rollback','--force',ok=False)
        self.d('accept'); self.call('rollback','--force',ok=False)
        self.assertTrue(list((self.root/'slots').glob('completed-D.*/record/checkpoint')))

    def test_emergency_isolate_keeps_old_stopped(self):
        self.d('begin','candidate'); self.d('freeze'); self.d('checkpoint','snapshot-1')
        self.d('manifest'); self.d('migrate'); self.d('preview'); self.d('publish'); self.d('isolate')
        for p in ('bizbase-prod','bizbase-prod-blue'):
            self.assertFalse(any(json.loads(self.sv.read_text())[p].values()))
        self.d('publish', ok=False); self.d('accept', ok=False); self.call('rollback','--force',ok=False)

    def test_ab_refuses_preedited_manifest(self):
        (self.root/'apps.txt').write_text('frappe\nfile_share\n')
        self.assertIn('D-class', self.call('release', 'candidate',ok=False).stderr)
        self.assertIn('3180',self.upstream.read_text())

    def test_refuses_unretired_slot(self):
        (self.root/'slots').mkdir(); (self.root/'slots/previous').write_text('green\n')
        self.d('begin','candidate',ok=False)
        self.assertFalse((self.root/'slots/maintenance').exists())


if __name__ == '__main__':
    unittest.main()
