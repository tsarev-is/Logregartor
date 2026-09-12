export function formatUtc(timestamp: string) {
  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) return timestamp;

  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(date);
}

export function formatUtcMillis(timestampMs: number | null) {
  if (timestampMs === null) return "No timestamp";
  const date = new Date(timestampMs);
  return Number.isNaN(date.getTime()) ? String(timestampMs) : formatUtc(date.toISOString());
}
