import OpenAI from "openai";
import type { ResponseCreateParamsNonStreaming } from "openai/resources/responses/responses";
import { CHAT_REPLY_SCHEMA, isChatReply } from "@/lib/chat-contract";

export const runtime = "nodejs";
export const maxDuration = 120;

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const SYSTEM_PROMPT = `You are Logregator, an incident investigation copilot embedded in an observability UI.
Use observability MCP tools to inspect logs, incidents, services and evidence before making claims.
Answer in the operator's language. Be concise and operational.
For root-cause hypotheses include confidence, supporting evidence, contradicting evidence and next checks.
Never invent identifiers, log lines or query results. If evidence is insufficient, explain what is missing.

You can add typed UI actions to your answer. An action becomes a clickable card in chat and opens data in the main workspace.
Only create an action when its targetId came from an MCP result or is explicitly present in the conversation.
Use open_incident for an incident overview, show_timeline for correlated evidence, show_logs for log results, and show_service for service details.
Return an empty actions array when there is no verified target.`;

const ALLOWED_MCP_TOOLS = [
  "list_databases",
  "list_tables",
  "run_query",
];

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

  const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const mcpUrl = process.env.MCP_SERVER_URL;
  const tools: ResponseCreateParamsNonStreaming["tools"] = mcpUrl
    ? [
        {
          type: "mcp",
          server_label: "observability_database",
          server_description:
            "Read-only access to incidents, service topology, log events and anomaly evidence.",
          server_url: mcpUrl,
          ...(process.env.MCP_AUTHORIZATION
            ? { authorization: process.env.MCP_AUTHORIZATION }
            : {}),
          require_approval: "never",
          allowed_tools: ALLOWED_MCP_TOOLS,
        },
      ]
    : [];

  try {
    const response = await client.responses.create({
      model: process.env.OPENAI_MODEL ?? "gpt-5.4",
      instructions: SYSTEM_PROMPT,
      input: messages.map((message) => ({
        role: message.role,
        content: message.content,
      })),
      tools,
      tool_choice: "auto",
      max_output_tokens: 1600,
      text: {
        format: {
          type: "json_schema",
          name: "logregator_ui_reply",
          strict: true,
          schema: CHAT_REPLY_SCHEMA,
        },
      },
    });

    const reply: unknown = JSON.parse(response.output_text);
    if (!isChatReply(reply)) {
      throw new Error("The model returned an invalid UI response.");
    }

    return Response.json(reply, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to complete AI response.";
    return Response.json({ error: message }, { status: 500 });
  }
}
