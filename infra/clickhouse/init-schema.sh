#!/usr/bin/env bash
set -euo pipefail

if [[ ! "$CLICKHOUSE_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "CLICKHOUSE_DB must be a simple SQL identifier." >&2
  exit 1
fi

client=(clickhouse-client --host clickhouse --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD")
"${client[@]}" --query "CREATE DATABASE IF NOT EXISTS \`$CLICKHOUSE_DB\`"
for directory in /schema/logparser /schema/analytics; do
  for migration in "$directory"/*.sql; do
    "${client[@]}" --database "$CLICKHOUSE_DB" --multiquery < "$migration"
  done
done
echo "ClickHouse schema and UI aggregates are ready."
