#!/usr/bin/env bash
set -euo pipefail

# Guard script to verify required configuration before restarting services.
#
# Usage:
#   scripts/pre_restart_check.sh [ENV_FILE]
#
# When ENV_FILE is omitted, defaults to ".env" in the repository root.

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$WORKDIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

echo "Validating environment configuration via scripts.check_env..."
python -m scripts.check_env check --env-file "$ENV_FILE"
echo "Environment validation passed."
