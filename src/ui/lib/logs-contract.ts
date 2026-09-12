export type LiveLogEvent = {
  eventId: string;
  datasetId: string;
  timestampMs: number | null;
  level: string | null;
  component: string | null;
  message: string;
  rawText: string;
  requestId: string | null;
  instanceId: string | null;
  templateId: string | null;
  sourceFile: string;
  lineStart: number;
  parseStatus: string;
  templateStatus: string;
};

export type LiveLogsPage = {
  dataset: string;
  total: number;
  limit: number;
  offset: number;
  events: LiveLogEvent[];
  facets: {
    levels: string[];
    sources: string[];
    components: string[];
  };
};

export function isLiveLogsPage(value: unknown): value is LiveLogsPage {
  if (!value || typeof value !== "object") return false;
  const page = value as Partial<LiveLogsPage>;
  return (
    typeof page.dataset === "string" &&
    typeof page.total === "number" &&
    typeof page.limit === "number" &&
    typeof page.offset === "number" &&
    Array.isArray(page.events) &&
    page.events.every((event) =>
      event &&
      typeof event.eventId === "string" &&
      typeof event.message === "string" &&
      typeof event.rawText === "string" &&
      typeof event.sourceFile === "string" &&
      typeof event.lineStart === "number",
    ) &&
    Boolean(page.facets) &&
    Array.isArray(page.facets?.levels) &&
    Array.isArray(page.facets?.sources) &&
    Array.isArray(page.facets?.components)
  );
}
