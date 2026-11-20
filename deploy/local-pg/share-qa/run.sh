#!/bin/bash
# Unique Compose project, no external ports, clean up only this run's resources.
set -euo pipefail
project="shareqa-$(openssl rand -hex 6)"
export QA_DB_PASSWORD="$(openssl rand -hex 24)"
compose=(docker compose -p "$project" -f "$(dirname "$0")/compose.yaml")
trap '"${compose[@]}" down --volumes --remove-orphans' EXIT
"${compose[@]}" run --rm check
