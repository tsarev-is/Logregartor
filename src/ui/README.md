# Logregator

Evidence-first incident investigation UI with a server-side OpenAI copilot and read-only MCP access to observability data.

## Architecture

```text
Browser (Next.js UI)
        |
        | POST /api/chat (typed JSON)
        v
Next.js Route Handler -----> OpenAI Responses API
                                  |
                                  | remote MCP tool calls
                                  v
                         Read-only observability MCP
                                  |
                                  v
                              PostgreSQL
```

The OpenAI SDK runs only in the Next.js server route. `OPENAI_API_KEY` and MCP credentials are never sent to the browser. The model returns a strict `message + actions[]` contract. The UI renders actions as links which open an incident, timeline, log set or service in the main workspace. The model never sends HTML or arbitrary UI code.

The remote MCP server must be reachable from the OpenAI API over HTTPS; for local hackathon development, expose it through a tunnel.

## Run locally

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open <http://localhost:3000>. The dashboard has seeded incident evidence for the demo. Chat requests become live after `OPENAI_API_KEY` is configured; MCP-backed investigation additionally requires `MCP_SERVER_URL`.

Without credentials, click **Open demo incident** to test the complete chat-card-to-dashboard interaction.

## Run with Docker Compose

```bash
cd ../..
cp .env.example .env
docker compose up --build ui
```

The root `ui` service builds this directory and includes a health check at `/api/health`. ClickHouse already lives in the same Compose project; MCP and other services can be added later without changing the browser-to-server chat contract.

## MCP contract for the first demo

Keep the MCP surface small and read-only. These tools are enough:

- `get_incident(incident_id)`
- `search_logs(from, to, services, levels, query, limit)`
- `get_service_topology(service, depth)`
- `get_anomalies(from, to, services)`
- `get_evidence(evidence_ids)`

Return stable IDs, UTC timestamps and bounded result sets. The server route currently sets MCP approval to `never`, so only expose tools safe for automatic use.
