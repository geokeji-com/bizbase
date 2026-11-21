"""User-level installer and entry point for the downloadable BizBase zipapp."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
from zipfile import ZipFile

from .auth import ClientError, origin


def install_root():
    return Path.home() / '.local' / 'share' / 'bizbase-agent'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_atomic(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.bizbase-')
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n').encode()


def install(site, source):
    site = origin(site)
    root = install_root()
    archive = root / 'bizbase.pyz'
    settings = root / 'site.json'
    receipt = root / 'installed.json'
    command = [sys.executable, '-I', str(archive)]
    launcher = Path.home() / '.local' / 'bin' / ('bizbase.cmd' if os.name == 'nt' else 'bizbase')
    if os.name == 'nt':
        # Do not rely on shell file associations or an already-refreshed PATH.
        python, pyz = [str(p).replace('%', '%%') for p in (sys.executable, archive)]
        wrapper = f'@echo off\r\nsetlocal DisableDelayedExpansion\r\n"{python}" -I "{pyz}" %*\r\n'
    else:
        wrapper = '#!/bin/sh\nexec ' + shlex.join(command) + ' "$@"\n'

    with ZipFile(source) as z:
        skill = z.read('bizbase-share/SKILL.md').decode()
    start = skill.index('<!-- bizbase-command -->')
    end = skill.index('<!-- /bizbase-command -->', start) + len('<!-- /bizbase-command -->')
    local_command = ('下面命令中的 `bizbase` 代表本机已安装的程序。用以下 JSON 参数数组启动，在数组末尾追加子命令参数。'
                     '站点默认使用安装时指定的地址，可用全局 `--site` 显式切换。\n\n```json\n'
                     + json.dumps(command, ensure_ascii=False) + '\n```')
    skill = (skill[:start] + local_command + skill[end:]).encode()
    claude_root = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude').expanduser()
    if not claude_root.is_absolute():
        raise ValueError('CLAUDE_CONFIG_DIR 必须为绝对路径')
    skills = [directory / 'skills' / 'bizbase-share' / 'SKILL.md' for directory in
              (claude_root, Path.home() / '.agents')]
    targets = {archive: (source.read_bytes(), 0o600), settings: (json_bytes({'site': site}), 0o600),
               launcher: (wrapper.encode(), 0o700), **{path: (skill, 0o600) for path in skills}}
    if receipt.is_symlink():
        raise ValueError(f'请检查安装记录符号链接 {receipt}')
    previous = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else {}
    hashes = {str(path): digest(data) for path, (data, _) in targets.items()}
    # Validate all destinations before the first write. Repeat installs may repair a missing file,
    # but must not overwrite an unrelated executable or a locally edited skill.
    for path in targets:
        if path.is_symlink() or (path.exists() and (not path.is_file() or
                digest(path.read_bytes()) not in (previous.get(str(path)), hashes[str(path)]))):
            raise ValueError(f'已有同名或已修改的文件，请先保留并移开它：{path}')
    for path, (data, mode) in targets.items():
        write_atomic(path, data, mode)
    write_atomic(receipt, json_bytes(hashes))
    return {'site': site, 'command': command, 'launcher': str(launcher), 'skills': list(map(str, skills))}


def run():
    if sys.version_info < (3, 9):
        print('BizBase 需要 Python 3.9 或更高版本', file=sys.stderr)
        return 2
    if sys.argv[1:2] == ['install']:
        parser = argparse.ArgumentParser(prog='bizbase install')
        parser.add_argument('--site', required=True, help='下载本工具的 BizBase 站点源地址')
        args = parser.parse_args(sys.argv[2:])
        try:
            print(json.dumps(install(args.site, Path(sys.argv[0]).absolute()), ensure_ascii=False))
        except (OSError, ValueError, ClientError) as error:
            print(f'安装未完成：{error}', file=sys.stderr)
            return 1
        return 0
    if not os.environ.get('BIZBASE_SITE') and not any(a == '--site' or a.startswith('--site=') for a in sys.argv[1:]):
        config = install_root() / 'site.json'
        if config.is_file():
            try:
                os.environ['BIZBASE_SITE'] = origin(json.loads(config.read_text(encoding='utf-8'))['site'])
            except (OSError, ValueError, KeyError, ClientError) as error:
                print(f'请修复或重新安装 BizBase 站点配置：{error}', file=sys.stderr)
                return 1
    from .main import main
    return main()
