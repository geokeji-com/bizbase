#!/usr/bin/env bash
# Blue-green release for BizBase on the ECS host. Run as root from anywhere.
#
#   deploy.sh status
#   deploy.sh release IMAGE [--migrate]   start the idle slot, smoke-test, switch traffic, hand over jobs
#   deploy.sh rollback [--force]          switch traffic and jobs back to the previous slot
#   deploy.sh retire                      remove the previous slot once rollback is no longer needed
#   deploy.sh maintenance ACTION ...      D-class coordinated outage; see OPERATIONS.md
#   deploy.sh compose ARGS...             docker compose on the active slot outside D windows
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
D=$STATE/maintenance
# The process environment must not override slot-specific image/port settings in Compose.
unset BIZBASE_IMAGE BIZBASE_PORT BIZBASE_PROXY_IP
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
upstream_now() { grep -m1 -E '^[[:space:]]*server[[:space:]]' "$UPSTREAM"; }

lock() {
	mkdir -p "$STATE"
	mkdir "$STATE/.lock" 2>/dev/null || die "another deploy is running (remove $STATE/.lock if it crashed)"
	trap 'rmdir "$STATE/.lock"' EXIT
}

no_maintenance() { [ ! -e "$D" ] || die "D-class window in progress; use maintenance commands, not A/B rollback"; }

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
	asset=$(printf '%s' "$html" | grep -oE '/assets/[^"?]+\.(css|js)' | sed -n '1p') || return 1
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
	if [ -d "$D" ]; then printf "D window: %s (rollback disabled)\n" "$(cat "$D/phase")"; fi
	a=$(active)
	p=$(previous)
	echo "active:   $a (port $(port "$a"), $(project "$a"), $(slot_compose "$a"))"
	echo "previous: ${p:-none}"
	if [ -f "$UPSTREAM" ]; then echo "nginx:    $(upstream_now)"; fi
	if [ -f "$STATE/migrated" ]; then echo "note:     the active slot ran migrate; rollback needs --force"; fi
	docker ps --filter "label=com.docker.compose.project" --format '{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.service"}}\t{{.Image}}\t{{.Status}}' | awk -v p="$LEGACY" '$1==p || $1==p "-blue" || $1==p "-green"' | sort
}

cmd_release() {
	local image=${1:?usage: deploy.sh release IMAGE [--migrate]} migrate=${2:-}
	[ -z "$migrate" ] || [ "$migrate" = --migrate ] || die "unknown option $migrate"
	lock
	no_maintenance
	local cur new old_image expected candidate baseline
	cur=$(active)
	case $cur in legacy | green) new=blue ;; blue) new=green ;; esac
	check_upstream "$cur"

	[ "$(docker image inspect -f '{{.Os}}/{{.Architecture}}' "$image")" = "$ARCH" ] || die "$image is not $ARCH"
	old_image=$(docker inspect -f '{{.Image}}' "$(containers "$cur" backend | head -1)")
	expected=$(LC_ALL=C sort "$SITES_DIR/apps.txt")
	candidate=$(docker run --rm --network none --entrypoint cat "$image" sites/apps.txt | LC_ALL=C sort)
	baseline=$(docker run --rm --network none --entrypoint cat "$old_image" sites/apps.txt | LC_ALL=C sort)
	[ -n "$expected" ] && [ "$expected" = "$candidate" ] && [ "$expected" = "$baseline" ] ||
		die "installed image app sets differ; use D-class maintenance (do not pre-edit apps.txt for A/B release)"
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
	no_maintenance
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
	no_maintenance
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

