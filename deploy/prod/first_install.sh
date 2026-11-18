#!/usr/bin/env bash
# ECS only. Run after prepare_host.py, with the verified local image ref as $1.
set -euo pipefail
cd /opt/bizbase-prod
export BIZBASE_IMAGE=${1:?expected image reference}
test "$(docker image inspect -f '{{.Os}}/{{.Architecture}}' "$BIZBASE_IMAGE")" = linux/amd64
test ! -e .env
test -z "$(docker compose ps -aq)"
umask 077
docker compose create --no-build --pull never backend
network=bizbase-prod_default
export BIZBASE_PROXY_IP
BIZBASE_PROXY_IP=$(docker network inspect -f '{{(index .IPAM.Config 0).Gateway}}' "$network")
printf 'BIZBASE_IMAGE=%s\nBIZBASE_PROXY_IP=%s\n' "$BIZBASE_IMAGE" "$BIZBASE_PROXY_IP" > .env
docker compose run --rm --no-deps -T \
  -v /opt/bizbase-prod/init_site.py:/opt/bizbase/init_site.py:ro \
  -v /etc/bizbase/initial-admin-password:/run/secrets/bizbase_admin:ro \
  backend env/bin/python /opt/bizbase/init_site.py >first-install.log 2>&1 || {
    printf 'Initialization failed. No services started. Inspect the private first-install.log.\n' >&2
    exit 1
  }
docker compose up -d --pull never
