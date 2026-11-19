#!/usr/bin/env bash
# Blue-green release for BizBase on the ECS host. Run as root from anywhere.
#
#   deploy.sh status
#   deploy.sh release IMAGE [--migrate]   start the idle slot, smoke-test, switch traffic, hand over jobs
#   deploy.sh rollback [--force]          switch traffic and jobs back to the previous slot
#   deploy.sh retire                      remove the previous slot once rollback is no longer needed
#   deploy.sh compose ARGS...             docker compose on the active slot (maintenance releases)
#
# Slots share the site directory, database and Redis. Only one slot runs worker and
# scheduler at a time. The legacy single-stack project counts as the first slot.
# Releases that add apps or change the Frappe/ERPNext assets are refused: use the
# maintenance procedure in OPERATIONS.md for those.
set -euo pipefail

DIR=${BIZBASE_DIR:-/opt/bizbase-prod}
SITE=${BIZBASE_SITE:-bizbase.geokeji.com}
SITES_DIR=${BIZBASE_SITES_DIR:-/var/lib/bizbase-prod/sites}
UPSTREAM=${BIZBASE_UPSTREAM_FILE:-/www/server/panel/vhost/nginx/bizbase-upstream.inc}
# %PORT% and %PROJECT% expand per slot; the test sandbox addresses containers by name.
UPSTREAM_FMT=${BIZBASE_UPSTREAM_FMT:-127.0.0.1:%PORT%}
EDGE_URL=${BIZBASE_EDGE_URL:-https://bizbase.geokeji.com/api/method/ping}
EDGE_RESOLVE=${BIZBASE_EDGE_RESOLVE-bizbase.geokeji.com:443:127.0.0.1}
ARCH=${BIZBASE_ARCH:-linux/amd64}
LEGACY=${BIZBASE_LEGACY_PROJECT:-bizbase-prod}
read -r -a NGINX <<<"${BIZBASE_NGINX:-nginx}"
STATE=$DIR/slots
COMPOSE=(docker compose --project-directory "$DIR" -f "$DIR/compose.yaml")
if [ -n "${BIZBASE_COMPOSE_EXTRA:-}" ]; then COMPOSE+=(-f "$BIZBASE_COMPOSE_EXTRA"); fi

log() { printf '==> %s\n' "$*"; }
die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

project() { if [ "$1" = legacy ]; then echo "$LEGACY"; else echo "$LEGACY-$1"; fi; }
port() { case $1 in legacy) echo 3180 ;; blue) echo 3181 ;; green) echo 3182 ;; *) die "unknown slot $1" ;; esac }
slot_compose() {
	if [ "$1" = legacy ]; then echo "$DIR/.env"; else echo "$STATE/$1.env"; fi
}
dc() {
	local s=$1
	shift
	"${COMPOSE[@]}" --env-file "$(slot_compose "$s")" -p "$(project "$s")" "$@"
}
containers() { docker ps -aq --filter "label=com.docker.compose.project=$(project "$1")" --filter "label=com.docker.compose.service=$2"; }
running() { [ -n "$(docker ps -q --filter "label=com.docker.compose.project=$(project "$1")" --filter "label=com.docker.compose.service=$2")" ]; }

active() {
	if [ -f "$STATE/active" ]; then
		cat "$STATE/active"
	elif running legacy backend; then
		echo legacy
	else die "no active slot: neither $STATE/active nor a running $LEGACY project"; fi
}
previous() { if [ -f "$STATE/previous" ]; then cat "$STATE/previous"; fi; }

