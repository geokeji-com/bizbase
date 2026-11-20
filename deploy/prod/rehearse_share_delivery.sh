#!/usr/bin/env bash
# Run on the BizBase host, with a verified schema backup and a pinned local image.
# No service ports, outgoing network, production DB credentials or live site mounts.
set -euo pipefail
umask 077
image=${1:?exact image ID}; dump=${2:?verified schema dump}; base=${3:?private staging directory}
[[ $image =~ ^sha256:[0-9a-f]{64}$ && -s $dump && -d $base ]]
work=$(mktemp -d "$base/rehearsal.XXXXXXXX"); id="bb-share-$(basename "$work" | cut -d. -f2 | tr '[:upper:]' '[:lower:]')"
site=bizbase.geokeji.com; bench=/home/frappe/frappe-bench; src=/var/lib/bizbase-prod/sites
mkdir -p "$work/sites/$site/private" "$work/sites/$site/public" "$work/sites/$site/logs" "$work/sites/$site/locks" "$work/logs"
cp "$src/apps.txt" "$work/sites/"; ln -s "$bench/assets" "$work/sites/assets"
for kind in public private; do if [[ -d $src/$site/$kind/files ]]; then cp -a "$src/$site/$kind/files" "$work/sites/$site/$kind/"; fi; done
python3 -I - "$work/sites" "$site" "$src" <<'PY'
import json,sys,secrets
from pathlib import Path
out,site,src=Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3]); cfg={}
for p in (src/'common_site_config.json',src/site/'site_config.json'): cfg.update(json.loads(p.read_text()))
assert cfg['db_schema']=='bizbase_app' and cfg['db_name']=='bizbase'
a=dict(db_type='postgres',db_name='bizbase',db_schema='bizbase_app',db_user='bizbase_app',db_password=secrets.token_hex(),db_host='qa-db',db_port=5432,encryption_key=cfg['encryption_key'],maintenance_mode=1,disable_scheduler=1,mute_emails=1,file_share_primary_origin='https://'+site,host_name='https://'+site)
(out/site/'site_config.json').write_text(json.dumps(a)); (out/'common_site_config.json').write_text(json.dumps(dict(default_site=site,redis_cache='redis://qa-redis:6379/0',redis_queue='redis://qa-redis:6379/1',redis_socketio='redis://qa-redis:6379/1')))
PY
chown -R -h 1000:0 "$work/sites" "$work/logs"
docker network create --internal "$id" >/dev/null
cleanup(){ docker rm -fv "$id-db" "$id-redis" >/dev/null 2>&1 || :; docker network rm "$id" >/dev/null || :; }; trap cleanup EXIT
common=(--pull=never --network "$id" --log-driver none)
docker run -d "${common[@]}" --name "$id-db" --network-alias qa-db -e POSTGRES_USER=bizbase_app -e POSTGRES_DB=bizbase -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine >/dev/null
docker run -d "${common[@]}" --name "$id-redis" --network-alias qa-redis redis:8.6.5-alpine >/dev/null
for _ in {1..45}; do docker exec "$id-db" pg_isready -q -h 127.0.0.1 -U bizbase_app && break; sleep 1; done
docker exec -i "$id-db" pg_restore -U bizbase_app -d bizbase --exit-on-error --no-owner --no-privileges <"$dump"
docker exec "$id-db" psql -X -U bizbase_app -d bizbase -c 'ALTER ROLE bizbase_app SET search_path=bizbase_app,public' >/dev/null
sql(){ docker exec "$id-db" psql -XAtq -v ON_ERROR_STOP=1 -U bizbase_app -d bizbase -c "$1"; }
counts='SELECT (SELECT count(*) FROM "tabFile Share"), (SELECT count(*) FROM "tabFile Share Version"), (SELECT count(*) FROM "tabFile Share Access Log");'
before=$(sql "$counts"); [[ $before =~ ^[0-9]+\|[0-9]+\|[0-9]+$ ]]
docker run --rm "${common[@]}" -v "$work/sites:$bench/sites" -v "$work/logs:$bench/logs" --entrypoint bench "$image" --site "$site" migrate >"$work/migrate.log" 2>&1 || { grep -E 'Error|Exception|Traceback' "$work/migrate.log" | tail -8 >&2; exit 1; }
after=$(sql "$counts"); [[ $after == "$before" ]]
bad=$(sql "SELECT count(*) FROM \"tabFile Share\" s WHERE share_url IS DISTINCT FROM '/file-share/s/'||s.name OR (SELECT count(*) FROM \"tabFile Share Entry\" e WHERE e.parent=s.name AND e.domain='bizbase.geokeji.com' AND e.enabled=1) <> 1;"); [[ $bad == 0 ]]
printf 'Rehearsal passed: reports|versions|logs = %s; wrong URL/entry = %s. Logs: %s\n' "$after" "$bad" "$work"
