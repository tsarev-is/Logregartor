import assert from "node:assert/strict";
import test from "node:test";
import { isLiveLogsPage } from "../lib/logs-contract.ts";
import { isServiceSummaryList } from "../lib/services-contract.ts";

const service = {
  datasetId: "openstack",
  service: "nova.compute.manager",
  eventCount: 10,
  errorCount: 0,
  logErrorRate: 0,
  firstEventTimeMs: 1,
  lastEventTimeMs: 2,
  httpLatencySampleCount: 0,
  httpP95Seconds: null,
};

test("service summaries reject missing rates and accept a null HTTP percentile", () => {
  assert.equal(isServiceSummaryList([service]), true);
  assert.equal(isServiceSummaryList([{ ...service, logErrorRate: null, httpP95Seconds: 0.12 }]), true);
  assert.equal(isServiceSummaryList([{ ...service, service: "" }]), true);
  assert.equal(isServiceSummaryList([{ ...service, eventCount: "10" }]), false);
  assert.equal(isServiceSummaryList({ services: [service] }), false);
});

test("live log pages require a service facet before the explorer can render filters", () => {
  const page = {
    dataset: "openstack",
    total: 1,
    limit: 50,
    offset: 0,
    events: [{ eventId: "e", message: "m", rawText: "r", sourceFile: "f", lineStart: 1 }],
    facets: { levels: ["INFO"], sources: ["openstack_normal1.log"], components: ["nova.compute.manager"] },
  };
  assert.equal(isLiveLogsPage(page), true);
  const { components, ...facets } = page.facets;
  assert.equal(isLiveLogsPage({ ...page, facets }), false);
  assert.equal(components.includes("nova.compute.manager"), true);
});