target() {
	local t=${UPSTREAM_FMT//%PORT%/$(port "$1")}
	echo "${t//%PROJECT%/$(project "$1")}"
}
upstream_line() { printf 'server %s;\n' "$(target "$1")"; }
upstream_now() { grep -E '^[[:space:]]*server[[:space:]]' "$UPSTREAM" | head -1; }

lock() {
	mkdir -p "$STATE"
	mkdir "$STATE/.lock" 2>/dev/null || die "another deploy is running (remove $STATE/.lock if it crashed)"
	trap 'rmdir "$STATE/.lock"' EXIT
}

check_upstream() {
	[ -f "$UPSTREAM" ] || die "$UPSTREAM missing: complete the one-time Nginx step in OPERATIONS.md"
	[ "$(upstream_now)" = "$(upstream_line "$1" | tr -d '\n')" ] || die "Nginx has '$(upstream_now)', expected active slot $1: $(upstream_line "$1")"
	"${NGINX[@]}" -t >/dev/null 2>&1 || die "Nginx configuration test fails before any change"
}

switch_upstream() {
	cp -p "$UPSTREAM" "$UPSTREAM.prev"
	upstream_line "$1" >"$UPSTREAM.tmp"
	mv "$UPSTREAM.tmp" "$UPSTREAM"
	local out
	if ! out=$("${NGINX[@]}" -t 2>&1); then
		mv "$UPSTREAM.prev" "$UPSTREAM"
		printf '%s\n' "$out" >&2
		die "Nginx rejected the new upstream; left unchanged"
	fi
	"${NGINX[@]}" -s reload
	log "Nginx now sends new requests to $1 ($(target "$1"))"
}

edge_ok() {
	local args=(-fsS -o /dev/null --max-time 10)
	if [ -n "$EDGE_RESOLVE" ]; then args+=(--resolve "$EDGE_RESOLVE"); fi
	local _
	for _ in 1 2 3 4 5; do
		if curl "${args[@]}" "$EDGE_URL"; then return 0; fi
		sleep 2
	done
	return 1
}

smoke() {
	local base html asset
	base=http://127.0.0.1:$(port "$1")
	curl -fsS -o /dev/null --max-time 10 "$base/api/method/ping" || return 1
	html=$(curl -fsS --max-time 20 "$base/login") || return 1
	asset=$(printf '%s' "$html" | grep -oE '/assets/[^"?]+\.(css|js)' | head -1)
	[ -n "$asset" ] || {
		echo "no asset link on /login" >&2
		return 1
	}
	curl -fsS -o /dev/null --max-time 10 "$base$asset" || return 1
	log "smoke test passed on $1: ping, /login, $asset"
}

# Worker and scheduler move between slots by stopping and starting existing containers.
stop_jobs() {
	local c
	for c in $(containers "$1" scheduler) $(containers "$1" worker); do docker stop -t 120 "$c" >/dev/null; done
}
start_jobs() {
	local c
	for c in $(containers "$1" worker) $(containers "$1" scheduler); do docker start "$c" >/dev/null; done
}

image_file_sum() { docker run --rm --network none --entrypoint sha256sum "$1" "$2" | cut -d' ' -f1; }

cmd_status() {
	local a p
	a=$(active)
	p=$(previous)
	echo "active:   $a (port $(port "$a"), $(project "$a"), $(slot_compose "$a"))"
	echo "previous: ${p:-none}"
	if [ -f "$UPSTREAM" ]; then echo "nginx:    $(upstream_now)"; fi
	if [ -f "$STATE/migrated" ]; then echo "note:     the active slot ran migrate; rollback needs --force"; fi
	docker ps --filter "label=com.docker.compose.project" --format '{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.service"}}\t{{.Image}}\t{{.Status}}' | grep "^$LEGACY" | sort
}

cmd_release() {
	local image=${1:?usage: deploy.sh release IMAGE [--migrate]} migrate=${2:-}
	[ -z "$migrate" ] || [ "$migrate" = --migrate ] || die "unknown option $migrate"
	lock
	local cur new old_image extra
	cur=$(active)
	case $cur in legacy | green) new=blue ;; blue) new=green ;; esac
	check_upstream "$cur"

	[ "$(docker image inspect -f '{{.Os}}/{{.Architecture}}' "$image")" = "$ARCH" ] || die "$image is not $ARCH"
	old_image=$(docker inspect -f '{{.Image}}' "$(containers "$cur" backend | head -1)")
	extra=$(comm -13 <(sort "$SITES_DIR/apps.txt") <(docker run --rm --network none --entrypoint cat "$image" sites/apps.txt | sort) | tr '\n' ' ')
	[ -z "$extra" ] || die "image adds apps (${extra% }); installing apps needs the maintenance procedure"
	[ "$(image_file_sum "$old_image" assets/assets.json)" = "$(image_file_sum "$image" assets/assets.json)" ] ||
		die "framework assets differ from the running image; use the maintenance procedure"

	# A new release replaces the rollback point: retire the old one and anything left in the target slot.
	local prev
	prev=$(previous)
	if [ -n "$prev" ] && [ "$prev" != "$new" ] && [ "$prev" != "$cur" ]; then
		log "retiring the previous slot $prev"
		dc "$prev" down
	fi
	if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$(project "$new")")" ]; then
		log "removing the old $new slot"
		dc "$new" down
	fi
	rm -f "$STATE/previous"

	printf 'BIZBASE_IMAGE=%s\nBIZBASE_PORT=%s\n' "$image" "$(port "$new")" >"$STATE/$new.env"
	dc "$new" create --no-build --pull never --no-recreate backend >/dev/null
	local gw
	gw=$(docker network inspect -f '{{(index .IPAM.Config 0).Gateway}}' "$(project "$new")_default")
	printf 'BIZBASE_PROXY_IP=%s\n' "$gw" >>"$STATE/$new.env"

	rm -f "$STATE/migrated.next"
	if [ "$migrate" = --migrate ]; then
		log "migrating $SITE with $image while $cur keeps serving"
		dc "$new" run --rm --no-deps -T backend bench --site "$SITE" migrate ||
			die "migrate failed; traffic still on $cur. Check whether the schema changed before retrying"
		touch "$STATE/migrated.next"
	fi

	log "starting $new web processes on port $(port "$new")"
	dc "$new" up -d --no-build --pull never --wait --wait-timeout 300 backend websocket frontend ||
		die "$new did not become healthy; traffic still on $cur"
	smoke "$new" || die "smoke test failed on $new; traffic still on $cur"

	switch_upstream "$new"
	if ! edge_ok; then
		switch_upstream "$cur"
		die "public entry failed after switching; traffic returned to $cur"
	fi

	log "handing worker and scheduler from $cur to $new"
	stop_jobs "$cur"
	dc "$new" up -d --no-build --pull never worker scheduler

	echo "$new" >"$STATE/active"
	echo "$cur" >"$STATE/previous"
	if [ -f "$STATE/migrated.next" ]; then mv "$STATE/migrated.next" "$STATE/migrated"; else rm -f "$STATE/migrated"; fi
	log "released $image on $new. $cur web processes stay up for rollback; run 'deploy.sh retire' when done"
}

