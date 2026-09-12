# Demo commands

Use one Bash session; requires Docker Compose, Go 1.26.3, Python 3.11+ and curl.

Run from the repository root.

```bash
cd "$(git rev-parse --show-toplevel)"
```

Validate the Compose configuration.

```bash
docker compose --profile mcp config --quiet
```

Start ClickHouse and create all tables and views.

```bash
docker compose up -d --wait clickhouse
docker compose run --rm clickhouse-init
```

Build and start Analytics and the dashboard.

```bash
docker compose up -d --build --wait analytics ui
```

Start AI research services; set `OPENAI_API_KEY`, `CLICKHOUSE_MCP_PASSWORD` and `CLICKHOUSE_MCP_AUTH_TOKEN` in `.env` first.

```bash
docker compose --profile mcp up -d --build --wait
docker compose exec -T mcp-clickhouse python /app/smoke.py
```

Show service status and published ports.

```bash
docker compose --profile mcp ps -a
```

Define SQL and API helpers using the running Compose services.

```bash
ch() {
  docker compose exec -T clickhouse sh -c '
    exec clickhouse-client --host 127.0.0.1 \
      --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
      --database "$CLICKHOUSE_DB" --multiquery "$@"
  ' sh "$@"
}
ANALYTICS_URL="http://$(docker compose port analytics 8080)"
UI_URL="http://127.0.0.1:$(docker compose port ui 3000 | awk -F: 'NR == 1 {print $NF}')"
api() { curl -fsS "${ANALYTICS_URL}$1" | python3 -m json.tool; }
```

Connect the local importer to the same ClickHouse database and credentials.

```bash
export CLICKHOUSE_URL="http://$(docker compose port clickhouse 8123)"
export CLICKHOUSE_DB="$(docker compose exec -T clickhouse printenv CLICKHOUSE_DB)"
export CLICKHOUSE_USER="$(docker compose exec -T clickhouse printenv CLICKHOUSE_USER)"
export CLICKHOUSE_PASSWORD="$(docker compose exec -T clickhouse printenv CLICKHOUSE_PASSWORD)"
```

Install LogParser dependencies and build the parser.

```bash
(
  set -e
  cd src/LogParser
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
  go build -o bin/logparser .
)
```

Download and verify the real OpenStack archive; reuse cached downloads on repeat runs.

```bash
(
  cd src/LogParser &&
  .venv/bin/python -m pipeline prepare --output-dir data/openstack
)
```

Import all three real log files into ClickHouse; repeated imports skip completed files.

```bash
(
  cd src/LogParser &&
  .venv/bin/python -m pipeline run \
    --input data/openstack/openstack_normal1.log \
    --input data/openstack/openstack_normal2.log \
    --input data/openstack/openstack_abnormal.log \
    --reference data/openstack/openstack_normal1.log \
    --dataset-id openstack \
    --state-dir state/openstack-v1 \
    --work-dir output/openstack
)
```

Show the import report.

```bash
python3 -m json.tool src/LogParser/output/openstack/ingestion.json
```

Check imported files, row counts and historical time ranges; the full archive has 207,820 rows.

```bash
ch --query "SELECT source_file, count() AS events,
  min(event_time) AS first_event, max(event_time) AS last_event
  FROM log_events WHERE dataset_id = 'openstack'
  GROUP BY source_file ORDER BY source_file FORMAT PrettyCompact"
```

Detect slow VM builds and publish incidents to the dashboard; this archive yields four incidents.

```bash
docker compose exec -T analytics python -m log_analytics run \
  --dataset-id openstack --threshold-seconds 27.91
```

Use the reference file's maximum build duration plus five seconds as the threshold instead.

```bash
docker compose exec -T analytics python -m log_analytics run \
  --dataset-id openstack \
  --reference-source 4e4d47347bdae198056bb3b0a8a755e1cb0100d6c6a30bbd4058684234769199 \
  --margin-seconds 5
```

Print the dashboard URL and check Analytics, MCP and AI configuration status.

```bash
printf '%s\n' "$UI_URL"
curl -fsS "$UI_URL/api/status" | python3 -m json.tool
api /health
```

Show available datasets and whether the analysis needs refreshing.

```bash
api /v1/datasets
```

Show analysis counters and the ranked slowest VM builds.

```bash
ch --query "SELECT * FROM ui_analysis_summary
  WHERE dataset_id = 'openstack' FORMAT Vertical"
ch --query "SELECT instance_id, observed_seconds, threshold_seconds,
  excess_seconds, completeness_status FROM ui_incident_details
  WHERE dataset_id = 'openstack'
  ORDER BY excess_seconds DESC, incident_id FORMAT PrettyCompact"
```

