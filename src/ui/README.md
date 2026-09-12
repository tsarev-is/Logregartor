# Logregator Dashboard

Next.js UI for investigating published OpenStack incidents. The main path works
without an LLM: dataset → ranked VM builds → stages → timeline → original log line.
Data comes from Analytics through server-side `/api/analytics/*` routes. Every
incident and evidence link stays pinned to its completed `analysis_run_id`.

See [Dashboard integration](../../docs/DASHBOARD_INTEGRATION.md) for API contracts,
empty/error states, chat actions, module boundaries and end-to-end setup.

## Local development

Requires Node.js 22.18+ and an Analytics API (default host port 8080):

```bash
npm ci
cp .env.example .env.local
npm run dev
```

Set `ANALYTICS_API_URL=http://127.0.0.1:8080` in `.env.local`. Open
<http://localhost:3000>. Import data with LogParser and publish an Analytics run
before expecting incidents; an empty or unavailable backend is displayed explicitly.

## Docker Compose

From the repository root:

```bash
docker compose up -d --build --wait clickhouse analytics ui
# After importing logs, choose an explicit threshold or reference baseline:
docker compose exec analytics python -m log_analytics run \
  --dataset-id openstack --threshold-seconds 27.91
```

The threshold is an example, not a default. In Compose the UI uses
`ANALYTICS_API_URL=http://analytics:8080`. `/api/health` checks UI liveness;
`/api/status` checks Analytics and MCP independently.

## Optional AI investigation

Configure `OPENAI_API_KEY`, optionally `OPENAI_MODEL`, and the MCP connection as
described in [MCP ClickHouse](../../docs/MCP_CLICKHOUSE.md). The OpenAI Agents SDK,
MCP client and credentials remain server-side. The selected dataset, incident or
evidence context is fetched and validated by the server. The model returns typed
links; their dataset, object and analysis run are checked against Analytics before
being sent to the browser. There is no fabricated incident fallback.

Allowed MCP tools: `list_databases`, `list_tables`, `run_query`. Without MCP,
chat can use the selected Analytics observation but cannot retrieve additional logs.
Analytics data stays usable when AI is unavailable.

## Validation

```bash
npm test           # Node tests; Python 3.11+ generates real Analytics contracts
npm run typecheck
npm run build
```

Contract tests require no database, model key or network. Database integration tests
and manual setup are documented in [Analytics](../Analytics/README.md).