# D state survives shell exits/reboots. Never expose old code to a renamed schema.
# Stop at the first error. No action here restores databases or rewinds Nginx to old code.
phase() { printf '%s\n' "$1" >"$D/phase.next"; mv "$D/phase.next" "$D/phase"; }
need_phase() { [[ " $* " == *" $(cat "$D/phase") "* ]] || die "wrong maintenance phase: $(cat "$D/phase")"; }
quiescent() {
	local ids
	ids=$(docker ps -q --filter "label=com.docker.compose.project=$(project "$1")")
	[ -z "$ids" ] || die "slot $1 still has live processes; no migration or cutover allowed"
}
maint_run() {
	local side=$1 slot image
	shift
	slot=$(cat "$D/$side"); image=$(cat "$D/$side.image")
	BIZBASE_IMAGE=$image dc "$slot" run --rm --no-deps -T backend "$@"
}
maint_db_check() {
	maint_run new env/bin/python - "$SITE" <<'PYDB'
import os, sys
from pathlib import Path
import frappe
os.chdir("sites")
frappe.init(site=sys.argv[1]); frappe.connect()
try:
    expected = set(Path("apps.txt").read_text().splitlines())
    if frappe.db.db_type != "postgres" or set(frappe.get_installed_apps()) != expected:
        raise RuntimeError("not PostgreSQL or installed apps do not match apps.txt")
finally:
    frappe.destroy()
PYDB
}
cmd_maintenance() {
	local action=${1:-} old old_id new img image_id gw checkpoint manifest actual s
	[ -n "$action" ] || die 'expected begin|freeze|checkpoint|old|manifest|new|migrate|preview|publish|accept|isolate'
	shift; lock
	if [ "$action" = begin ]; then
		no_maintenance
		[ "$#" = 1 ] || die 'usage: maintenance begin IMAGE'
		img=$1; old=$(active); case $old in legacy|green) new=blue ;; blue) new=green ;; *) die 'invalid active slot' ;; esac
		check_upstream "$old"
		[ -z "$(previous)" ] || die 'retire any prior rollback slot separately before maintenance'
		for s in legacy blue green; do [ "$s" = "$old" ] || quiescent "$s"; done
		[ "$(docker image inspect -f '{{.Os}}/{{.Architecture}}' "$img")" = "$ARCH" ] || die 'wrong candidate architecture'
		image_id=$(docker image inspect -f '{{.Id}}' "$img")
		old_id=$(docker inspect -f '{{.Image}}' "$(containers "$old" backend)")
		[ -z "$(docker ps -aq --filter "label=com.docker.compose.project=$(project "$new")")" ] || die 'target not empty; inspect and retire only its stopped containers before begin'
		# Save the legacy fallback before stopping its backend. Publish the marker atomically.
		local draft; draft=$(mktemp -d "$STATE/.maintenance.XXXXXX")
		printf '%s\n' "$old" >"$draft/old"; printf '%s\n' "$old_id" >"$draft/old.image"
		printf '%s\n' "$new" >"$draft/new"; printf '%s\n' "$image_id" >"$draft/new.image"
		printf '%s\n' prepared >"$draft/phase"; echo "$old" >"$STATE/active"; mv "$draft" "$D"
		log "pinned $old and $new images; no traffic or jobs changed"; return
	fi
	[ -d "$D" ] || die 'no D-class window'
	old=$(cat "$D/old"); new=$(cat "$D/new"); image_id=$(cat "$D/new.image")
	case $action in
	freeze)
		need_phase prepared freezing
		check_upstream "$old"; phase freezing
		# Disable HTTP writes before draining. If interrupted, retry without the old backend.
		if running "$old" backend; then dc "$old" exec -T backend bench --site "$SITE" set-maintenance-mode on; fi
		dc "$old" stop -t 120 frontend websocket scheduler worker backend
		quiescent "$old"; phase frozen ;;
	checkpoint)
		need_phase frozen
		checkpoint=${1:?expected verified coordinated backup reference}
		[[ "$checkpoint" =~ ^[a-zA-Z0-9._:-]{1,120}$ ]] || die 'expected a backup identifier, not credentials or a path'
		quiescent "$old"
		printf '%s\n' "$checkpoint" >"$D/checkpoint"
		printf 'BIZBASE_IMAGE=%s\nBIZBASE_PORT=%s\n' "$image_id" "$(port "$new")" >"$STATE/$new.env"
		dc "$new" create --no-build --pull never --no-recreate backend >/dev/null
		gw=$(docker network inspect -f '{{(index .IPAM.Config 0).Gateway}}' "$(project "$new")_default")
		printf 'BIZBASE_PROXY_IP=%s\n' "$gw" >>"$STATE/$new.env"; phase backed-up ;;
	manifest)
		need_phase backed-up; quiescent "$old"; quiescent "$new"
		local tmp; tmp=$(mktemp "$SITES_DIR/.apps.XXXXXX")
		cp -p "$SITES_DIR/apps.txt" "$tmp"
		docker run --rm --network none --entrypoint cat "$image_id" sites/apps.txt >"$tmp"
		[ -s "$tmp" ] && ! grep -qEv '^[a-z][a-z0-9_]*$' "$tmp" || die 'invalid candidate apps.txt'
		mv "$tmp" "$SITES_DIR/apps.txt"; phase candidate ;;
	old|new)
		need_phase backed-up candidate; quiescent "$old"; quiescent "$new"
		[ "$#" -gt 0 ] || die 'expected migration/admin command'
		if [ "$action" = old ]; then need_phase backed-up; else need_phase candidate; fi
		maint_run "$action" "$@" ;;
	migrate)
		need_phase candidate; quiescent "$old"; quiescent "$new"
		manifest=$(docker run --rm --network none --entrypoint cat "$image_id" sites/apps.txt | LC_ALL=C sort)
		actual=$(LC_ALL=C sort "$SITES_DIR/apps.txt")
		[ -n "$manifest" ] && [ "$manifest" = "$actual" ] || die 'candidate manifest and shared apps.txt differ'
		maint_db_check
		maint_run new bench --site "$SITE" migrate
		maint_run new bench --site "$SITE" clear-cache
		maint_db_check; phase migrated ;;
	preview)
		need_phase migrated preview; quiescent "$old"; check_upstream "$old"
		# Old web remains stopped: disabling maintenance opens only the candidate loopback port.
		maint_run new bench --site "$SITE" set-maintenance-mode off
		dc "$new" up -d --no-build --pull never --wait --wait-timeout 300 backend websocket frontend
		smoke "$new"; phase preview; log "validate port $(port "$new") before authorizing publish" ;;
	publish)
		need_phase preview publishing; quiescent "$old"
		if [ "$(cat "$D/phase")" = publishing ]; then
			dc "$new" up -d --no-build --pull never --wait --wait-timeout 300 backend websocket frontend
		fi
		smoke "$new" || die 'candidate smoke failed'
		phase publishing
		if [ "$(upstream_now)" = "$(upstream_line "$old")" ]; then
			check_upstream "$old"; switch_upstream "$new"
		else
			# A failed reload may have updated the file without changing the live workers.
			check_upstream "$new"; "${NGINX[@]}" -s reload
		fi
		if ! edge_ok || ! dc "$new" up -d --no-build --pull never worker scheduler; then
			dc "$new" stop -t 120 frontend scheduler worker
			die 'public check or job start failed; candidate ingress/jobs stopped; never route to pre-migration code'
		fi
		echo "$new" >"$STATE/active.next"; mv "$STATE/active.next" "$STATE/active"
		phase published
		log "traffic and jobs live on $new; verify business routes, then maintenance accept" ;;
	accept)
		need_phase published; quiescent "$old"; check_upstream "$new"
		edge_ok && running "$new" worker && running "$new" scheduler || die 'new slot is not healthy'
		rm -f "$STATE/previous" "$STATE/migrated"
		mv "$D" "$(mktemp -d "$STATE/completed-D.XXXXXX")/record"
		log "D cutover accepted on $new; $old is stopped and is NOT a rollback target" ;;
	isolate)
		# Operator-authorized recovery barrier; no code or data rollback here.
		phase isolating
		for s in "$old" "$new"; do
			if [ -n "$(docker ps -q --filter "label=com.docker.compose.project=$(project "$s")")" ]; then
				dc "$s" stop -t 120 frontend websocket scheduler worker backend
			fi
			quiescent "$s"
		done
		phase isolated
		log 'both slots stopped. Restore the coordinated checkpoint before starting old code.' ;;
	*) die 'unknown maintenance action' ;;
	esac
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
maintenance) shift; cmd_maintenance "$@" ;;
compose)
	no_maintenance
	shift
	dc "$(active)" "$@"
	;;
*)
	sed -n '2,8p' "$0"
	exit 2
	;;
esac
