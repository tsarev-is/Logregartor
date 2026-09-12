#!/usr/bin/env bash
set -euo pipefail

: "${CLICKHOUSE_MCP_PASSWORD:?Set CLICKHOUSE_MCP_PASSWORD in the local .env file}"
if [[ ! "$CLICKHOUSE_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "CLICKHOUSE_DB must be a simple SQL identifier." >&2
  exit 1
fi

# Run on every MCP startup, including when ClickHouse already has a data volume.
# Passwords use query parameters; GRANT requires a validated literal identifier.
clickhouse-client \
  --host clickhouse \
  --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" \
  --param_mcp_password="$CLICKHOUSE_MCP_PASSWORD" \
  --multiquery <<'SQL'
CREATE USER IF NOT EXISTS logregartor_mcp
  IDENTIFIED WITH sha256_password BY {mcp_password:String};
ALTER USER logregartor_mcp
  IDENTIFIED WITH sha256_password BY {mcp_password:String}
  SETTINGS readonly = 1,
           max_execution_time = 30,
           max_result_rows = 10000,
           result_overflow_mode = 'throw',
           max_memory_usage = 1000000000;
SQL

clickhouse-client \
  --host clickhouse \
  --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" \
  --query "GRANT SELECT ON \`$CLICKHOUSE_DB\`.* TO logregartor_mcp"

echo "ClickHouse MCP reader is ready."
