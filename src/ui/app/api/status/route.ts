import { createClickhouseMcpServer } from "@/lib/mcp-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const mcpServer = createClickhouseMcpServer(5_000);

  if (!mcpServer) {
    return Response.json({
      aiConfigured: Boolean(process.env.OPENAI_API_KEY),
      mcp: { configured: false, connected: false, tools: [] },
    });
  }

  try {
    await mcpServer.connect();
    const tools = await mcpServer.listTools();

    return Response.json({
      aiConfigured: Boolean(process.env.OPENAI_API_KEY),
      mcp: {
        configured: true,
        connected: true,
        tools: tools.map((tool) => tool.name),
      },
    });
  } catch {
    return Response.json({
      aiConfigured: Boolean(process.env.OPENAI_API_KEY),
      mcp: { configured: true, connected: false, tools: [] },
    });
  } finally {
    await mcpServer.close().catch(() => undefined);
  }
}
