import { IncidentWorkspace } from "@/components/incident-workspace";

export default function Home() {
  return (
    <IncidentWorkspace
      aiConfigured={Boolean(process.env.OPENAI_API_KEY)}
      mcpConfigured={Boolean(process.env.MCP_SERVER_URL)}
    />
  );
}