cmd_rollback() {
	lock
	local cur prev
	cur=$(active)
	prev=$(previous)
	[ -n "$prev" ] || die "no previous slot recorded"
	if ! running "$prev" backend || ! running "$prev" frontend; then die "previous slot $prev is not running"; fi
	if [ -f "$STATE/migrated" ] && [ "${1:-}" != --force ]; then
		die "$cur ran migrate; old code may not match the schema. Re-run with --force only if the change was additive"
	fi
	check_upstream "$cur"
	smoke "$prev" || die "previous slot $prev fails the smoke test"
	switch_upstream "$prev"
	edge_ok || die "public entry fails on $prev too; investigate before switching again"
	stop_jobs "$cur"
	start_jobs "$prev"
	echo "$prev" >"$STATE/active"
	echo "$cur" >"$STATE/previous"
	rm -f "$STATE/migrated"
	log "rolled back to $prev. $cur stays up; run 'deploy.sh retire' to remove it"
}

cmd_retire() {
	lock
	local prev
	prev=$(previous)
	[ -n "$prev" ] || {
		log "nothing to retire"
		return
	}
	[ "$prev" != "$(active)" ] || die "refusing to retire the active slot"
	dc "$prev" down
	rm -f "$STATE/previous"
	log "removed $prev"
}

case ${1:-} in
status) cmd_status ;;
release)
	shift
	cmd_release "$@"
	;;
rollback)
	shift
	cmd_rollback "$@"
	;;
retire) cmd_retire ;;
compose)
	shift
	dc "$(active)" "$@"
	;;
*)
	sed -n '2,8p' "$0"
	exit 2
	;;
esac
