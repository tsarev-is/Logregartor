// Server-side transport. Browser code calls /api/analytics, never this module.
import { z } from "zod";
import {
  DatasetsSchema, EvidenceSchema, IncidentSchema, ReportSchema, TimelineSchema,
} from "./analytics-contract.ts";

export class AnalyticsError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function responseSchema(path: string) {
  if (path === "health") return z.object({ status: z.literal("ok") });
  if (path === "datasets") return DatasetsSchema;
  if (path === "incidents") return ReportSchema;
  if (/^incidents\/[0-9a-f]{64}\/timeline$/.test(path)) return TimelineSchema;
  if (/^incidents\/[0-9a-f]{64}$/.test(path)) return IncidentSchema;
  if (/^events\/[0-9a-f]{64}$/.test(path)) return EvidenceSchema;
  if (/^(incidents|events)\/[^/]+(\/timeline)?$/.test(path)) {
    throw new AnalyticsError(422, "Evidence IDs must be lowercase SHA-256 strings.");
  }
  throw new AnalyticsError(404, "Unknown Analytics endpoint.");
}

export async function analyticsGet(path: string, query = new URLSearchParams()): Promise<unknown> {
  const schema = responseSchema(path);
  const allowed = path === "incidents" ? ["dataset_id"] :
    path.startsWith("incidents/") || path.startsWith("events/") ? ["analysis_run_id"] : [];
  for (const key of query.keys()) {
    if (!allowed.includes(key)) throw new AnalyticsError(422, `Unsupported parameter: ${key}`);
  }
  const configured = process.env.ANALYTICS_API_URL;
  if (!configured) throw new AnalyticsError(503, "Analytics API is not configured on the server.");
  let url: URL;
  try {
    url = new URL(configured);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error("invalid URL");
    }
    url.pathname = `${url.pathname.replace(/\/$/, "")}/${path === "health" ? path : `v1/${path}`}`;
    url.search = query.toString();
  } catch {
    throw new AnalyticsError(503, "Analytics API URL is invalid.");
  }
  try {
    const response = await fetch(url, {
      cache: "no-store", redirect: "error", signal: AbortSignal.timeout(10_000),
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      const messages: Record<number, string> = {
        404: "No published analysis or evidence found.",
        422: "Invalid dataset, evidence ID or analysis run.",
        503: "Analytics database or schema is unavailable.",
      };
      throw new AnalyticsError(messages[response.status] ? response.status : 502,
        messages[response.status] ?? "Analytics returned an unexpected error.");
    }
    const payload: unknown = await response.json().catch(() => {
      throw new AnalyticsError(502, "Analytics returned invalid JSON.");
    });
    if (!schema.safeParse(payload).success) throw new AnalyticsError(502, "Analytics returned an incompatible response.");
    // Preserve additive upstream fields, after validating those used by the UI.
    return payload;
  } catch (error) {
    if (error instanceof AnalyticsError) throw error;
    throw new AnalyticsError(503, "Analytics API is unavailable. Retry when the service is ready.");
  }
}

export function analyticsErrorResponse(error: unknown) {
  const failure = error instanceof AnalyticsError ? error : new AnalyticsError(502, "Analytics request failed.");
  return Response.json({ detail: failure.message }, {
    status: failure.status, headers: { "Cache-Control": "no-store" },
  });
}
