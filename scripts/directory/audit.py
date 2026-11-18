#!/usr/bin/env python3
"""审计新增构建依赖及继承运行时；原始报告保存在本机私有目录。"""
from pathlib import Path
import json
import subprocess
import sys

import bootstrap as infra


def main():
    infra.load_env()
    python = infra.PRIVATE / "audit-venv/bin/python"
    if not python.exists():
        raise SystemExit("Create the private audit venv with pip-audit==2.10.1 first")
    directory = infra.PRIVATE / "audit"
    directory.mkdir(mode=0o700, exist_ok=True)
    script = "import importlib.metadata as m,json; print(json.dumps([{'name':d.metadata['Name'],'version':d.version,'direct':d.read_text('direct_url.json')} for d in m.distributions()]))"
    packages = json.loads(infra.compose("exec", "-T", "backend", "env/bin/python", "-c", script, capture=True))
    requirements, excluded = [], []
    for package in packages:
        name = package["name"].lower().replace("_", "-")
        if package["direct"] and name != "flit-core":
            excluded.append({"name": name, "version": package["version"], "reason": "local app or pinned source fork; PyPI advisory matching does not verify this source"})
        else:
            requirements.append(f'{package["name"]}=={package["version"]}')
    infra.private_write(directory / "runtime.txt", "\n".join(sorted(requirements)) + "\n")
    infra.private_write(directory / "excluded.json", json.dumps(excluded, indent=2) + "\n")
    infra.private_write(directory / "new.txt", "flit_core==3.12.0\n")
    statuses = {}
    for scope in ("new", "runtime"):
        report = directory / f"{scope}.json"
        result = subprocess.run([str(python), "-m", "pip_audit", "--timeout", "60", "--no-deps", "--disable-pip", "-r", str(directory / f"{scope}.txt"), "--format", "json", "--output", str(report)], capture_output=True, text=True)
        if report.exists():
            report.chmod(0o600)
            parsed = json.loads(report.read_text())
            statuses[scope] = {"exit_code": result.returncode, "vulnerabilities": sum(len(p.get("vulns", [])) for p in parsed.get("dependencies", []))}
        else:
            statuses[scope] = {"exit_code": result.returncode, "error": result.stderr[-2000:]}
    infra.private_write(directory / "summary.json", json.dumps(statuses, indent=2) + "\n")
    print(json.dumps(statuses, indent=2))
    return int(any(value["exit_code"] for value in statuses.values()))


if __name__ == "__main__":
    sys.exit(main())
