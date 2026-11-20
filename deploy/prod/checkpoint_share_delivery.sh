#!/usr/bin/env bash
# Compose is already frozen. Only the site-specific read-only verifier may query production.
set -euo pipefail
umask 077
stage=${1:?private stage}; tools=${2:?previous verified window tools}; recipient=${3:?recovery certificate}
base=/opt/bizbase-prod; state=$base/slots/maintenance; sites=/var/lib/bizbase-prod/sites
[[ $(cat "$state/phase") == frozen && $(cat "$state/old") == blue && -s $stage/host-before.tar ]]
for service in bizbase-yishan-id.timer bizbase-yishan-id.service; do [[ $(systemctl show -p ActiveState --value "$service") == inactive ]]; done
for project in bizbase-prod bizbase-prod-blue bizbase-prod-green; do [[ -z $(docker ps -q --filter "label=com.docker.compose.project=$project") ]]; done
cd "$stage"; mkdir -p frozen; cd frozen; [[ ! -e id && ! -e recovery.cms ]]
probe(){ docker run --rm -i --pull=never --log-driver=none --tmpfs /home/frappe/frappe-bench/sites/bizbase.geokeji.com/logs:uid=1000,gid=0 --network bizbase-prod-blue_default -v "$sites:/home/frappe/frappe-bench/sites:ro" --entrypoint env/bin/python "$(cat "$state/old.image")" - "$@"; }
probe queue < "$tools/routes_checks.py"
probe before < ../check.py > before.txt
if [[ ! -s backup.log ]]; then python3 -I "$tools/pg16_schema.py" backup > backup.log </dev/null; fi
id=$(grep -oE '[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}' backup.log); [[ $id =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$ ]]; printf '%s\n' "$id" >id
python3 -I "$tools/pg16_schema.py" verify "$id"
tar -cpf sites.tar -C "${sites%/*}" sites; tar --compare -f sites.tar -C "${sites%/*}"
cp -p "/var/backups/bizbase-pg16/$id/"{bizbase_app.dump,manifest.json} .; cp -p ../host-before.tar host.tar
sha256sum id bizbase_app.dump manifest.json sites.tar host.tar before.txt >SHA256SUMS
tar -cf - id bizbase_app.dump manifest.json sites.tar host.tar before.txt SHA256SUMS | openssl cms -encrypt -binary -stream -aes-256-cbc -outform DER -out recovery.cms "$recipient"
sha256sum recovery.cms; printf 'Verified frozen checkpoint: %s\n' "$id"
