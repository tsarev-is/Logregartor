import { readServiceSummaries } from "@/lib/clickhouse";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const dataset = (new URL(request.url).searchParams.get("dataset") ?? "").trim();
  if (!/^[a-zA-Z0-9_.-]{1,80}$/.test(dataset)) {
    return Response.json({ error: "Invalid dataset." }, { status: 400 });
  }

  try {
    return Response.json(await readServiceSummaries(dataset), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to read services.";
    return Response.json({ error: message }, { status: 503 });
  }
}
