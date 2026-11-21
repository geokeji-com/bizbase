#!/bin/bash
set -euo pipefail
site=frontend
apps=(frappe erpnext yishan_id file_share management_board sales_board ops_board customer_board insights)
if [[ -f sites/$site/site_config.json ]] && { grep -Fxq bizbase_mgmt sites/apps.txt || ! grep -Fxq management_board sites/apps.txt; }; then
  printf '%s\n' '已有站请先按 deploy/prod/management-board-migration.md 在旧镜像离线迁移，不可直接覆盖清单。' >&2
  exit 1
fi
for app in "${apps[@]}"; do test -d "apps/$app"; done
printf '%s\n' "${apps[@]}" > sites/apps.txt
# The base image ships CRM. Keep it importable for sites awaiting data migration.
printf '%s\n' crm >> sites/apps.txt
bench set-config -g db_host db
bench set-config -gp db_port 5432
bench set-config -g redis_cache redis://redis-cache:6379
bench set-config -g redis_queue redis://redis-queue:6379
bench set-config -g redis_socketio redis://redis-queue:6379
bench set-config -gp socketio_port 9000
if [[ ! -f sites/$site/site_config.json ]]; then
  bench new-site "$site" --db-type postgres --db-host db --db-port 5432 --db-root-username postgres \
    --db-root-password "$(cat /run/secrets/db_root)" --admin-password "$(cat /run/secrets/admin_password)" --set-default
fi
for app in "${apps[@]:1}"; do
  bench --site "$site" install-app "$app"
done
bench --site "$site" migrate
bench --site "$site" set-config -p developer_mode 1
bench --site "$site" enable-scheduler
bench --site "$site" clear-cache
