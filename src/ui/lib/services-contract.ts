export type ServiceSummary = {
  datasetId: string;
  service: string;
  eventCount: number;
  errorCount: number;
  logErrorRate: number | null;
  firstEventTimeMs: number | null;
  lastEventTimeMs: number | null;
  httpLatencySampleCount: number;
  httpP95Seconds: number | null;
};

export function isServiceSummaryList(value: unknown): value is ServiceSummary[] {
  return Array.isArray(value) && value.every((item) => (
    item &&
    typeof item === "object" &&
    typeof item.datasetId === "string" &&
    typeof item.service === "string" &&
    typeof item.eventCount === "number" &&
    typeof item.errorCount === "number" &&
    (item.logErrorRate === null || typeof item.logErrorRate === "number") &&
    (item.firstEventTimeMs === null || typeof item.firstEventTimeMs === "number") &&
    (item.lastEventTimeMs === null || typeof item.lastEventTimeMs === "number") &&
    typeof item.httpLatencySampleCount === "number" &&
    (item.httpP95Seconds === null || typeof item.httpP95Seconds === "number")
  ));
}
