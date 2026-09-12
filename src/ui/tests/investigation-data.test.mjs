import assert from "node:assert/strict";
import test from "node:test";
import { DEMO_INVESTIGATION as demo } from "../lib/demo-investigation.ts";

test("fixture is explicitly synthetic, sampled and insufficient for confirmed RCA", () => {
  assert.equal(demo.source.mode, "synthetic");
  assert.equal(demo.source.coverage, "sample");
  assert.equal(demo.status, "insufficient_evidence");
  assert.ok(demo.limitations.some((item) => item.includes("not an analyzed Loghub")));
});

test("all records have unique IDs, known templates, UTC time and exact source pointers", () => {
  const ids = demo.evidence.map((item) => item.id);
  assert.equal(new Set(ids).size, ids.length);
  const templates = new Set(demo.templates.map((item) => item.id));
  for (const record of demo.evidence) {
    assert.ok(templates.has(record.templateId));
    assert.ok(record.timestamp.endsWith("Z"));
    assert.ok(Date.parse(record.timestamp) >= Date.parse(demo.source.start));
    assert.ok(Date.parse(record.timestamp) < Date.parse(demo.source.end));
    assert.ok(record.source.file && record.source.line > 0);
    assert.ok(record.raw.includes(record.message));
    assert.ok(record.correlationBasis.includes(record.entity.id));
  }
});

test("all hypothesis, anomaly and next-check citations resolve to real fixture records", () => {
  const ids = new Set(demo.evidence.map((item) => item.id));
  const citations = [
    ...demo.anomalies.flatMap((item) => item.evidenceIds),
    ...demo.hypotheses.flatMap((item) => [...item.supportingEvidenceIds, ...item.contradictingEvidenceIds]),
    ...demo.nextChecks.flatMap((item) => item.evidenceIds),
  ];
  assert.ok(citations.length > 0);
  for (const id of citations) assert.ok(ids.has(id), `Unknown citation ${id}`);
});

test("the example anomaly matches the stated bounded rule without invented baseline", () => {
  const finding = demo.anomalies[0];
  const timeouts = demo.evidence.filter((item) => item.templateId === "DEMO-T-3");
  assert.equal(finding.observed, timeouts.length);
  assert.ok(timeouts.length >= 2);
  assert.equal(new Set(timeouts.map((item) => item.entity.id)).size, 1);
  const times = timeouts.map((item) => Date.parse(item.timestamp));
  assert.ok(Math.max(...times) - Math.min(...times) <= 60_000);
  assert.equal(finding.baseline, null);
  assert.equal(finding.baselineWindow, null);
});

test("ranked hypotheses and next checks express uncertainty and missing evidence", () => {
  assert.ok(demo.hypotheses.length >= 2);
  assert.equal(new Set(demo.hypotheses.map((item) => item.rank)).size, demo.hypotheses.length);
  for (const hypothesis of demo.hypotheses) {
    assert.ok(hypothesis.missingEvidence.length > 0);
    assert.ok(hypothesis.confidenceReason.length > 0);
    assert.equal(typeof hypothesis.confidence, "string");
  }
  for (const check of demo.nextChecks) assert.ok(check.expectedResult.length > 0);
});
