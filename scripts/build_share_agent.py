"""Rebuild the static CLI+skill release served by File Share; --check detects stale assets."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'apps/file_share/file_share/public/agent'


def release():
    entries = {'__main__.py': b'from bizbase_cli.distribution import run\nraise SystemExit(run())\n',
               'bizbase-share/SKILL.md': (ROOT / 'skills/bizbase-share/SKILL.md').read_bytes()}
    for module in ('__init__', 'auth', 'main', 'distribution'):
        name = 'bizbase_cli/' + module + '.py'
        entries[name] = (ROOT / 'tools' / name).read_bytes()
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        for name, content in sorted(entries.items()):
            # Fixed metadata and a stored archive give identical bytes across hosts / zlib releases.
            member = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            member.compress_type = ZIP_STORED
            archive.writestr(member, content.replace(b'\r\n', b'\n'))
    bundle = buffer.getvalue()
    manifest = {'filename': 'bizbase.pyz', 'sha256': sha256(bundle).hexdigest(), 'size': len(bundle),
                'minimum_python': '3.9'}
    return {'bizbase.pyz': bundle, 'manifest.json': (json.dumps(manifest, indent=2) + '\n').encode()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    for name, content in release().items():
        dest = ASSETS / name
        if args.check:
            if not dest.is_file() or dest.read_bytes() != content:
                p.exit(1, f'Stale agent distribution: {dest}. Run python3 scripts/build_share_agent.py\n')
        else:
            ASSETS.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)


if __name__ == '__main__':
    main()
