#!/bin/bash
# A persistent, loopback-only onboarding preview. All records and credentials are synthetic.
set -euo pipefail
cd "$(dirname "$0")/../../.."
export BIZBASE_DEV_SECRETS="$HOME/.local/share/bizbase-share-preview"
export BIZBASE_DEV_PORT=18081
export BIZBASE_DEV_IMAGE=bizbase/local:geo-apps
umask 077
mkdir -p "$BIZBASE_DEV_SECRETS"
chmod 700 "$BIZBASE_DEV_SECRETS"
for key in db_root admin_password employee_password; do
    if [[ ! -s "$BIZBASE_DEV_SECRETS/$key" ]]; then openssl rand -hex 32 > "$BIZBASE_DEV_SECRETS/$key"; fi
    chmod 640 "$BIZBASE_DEV_SECRETS/$key"
done
compose=(docker compose -p bizbase-share-preview -f deploy/local-pg/compose.yaml)
"${compose[@]}" run --rm -T setup bash -s <<'INIT'
set -eu
bench set-config -g db_host db
bench set-config -gp db_port 5432
bench set-config -g redis_cache redis://redis-cache:6379
bench set-config -g redis_queue redis://redis-queue:6379
bench set-config -g redis_socketio redis://redis-queue:6379
if [ ! -f sites/frontend/site_config.json ]; then
    bench new-site frontend --db-type postgres --db-host db --db-port 5432 --db-root-username postgres --db-root-password "$(cat /run/secrets/db_root)" --admin-password "$(cat /run/secrets/admin_password)" --set-default
fi
for app in erpnext yishan_id file_share; do bench --site frontend install-app "$app"; done
bench --site frontend set-config host_name http://127.0.0.1:18081
bench --site frontend migrate
INIT
"${compose[@]}" run --rm -T -v "$BIZBASE_DEV_SECRETS/employee_password:/run/secrets/preview_employee:ro" -v "$PWD/deploy/local-pg/share-preview/seed.py:/tmp/preview_seed.py:ro" setup env/bin/python /tmp/preview_seed.py
"${compose[@]}" up -d backend websocket frontend
