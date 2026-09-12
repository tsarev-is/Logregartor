import {
  Agent,
  Runner,
  type AgentInputItem,
} from "@openai/agents";
import { z } from "zod";
import { UI_ACTION_KINDS, isChatReply } from "@/lib/chat-contract";
import { createClickhouseMcpServer } from "@/lib/mcp-client";

export const runtime = "nodejs";
export const maxDuration = 120;

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const ChatReplySchema = z.object({
  message: z.string().describe("Concise operator-facing answer in the user's language."),
  actions: z
    .array(
      z.object({
        kind: z.enum(UI_ACTION_KINDS),
        label: z.string(),
        title: z.string(),
        description: z.string(),
        targetId: z.string(),
      }),
    )
    .max(3)
    .describe("UI links backed by identifiers found in MCP results. Empty when no verified target exists."),
});

const SYSTEM_PROMPT = `You are Logregator, an incident investigation copilot embedded in an observability UI.
Answer in the operator's language. Be concise and operational.

For every question about real system data, use the read-only ClickHouse MCP tools before making claims. Start with list_databases and list_tables when the schema is unknown, then use run_query for bounded SELECT queries. Prefer the finalized log_events and event_templates views when they exist; do not use unfinished rows from log_events_raw. Discover historical dataset time ranges instead of assuming that the logs are recent. Limit raw-event queries and include stable IDs, UTC timestamps, filters, and query evidence in the answer. Never invent identifiers, log lines, schema fields, or query results. If evidence is insufficient, explain what is missing.

For root-cause hypotheses include confidence, supporting evidence, contradicting evidence, and next checks.

You can add typed UI actions to your answer. An action becomes a clickable card in chat and opens data in the main workspace. Only create an action when targetId came from an MCP result or is explicitly present in the conversation. Use open_incident for an incident overview, show_timeline for correlated evidence, show_logs for a bounded log result, and show_service for service details. Return an empty actions array when there is no verified target.`;

function toAgentInput(messages: ChatMessage[]): AgentInputItem[] {
  return messages.map((message) =>
    message.role === "user"
      ? { role: "user", content: message.content }
      : {
          role: "assistant",
          status: "completed",
          content: [{ type: "output_text", text: message.content }],
        },
  );
}

export async function POST(request: Request) {
  if (!process.env.OPENAI_API_KEY) {
    return Response.json(
      { error: "OPENAI_API_KEY is not configured on the server." },
      { status: 503 },
    );
  }

  const body = (await request.json()) as { messages?: ChatMessage[] };
  const messages = (body.messages ?? []).slice(-20).filter(
    (message) =>
      (message.role === "user" || message.role === "assistant") &&
      typeof message.content === "string" &&
      message.content.trim().length > 0 &&
      message.content.length <= 10_000,
  );

  if (messages.length === 0) {
    return Response.json({ error: "At least one message is required." }, { status: 400 });
  }

  const mcpServer = createClickhouseMcpServer();

  try {
    if (mcpServer) await mcpServer.connect();

    const agent = new Agent({
      name: "Logregator incident copilot",
      model: process.env.OPENAI_MODEL ?? "gpt-5.4",
      instructions: SYSTEM_PROMPT,
      mcpServers: mcpServer ? [mcpServer] : [],
      mcpConfig: {
        convertSchemasToStrict: true,
        errorFunction: null,
      },
      outputType: ChatReplySchema,
    });

    const runner = new Runner({ tracingDisabled: true });
    const result = await runner.run(agent, toAgentInput(messages), {
      maxTurns: 8,
      signal: AbortSignal.timeout(90_000),
    });
    const reply: unknown = result.finalOutput;

    if (!isChatReply(reply)) {
      throw new Error("The model returned an invalid UI response.");
    }

    return Response.json(reply, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to complete AI response.";
    return Response.json({ error: message }, { status: 500 });
  } finally {
    await mcpServer?.close().catch(() => undefined);
  }
}
