#!/bin/bash
# Build the local development image from the exact upstream tag, leaving the old site alone.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
rev=4cdc09e0ec15edfaefb2a9d180efd1b6b552394e
base=${CRM_IMAGE:-bizbase/erpnext-crm:16.55.0-16.0.4}
work=$(mktemp -d)
printf "构建工作目录：%s\n" "$work"
# Only use release sources that match the verified archives for these exact commits.
download() {
  docker run --rm --pull=never --entrypoint curl "$base" --retry 3 --retry-all-errors -fsSL "$1" > "$2"
  printf '%s  %s\n' "$3" "$2" | shasum -a 256 -c -
}
download "https://codeload.github.com/frappe/insights/tar.gz/$rev" "$work/insights.tgz" \
  7c93f8434ecea210ff19900f82a2d03e45f1c111b28b3cf1272c7ccf016810c5
mkdir "$work/insights"
tar -xzf "$work/insights.tgz" -C "$work/insights" --strip-components=1
ui_rev=85de151a6937f61fc4bf46ff71a3ae40eb0ac2f0
ui_url="https://codeload.github.com/frappe/frappe-ui/tar.gz/$ui_rev"
download "$ui_url" "$work/frappe-ui.tgz" 10eb31fdef00cdef2a46c9ece0a1371b394c131ebfb1d9f147743849e8004212
python3 -I - "$work/insights/frontend/yarn.lock" "$ui_url" "$work/frappe-ui.tgz" <<'PYLOCK'
import sys
from pathlib import Path
lock = Path(sys.argv[1])
text = lock.read_text()
if text.count(sys.argv[2]) != 1:
    raise ValueError("unexpected frappe-ui lock entry")
lock.write_text(text.replace(sys.argv[2], Path(sys.argv[3]).as_uri()))
PYLOCK
mkdir "$work/frappe"
docker run --rm --pull=never --entrypoint tar "$base" -C apps/frappe --exclude=node_modules -cf - ui | tar -xf - -C "$work/frappe"
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
# Yarn 1 and Node >=22.12; @framework/ui is linked from the same Frappe as the runtime image.
yarn --cwd "$work/insights/frontend" install --frozen-lockfile
ln -s "$work/insights/frontend/node_modules" "$work/frappe/node_modules"
yarn --cwd "$work/insights/frontend" build
yarn --cwd "$work/insights/frontend" build:islands
mkdir "$work/context"
cp -R "$work/insights/insights" "$work/insights/pyproject.toml" "$work/insights/README.md" "$work/context/"
docker build --build-arg "CRM_IMAGE=$base" --build-context "insights=$work/context" \
  -f "$root/deploy/local-pg/Containerfile" -t "${BIZBASE_DEV_IMAGE:-bizbase/local:postgres-16}" "$root"