Show the dataset summary and components with the most error logs.

```bash
ch --query "SELECT * FROM ui_dataset_summary
  WHERE dataset_id = 'openstack' FORMAT Vertical"
ch --query "SELECT service, event_count, error_count, log_error_rate
  FROM ui_service_summary WHERE dataset_id = 'openstack'
  ORDER BY error_count DESC, service LIMIT 10 FORMAT PrettyCompact"
```

Show the most frequent recognized log templates.

```bash
ch --query "SELECT t.template_text, count() AS events
  FROM log_events AS e INNER JOIN event_templates AS t
    ON e.template_id = t.template_id AND e.template_version = t.template_version
  WHERE e.dataset_id = 'openstack'
  GROUP BY t.template_text ORDER BY events DESC LIMIT 10 FORMAT PrettyCompact"
```

Select the slowest incident and pin subsequent requests to its analysis snapshot.

```bash
read -r INCIDENT_ID ANALYSIS_RUN_ID EVENT_ID < <(
  ch --query "SELECT incident_id, toString(analysis_run_id), evidence_ids[1]
    FROM ui_incident_details WHERE dataset_id = 'openstack'
    ORDER BY excess_seconds DESC, incident_id LIMIT 1 FORMAT TSV"
)
```

Show the incident card, VM stages and exact source log record.

```bash
api "/v1/incidents/$INCIDENT_ID?analysis_run_id=$ANALYSIS_RUN_ID"
api "/v1/incidents/$INCIDENT_ID/timeline?analysis_run_id=$ANALYSIS_RUN_ID"
api "/v1/events/$EVENT_ID?analysis_run_id=$ANALYSIS_RUN_ID"
```

Export the current incident report for the presentation.

```bash
mkdir -p src/Analytics/output
curl -fsS "$ANALYTICS_URL/v1/incidents?dataset_id=openstack" \
  -o src/Analytics/output/openstack-incidents.json
```

Reload prepared events without downloading or parsing again; completed imports are skipped.

```bash
(
  cd src/LogParser &&
  .venv/bin/python -m pipeline load \
    --input output/openstack/events.jsonl --state-dir state/openstack-v1
)
```

Check that the published dataset has no duplicate event IDs.

```bash
ch --query "SELECT count() AS rows, uniqExact(event_id) AS unique_events,
  rows - unique_events AS duplicates
  FROM log_events WHERE dataset_id = 'openstack' FORMAT PrettyCompact"
```

Show a completed analysis with zero incidents using a higher threshold.

```bash
docker compose exec -T analytics python -m log_analytics run \
  --dataset-id openstack --threshold-seconds 100
api /v1/datasets
```

Restore the four-incident demo.

```bash
docker compose exec -T analytics python -m log_analytics run \
  --dataset-id openstack --threshold-seconds 27.91
```

Follow service logs; press Ctrl+C to stop following.

```bash
docker compose --profile mcp logs --tail=100 -f analytics ui clickhouse mcp-clickhouse
```

Restart Analytics and the dashboard.

```bash
docker compose restart analytics ui
```

Delete analysis results and history for all datasets; keep imported logs. Run after any analysis finishes.

```bash
ch <<'SQL'
TRUNCATE TABLE analysis_runs;
TRUNCATE TABLE incidents_raw;
TRUNCATE TABLE incident_evidence_raw;
SQL
```

Delete all imported logs, templates and analysis history; keep schemas. Run after all imports and analyses finish.

```bash
ch <<'SQL'
TRUNCATE TABLE analysis_runs;
TRUNCATE TABLE ingestion_runs;
TRUNCATE TABLE incidents_raw;
TRUNCATE TABLE incident_evidence_raw;
TRUNCATE TABLE log_events_raw;
TRUNCATE TABLE event_templates_raw;
SQL
```

Verify that published logs and incidents are empty.

```bash
ch --query "SELECT
  (SELECT count() FROM log_events) AS events,
  (SELECT count() FROM incidents) AS incidents FORMAT PrettyCompact"
api /v1/datasets
```

Refill ClickHouse from local prepared events and rebuild the demo after cleanup.

```bash
(
  cd src/LogParser &&
  .venv/bin/python -m pipeline load \
    --input output/openstack/events.jsonl --state-dir state/openstack-v1
) && docker compose exec -T analytics python -m log_analytics run \
  --dataset-id openstack --threshold-seconds 27.91
```

Stop all services and keep database contents.

```bash
docker compose --profile mcp down
```

Permanently delete the ClickHouse volume and all database contents; local parser artifacts remain.

```bash
docker compose --profile mcp down -v
```
