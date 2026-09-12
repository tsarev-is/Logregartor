import {
  MCPServerStreamableHttp,
  createMCPToolStaticFilter,
} from "@openai/agents";

export const ALLOWED_MCP_TOOLS = [
  "list_databases",
  "list_tables",
  "run_query",
] as const;

export function createClickhouseMcpServer(timeout = 30_000) {
  const url = process.env.MCP_SERVER_URL;
  if (!url) return undefined;

  const token =
    process.env.CLICKHOUSE_MCP_AUTH_TOKEN ?? process.env.MCP_AUTHORIZATION;

  return new MCPServerStreamableHttp({
    name: "clickhouse",
    url,
    cacheToolsList: true,
    timeout,
    toolFilter: createMCPToolStaticFilter({
      allowed: [...ALLOWED_MCP_TOOLS],
    }),
    requestInit: token
      ? { headers: { Authorization: `Bearer ${token}` } }
      : undefined,
  });
}
