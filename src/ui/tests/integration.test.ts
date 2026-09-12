import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { afterEach, test } from "node:test";
import { analyticsGet, AnalyticsError } from "../lib/analytics-client.ts";
import { ChatReplySchema, ChatRequestSchema, type UiAction } from "../lib/chat-contract.ts";
import { DatasetsSchema, EvidenceSchema, IncidentSchema, ReportSchema, TimelineSchema, snapshotQuery } from "../lib/analytics-contract.ts";
import { investigationContext, verifiedActions } from "../lib/investigation.ts";

const fixture = JSON.parse(execFileSync("python3", [fileURLToPath(new URL("fixtures.py", import.meta.url))], { encoding: "utf8" }));
const originalFetch = globalThis.fetch;
const originalUrl = process.env.ANALYTICS_API_URL;
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalUrl === undefined) delete process.env.ANALYTICS_API_URL;
  else process.env.ANALYTICS_API_URL = originalUrl;
});
function endpoint(body: unknown, status = 200) {
  process.env.ANALYTICS_API_URL = "http://analytics:8080";
  globalThis.fetch = async () => Response.json(body, { status });
}
const action: UiAction = {
  kind: "open_incident", label: "Open", title: "VM build", description: "Evidence",
  targetId: fixture.card.incident_id, datasetId: fixture.card.dataset_id, analysisRunId: fixture.report.analysis_run_id,
};

test("UI schemas accept reports, timelines and exact evidence produced by Analytics", () => {
  ReportSchema.parse(fixture.report); IncidentSchema.parse(fixture.card);
  TimelineSchema.parse(fixture.timeline); EvidenceSchema.parse(fixture.event);
  DatasetsSchema.parse({ datasets: [{ dataset_id: "test", ingested_sources: 1, analysis_run_id: action.analysisRunId, incident_count: 1, analysis_stale: false }] });
});

test("proxy forwards the pinned snapshot, disables caching and rejects redirects", async () => {
  process.env.ANALYTICS_API_URL = "http://analytics:8080";
  globalThis.fetch = async (input, init) => {
    const url = new URL(String(input));
    assert.equal(url.pathname, `/v1/incidents/${action.targetId}`);
    assert.equal(url.searchParams.get("analysis_run_id"), action.analysisRunId);
    assert.equal(init?.cache, "no-store"); assert.equal(init?.redirect, "error");
    assert.ok(init?.signal);
    return Response.json(fixture.card);
  };
  assert.deepEqual(await analyticsGet(`incidents/${action.targetId}`, snapshotQuery(action.analysisRunId)), fixture.card);
});

test("proxy keeps a valid empty publication distinct from missing data", async () => {
  endpoint({ ...fixture.report, incidents: [] });
  const report = ReportSchema.parse(await analyticsGet("incidents", new URLSearchParams({ dataset_id: "test" })));
  assert.deepEqual(report.incidents, []);
  endpoint({ detail: "private database information" }, 404);
  await assert.rejects(analyticsGet("incidents"), (error: AnalyticsError) => error.status === 404 && !error.message.includes("private"));
});

test("proxy handles unavailable, invalid and incompatible upstream responses", async () => {
  delete process.env.ANALYTICS_API_URL;
  await assert.rejects(analyticsGet("datasets"), (error: AnalyticsError) => error.status === 503);
  for (const status of [422, 503, 500]) {
    endpoint({ detail: "password=secret" }, status);
    await assert.rejects(analyticsGet("datasets"), (error: AnalyticsError) => error.status === (status === 500 ? 502 : status) && !error.message.includes("secret"));
  }
  endpoint({ incidents: [] });
  await assert.rejects(analyticsGet("incidents"), (error: AnalyticsError) => error.status === 502);
  globalThis.fetch = async () => { throw new Error("connection to internal host failed"); };
  await assert.rejects(analyticsGet("health"), (error: AnalyticsError) => error.status === 503 && !error.message.includes("internal"));
});

test("proxy cannot target arbitrary URLs, SQL endpoints or unsupported filters", async () => {
  globalThis.fetch = async () => { assert.fail("must not fetch"); };
  for (const path of ["https://example.com", "../health", "incidents/../../health", "query", "events/bad"]) {
    await assert.rejects(analyticsGet(path), AnalyticsError);
  }
  await assert.rejects(analyticsGet("datasets", new URLSearchParams({ query: "SELECT 1" })), (error: AnalyticsError) => error.status === 422);
});

test("chat rejects malformed messages and links without complete snapshot coordinates", () => {
  for (const value of [null, { messages: "oops" }, { messages: [null] }, { messages: [{ role: "system", content: "x" }] }]) {
    assert.equal(ChatRequestSchema.safeParse(value).success, false);
  }
  ChatReplySchema.parse({ message: "See evidence", actions: [action] });
  for (const change of [{ analysisRunId: undefined }, { kind: "show_service" }, { targetId: "INC-2048" }, { datasetId: "" }]) {
    assert.equal(ChatReplySchema.safeParse({ message: "x", actions: [{ ...action, ...change }] }).success, false);
  }
});

test("chat filters nonexistent or cross-dataset evidence and verifies event links", async () => {
  endpoint(fixture.card);
  assert.deepEqual(await verifiedActions([action]), [action]);
  assert.deepEqual(await verifiedActions([{ ...action, datasetId: "other" }]), []);
  endpoint({ detail: "not found" }, 404);
  assert.deepEqual(await verifiedActions([action]), []);
  const eventAction: UiAction = { ...action, kind: "show_logs", targetId: fixture.event.event_id };
  endpoint(fixture.event);
  assert.deepEqual(await verifiedActions([eventAction]), [eventAction]);
});

test("selected context is fetched server-side and pinned across publication changes", async () => {
  endpoint(fixture.card);
  assert.deepEqual(await investigationContext({ datasetId: action.datasetId, incidentId: action.targetId, analysisRunId: action.analysisRunId }), IncidentSchema.parse(fixture.card));
  await assert.rejects(investigationContext({ datasetId: "other", incidentId: action.targetId, analysisRunId: action.analysisRunId }), AnalyticsError);
  endpoint(fixture.report);
  await assert.rejects(investigationContext({ datasetId: action.datasetId, incidentId: null, analysisRunId: "00000000-0000-4000-8000-000000000001" }), (error: AnalyticsError) => error.status === 422);
  endpoint(fixture.event);
  const context = await investigationContext({ datasetId: action.datasetId, incidentId: null,
    eventId: fixture.event.event_id, analysisRunId: action.analysisRunId });
  assert.equal((context as { event_id: string }).event_id, fixture.event.event_id);
  assert.equal("source_file" in context!, false);
  assert.equal("raw_text" in context!, false);
  await assert.rejects(investigationContext({ datasetId: action.datasetId, incidentId: null,
    eventId: "f".repeat(64), analysisRunId: action.analysisRunId }), AnalyticsError);
});
