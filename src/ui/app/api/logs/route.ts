import { readLiveLogs } from "@/lib/clickhouse";

export const runtime = "nodejs";

const ALLOWED_LEVELS = new Set(["", "DEBUG", "INFO", "WARNING", "WARN", "ERROR", "CRITICAL"]);

function boundedInteger(value: string | null, fallback: number, minimum: number, maximum: number) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : fallback;
}

export async function GET(request: Request) {
  const searchParams = new URL(request.url).searchParams;
  const dataset = (searchParams.get("dataset") ?? "openstack").trim();
  const search = (searchParams.get("q") ?? "").trim();
  const level = (searchParams.get("level") ?? "").trim().toUpperCase();
  const source = (searchParams.get("source") ?? "").trim();
  if (!/^[a-zA-Z0-9_.-]{1,80}$/.test(dataset)) {
    return Response.json({ error: "Invalid dataset." }, { status: 400 });
  }
  if (search.length > 200 || source.length > 160 || !ALLOWED_LEVELS.has(level)) {
    return Response.json({ error: "Invalid log filter." }, { status: 400 });
  }

  try {
    const page = await readLiveLogs({
      dataset,
      search,
      level,
      source,
      limit: boundedInteger(searchParams.get("limit"), 50, 1, 100),
      offset: boundedInteger(searchParams.get("offset"), 0, 0, 1_000_000),
    });
    return Response.json(page, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to read logs.";
    return Response.json({ error: message }, { status: 503 });
  }
}
