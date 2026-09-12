import { createClickhouseMcpServer } from "@/lib/mcp-client";
import { analyticsGet } from "@/lib/analytics-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function mcpStatus() {
  const server = createClickhouseMcpServer(5_000);
  if (!server) return { configured: false, connected: false, tools: [] };
  try {
    await server.connect();
    const tools = await server.listTools();
    return { configured: true, connected: true, tools: tools.map((tool) => tool.name) };
  } catch {
    return { configured: true, connected: false, tools: [] };
  } finally {
    await server.close().catch(() => undefined);
  }
}
export async function GET() {
  const [mcp, analyticsConnected] = await Promise.all([
    mcpStatus(), analyticsGet("health").then(() => true, () => false),
  ]);
  return Response.json({
    aiConfigured: Boolean(process.env.OPENAI_API_KEY), mcp,
    analytics: { configured: Boolean(process.env.ANALYTICS_API_URL), connected: analyticsConnected },
  }, { headers: { "Cache-Control": "no-store" } });
}
