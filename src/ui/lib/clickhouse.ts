import type { LiveLogEvent, LiveLogsPage } from "@/lib/logs-contract";
import type { ServiceSummary } from "@/lib/services-contract";

type ClickHouseParams = Record<string, string | number>;

function connection() {
  const endpoint = process.env.LOGS_CLICKHOUSE_URL ?? "http://127.0.0.1:8123";
  const database = process.env.LOGS_CLICKHOUSE_DATABASE ?? "logs";
  const user = process.env.LOGS_CLICKHOUSE_USER ?? "logregartor";
  const password = process.env.LOGS_CLICKHOUSE_PASSWORD ?? "localdev";
  const parsed = new URL(endpoint);
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error("LOGS_CLICKHOUSE_URL must be an HTTP(S) endpoint without embedded credentials.");
  }
  return { endpoint: parsed, database, authorization: `Basic ${Buffer.from(`${user}:${password}`).toString("base64")}` };
}

async function rows<T>(sql: string, params: ClickHouseParams, signal: AbortSignal): Promise<T[]> {
  const { endpoint, database, authorization } = connection();
  const url = new URL(endpoint);
  url.searchParams.set("database", database);
  url.searchParams.set("wait_end_of_query", "1");
  url.searchParams.set("date_time_input_format", "best_effort");
  url.searchParams.set("readonly", "1");
  url.searchParams.set("max_execution_time", "15");
  url.searchParams.set("max_result_rows", "1000");
  url.searchParams.set("result_overflow_mode", "throw");
  for (const [name, value] of Object.entries(params)) url.searchParams.set(`param_${name}`, String(value));

  const response = await fetch(url, {
    method: "POST",
    headers: { Authorization: authorization, "Content-Type": "text/plain; charset=utf-8" },
    body: `${sql}\nFORMAT JSONEachRow`,
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    const detail = (await response.text()).replaceAll(/\s+/g, " ").slice(0, 500);
    throw new Error(`ClickHouse returned ${response.status}${detail ? `: ${detail}` : ""}`);
  }
  const text = await response.text();
  return text.trim() ? text.trim().split("\n").map((line) => JSON.parse(line) as T) : [];
}

function asNumber(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function asNullableNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const FILTER = `
WHERE dataset_id = {dataset:String}
  AND ({source:String} = '' OR source_file = {source:String})
  AND ({component:String} = '' OR ifNull(component, '') = {component:String})
  AND ({level:String} = '' OR ifNull(level, '') = {level:String})
  AND (
    {search:String} = ''
    OR positionCaseInsensitiveUTF8(message, {search:String}) > 0
    OR positionCaseInsensitiveUTF8(raw_text, {search:String}) > 0
    OR positionCaseInsensitiveUTF8(toString(event_id), {search:String}) > 0
    OR positionCaseInsensitiveUTF8(ifNull(request_id, ''), {search:String}) > 0
    OR positionCaseInsensitiveUTF8(ifNull(instance_id, ''), {search:String}) > 0
    OR positionCaseInsensitiveUTF8(ifNull(component, ''), {search:String}) > 0
  )`;

export async function readLiveLogs(input: {
  dataset: string;
  search: string;
  level: string;
  source: string;
  component: string;
  limit: number;
  offset: number;
}): Promise<LiveLogsPage> {
  const signal = AbortSignal.timeout(15_000);
  const params = { ...input };
  const eventsSql = `
SELECT
  toString(event_id) AS eventId,
  dataset_id AS datasetId,
  if(isNull(event_time), NULL, toUnixTimestamp64Milli(event_time)) AS timestampMs,
  level,
  component,
  message,
  raw_text AS rawText,
  request_id AS requestId,
  instance_id AS instanceId,
  template_id AS templateId,
  source_file AS sourceFile,
  line_start AS lineStart,
  parse_status AS parseStatus,
  template_status AS templateStatus
FROM log_events
${FILTER}
ORDER BY event_time DESC NULLS LAST, source_file, line_start DESC, event_id
LIMIT {limit:UInt32} OFFSET {offset:UInt32}`;
  const countSql = `SELECT count() AS total FROM log_events ${FILTER}`;
  const facetsSql = `
SELECT
  arraySort(groupUniqArray(ifNull(level, ''))) AS levels,
  arraySort(groupUniqArray(source_file)) AS sources,
  arraySort(groupUniqArray(ifNull(component, ''))) AS components
FROM log_events
WHERE dataset_id = {dataset:String}`;

  const [events, counts, facets] = await Promise.all([
    rows<LiveLogEvent>(eventsSql, params, signal),
    rows<{ total: string }>(countSql, params, signal),
    rows<{ levels: string[]; sources: string[]; components: string[] }>(facetsSql, params, signal),
  ]);
  return {
    dataset: input.dataset,
    total: asNumber(counts[0]?.total),
    limit: input.limit,
    offset: input.offset,
    events,
    facets: {
      levels: (facets[0]?.levels ?? []).filter(Boolean),
      sources: facets[0]?.sources ?? [],
      components: (facets[0]?.components ?? []).filter(Boolean),
    },
  };
}

export async function readServiceSummaries(dataset: string): Promise<ServiceSummary[]> {
  const signal = AbortSignal.timeout(15_000);
  const sql = `
SELECT
  dataset_id AS datasetId,
  service,
  event_count AS eventCount,
  error_count AS errorCount,
  log_error_rate AS logErrorRate,
  if(isNull(first_event_time), NULL, toUnixTimestamp64Milli(first_event_time)) AS firstEventTimeMs,
  if(isNull(last_event_time), NULL, toUnixTimestamp64Milli(last_event_time)) AS lastEventTimeMs,
  http_latency_sample_count AS httpLatencySampleCount,
  http_p95_seconds AS httpP95Seconds
FROM ui_service_summary
WHERE dataset_id = {dataset:String}
ORDER BY error_count DESC, event_count DESC, service
LIMIT 200`;
  const records = await rows<Record<string, unknown>>(sql, { dataset }, signal);
  return records.map((row) => ({
    datasetId: String(row.datasetId ?? ""),
    service: String(row.service ?? ""),
    eventCount: asNumber(row.eventCount),
    errorCount: asNumber(row.errorCount),
    logErrorRate: asNullableNumber(row.logErrorRate),
    firstEventTimeMs: asNullableNumber(row.firstEventTimeMs),
    lastEventTimeMs: asNullableNumber(row.lastEventTimeMs),
    httpLatencySampleCount: asNumber(row.httpLatencySampleCount),
    httpP95Seconds: asNullableNumber(row.httpP95Seconds),
  })).filter((row) => row.datasetId && row.service);
}
