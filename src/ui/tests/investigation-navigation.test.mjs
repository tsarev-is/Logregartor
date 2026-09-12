import assert from "node:assert/strict";
import test from "node:test";
import { DEMO_INVESTIGATION as demo } from "../lib/demo-investigation.ts";
import { resolveInvestigationAction } from "../lib/investigation-navigation.ts";

const action = (kind, targetId) => ({ kind, targetId, title: "Test", label: "Open", description: "Test reference" });
const blank = { evidenceId: null, templateId: null, service: null };

test("an exact incident target opens the overview", () => {
  assert.deepEqual(resolveInvestigationAction(action("open_incident", demo.id), demo), { ...blank, view: "overview" });
});

test("incident timeline/log actions resolve to the requested presentation", () => {
  assert.deepEqual(resolveInvestigationAction(action("show_timeline", demo.id), demo), { ...blank, view: "timeline" });
  assert.deepEqual(resolveInvestigationAction(action("show_logs", demo.id), demo), { ...blank, view: "logs" });
});

test("evidence targets preserve the exact selected ID", () => {
  const id = demo.evidence[2].id;
  for (const [kind, view] of [["show_logs", "logs"], ["show_timeline", "timeline"]]) {
    const selection = resolveInvestigationAction(action(kind, id), demo);
    assert.equal(selection.view, view);
    assert.equal(selection.evidenceId, id);
  }
});

test("template targets open only the matching group", () => {
  const id = demo.templates[2].id;
  const selection = resolveInvestigationAction(action("show_logs", id), demo);
  assert.equal(selection.view, "logs");
  assert.equal(selection.templateId, id);
});

test("known services resolve to a filtered evidence view", () => {
  const selection = resolveInvestigationAction(action("show_service", "nova-compute"), demo);
  assert.equal(selection.view, "logs");
  assert.equal(selection.service, "nova-compute");
});

test("unknown, approximate and wrong-kind IDs do not silently fall back", () => {
  for (const [kind, id] of [
    ["open_incident", "INC-2048"],
    ["show_logs", "DEMO-E-999"],
    ["show_logs", "demo-e-103"],
    ["show_service", "nova"],
    ["open_incident", demo.evidence[0].id],
    ["show_service", demo.id],
    ["show_timeline", demo.templates[0].id],
    ["show_logs", ""],
    ["unknown_kind", demo.id],
  ]) assert.equal(resolveInvestigationAction(action(kind, id), demo), null, `${kind}: ${id}`);
});

test("resolution is deterministic and does not mutate the investigation or action", () => {
  const input = structuredClone(demo);
  const reference = action("show_logs", demo.evidence[0].id);
  const before = JSON.stringify({ input, reference });
  const first = resolveInvestigationAction(reference, input);
  const second = resolveInvestigationAction(reference, input);
  assert.deepEqual(first, second);
  assert.equal(JSON.stringify({ input, reference }), before);
});
