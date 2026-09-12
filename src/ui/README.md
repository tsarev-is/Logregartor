# Logregator

Evidence-first incident investigation UI with a server-side OpenAI copilot and read-only MCP access to observability data.

## Architecture

```text
Browser (Next.js UI)
        |
        | POST /api/chat (typed JSON)
        v
Next.js Route Handler
        |
        +---- OpenAI Agents SDK ---- OpenAI Responses API
        |
        +---- Streamable HTTP ---- Read-only ClickHouse MCP
                                             |
                                             v
                                         ClickHouse
```

The OpenAI Agents SDK and MCP client run only in the Next.js server route. `OPENAI_API_KEY` and MCP credentials are never sent to the browser. The server connects directly to the local Streamable HTTP MCP endpoint, so the MCP port does not need a public tunnel. The model returns a strict `message + actions[]` contract. The UI renders actions as links which open an incident, timeline, log set or service in the main workspace. The model never sends HTML or arbitrary UI code.

## Run locally

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open <http://localhost:3000>. The dashboard has seeded incident evidence for the demo. Chat requests become live after `OPENAI_API_KEY` is configured. For a locally published MCP port, use `MCP_SERVER_URL=http://127.0.0.1:8000/mcp` and the same `CLICKHOUSE_MCP_AUTH_TOKEN` as the MCP server.

Without credentials, click **Open demo incident** to test the complete chat-card-to-dashboard interaction.

## Run with Docker Compose

```bash
cd ../..
cp .env.example .env
docker compose --profile mcp up -d --build --wait
```

The root `ui` service builds this directory and includes a health check at `/api/health`. Inside Compose, the server uses `http://mcp-clickhouse:8000/mcp` and forwards `CLICKHOUSE_MCP_AUTH_TOKEN` as a bearer token.

## MCP contract for the first demo

The agent receives only the three read-only tools exposed by `mcp-clickhouse`:

- `list_databases`
- `list_tables`
- `run_query`

The dedicated ClickHouse user is limited to `SELECT`, while the agent prompt requires bounded queries against finalized views and stable evidence IDs.
