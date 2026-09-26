#!/usr/bin/env bash
set -euo pipefail

# The MCP call stays open through the 30-minute approval window and verification.
export MCP_REQUEST_TIMEOUT_MS="${MCP_REQUEST_TIMEOUT_MS:-1900000}"
export SERVER_EXECUTION_TIMEOUT_SECONDS="${SERVER_EXECUTION_TIMEOUT_SECONDS:-2100}"
export TURN_SUBSCRIBE_TIMEOUT_MS="${TURN_SUBSCRIBE_TIMEOUT_MS:-2200000}"
if [[ -z "${OUTBOUND_URL_ALLOWED_HOSTS:-}" ]]; then
  export OUTBOUND_URL_ALLOWED_HOSTS='["127.0.0.1","localhost"]'
fi

exec npm exec @truefoundry/trueforge@0.2.1 -- --port "${TRUEFORGE_PORT:-8790}"
