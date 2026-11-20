#!/bin/bash
# Run only in the ephemeral acceptance container (no shared sites mount).
set -euo pipefail
test ! -e sites/share-qa.test
printf '%s\n' frappe erpnext file_share > sites/apps.txt
bench set-config -g db_host db
bench set-config -gp db_port 5432
bench set-config -g redis_cache redis://redis:6379/0
bench set-config -g redis_queue redis://redis:6379/1
bench new-site share-qa.test --db-type postgres --db-host db --db-port 5432 --db-root-username postgres --db-root-password "$QA_DB_PASSWORD" --admin-password "$QA_DB_PASSWORD" --set-default
bench --site share-qa.test install-app erpnext
bench --site share-qa.test set-config file_share_primary_origin https://company.example
bench --site share-qa.test install-app file_share
bench --site share-qa.test migrate
env/bin/python /qa/check.py
