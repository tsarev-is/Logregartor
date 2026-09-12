import type { Investigation, LogEvidence } from "./investigation-contract";

const event = (
  id: string, seconds: string, level: LogEvidence["level"], service: string,
  templateId: string, message: string, role: LogEvidence["role"],
): LogEvidence => ({
  id,
  timestamp: `2026-09-12T14:32:${seconds}Z`,
  level, service, templateId, message, role,
  entity: { kind: "request_id", id: "req-demo-7a" },
  raw: `2026-09-12 14:32:${seconds} ${level.toUpperCase()} ${service} [req-demo-7a] ${message}`,
  fields: { request_id: "req-demo-7a", instance_id: "vm-demo-42", host: "compute-demo-01" },
  source: { file: "synthetic-openstack-demo.log", line: Number(id.split("-").at(-1)) },
  redacted: false,
  correlationBasis: "Same request_id=req-demo-7a within the selected UTC interval. Temporal order is not proof of causation.",
});

/** Synthetic UI fixture. NOT extracted from Loghub or a connected MCP server. */
export const DEMO_INVESTIGATION: Investigation = {
  id: "DEMO-OS-001",
  title: "Instance creation stalled after RPC timeouts",
  summary: "One synthetic request shows repeated RPC timeouts before instance creation fails. The initiating cause is not established.",
  status: "insufficient_evidence",
  source: {
    dataset: "OpenStack-inspired synthetic fixture",
    mode: "synthetic",
    start: "2026-09-12T14:30:00Z",
    end: "2026-09-12T14:40:00Z",
    coverage: "sample",
    queryDescription: "Bundled UI fixture: 6 events for req-demo-7a. Counts describe this fixture only; no ClickHouse query was executed.",
  },
  entities: ["req-demo-7a", "vm-demo-42", "compute-demo-01"],
  evidence: [
    event("DEMO-E-101", "01", "info", "nova-api", "DEMO-T-1", "Create instance request accepted instance=vm-demo-42", "observation"),
    event("DEMO-E-102", "02", "warn", "nova-compute", "DEMO-T-2", "RPC reply delayed instance=vm-demo-42", "possible_trigger"),
    event("DEMO-E-103", "04", "error", "nova-compute", "DEMO-T-3", "RPC timeout after 2s instance=vm-demo-42", "symptom"),
    event("DEMO-E-104", "05", "warn", "nova-compute", "DEMO-T-4", "Retrying RPC call attempt=1 instance=vm-demo-42", "observation"),
    event("DEMO-E-105", "07", "error", "nova-compute", "DEMO-T-3", "RPC timeout after 2s instance=vm-demo-42", "symptom"),
    event("DEMO-E-106", "08", "error", "nova-api", "DEMO-T-5", "Instance creation failed instance=vm-demo-42", "symptom"),
  ],
  templates: [
    { id: "DEMO-T-1", pattern: "Create instance request accepted instance=<instance_id>", variables: ["instance_id"] },
    { id: "DEMO-T-2", pattern: "RPC reply delayed instance=<instance_id>", variables: ["instance_id"] },
    { id: "DEMO-T-3", pattern: "RPC timeout after <duration> instance=<instance_id>", variables: ["duration", "instance_id"] },
    { id: "DEMO-T-4", pattern: "Retrying RPC call attempt=<attempt> instance=<instance_id>", variables: ["attempt", "instance_id"] },
    { id: "DEMO-T-5", pattern: "Instance creation failed instance=<instance_id>", variables: ["instance_id"] },
  ],
  anomalies: [{
    id: "DEMO-A-1", title: "Repeated RPC timeouts in one request", anomalyClass: "Repeated-event sequence",
    method: "Demonstration rule: at least 2 RPC timeouts for the same request within 60 seconds",
    explanation: "The fixture contains two RPC timeout events for req-demo-7a, three seconds apart, followed by a failed create operation.",
    observed: 2, baseline: null, unit: "timeout events", threshold: ">= 2 events / request / 60 seconds",
    baselineWindow: null, evidenceIds: ["DEMO-E-103", "DEMO-E-105", "DEMO-E-106"],
  }],
  hypotheses: [
    { id: "DEMO-H-1", rank: 1, title: "Delayed or unavailable RPC dependency", status: "suspected", confidence: "medium",
      confidenceReason: "Repeated timeout symptoms support an RPC-path issue; broker and network evidence are missing. Qualitative fixture assessment, not a calibrated probability.",
      reasoning: "The delayed-reply event and two timeouts are consistent with an unavailable or slow RPC dependency. These application logs cannot distinguish broker failure, network delay, or worker overload.",
      supportingEvidenceIds: ["DEMO-E-102", "DEMO-E-103", "DEMO-E-105"], contradictingEvidenceIds: [],
      missingEvidence: ["RPC broker health and logs", "Network reachability during the same interval", "Worker queue and execution time"] },
    { id: "DEMO-H-2", rank: 2, title: "Compute worker processing delay", status: "suspected", confidence: "low",
      confidenceReason: "Compatible with the symptoms but there is no worker resource or queue telemetry in this fixture.",
      reasoning: "A busy compute worker could delay replies without a broker outage. Application-side timeout events do not localize the delay.",
      supportingEvidenceIds: ["DEMO-E-102", "DEMO-E-105"], contradictingEvidenceIds: [],
      missingEvidence: ["Worker CPU and memory", "Queue depth and worker processing logs"] },
  ],
  nextChecks: [
    { id: "DEMO-N-1", title: "Inspect the RPC dependency in the same interval",
      description: "Read broker health, connection errors and network diagnostics for 14:30–14:40 UTC. Do not restart services based only on this fixture.",
      expectedResult: "Broker or connection failures would support hypothesis 1; a healthy broker alone would not rule out network or worker delay.", evidenceIds: ["DEMO-E-103", "DEMO-E-105"] },
    { id: "DEMO-N-2", title: "Check compute worker queue and processing time",
      description: "Inspect compute-demo-01 queue depth and worker processing logs for req-demo-7a.",
      expectedResult: "Elevated queue delay with otherwise healthy RPC transport would strengthen hypothesis 2.", evidenceIds: ["DEMO-E-102", "DEMO-E-106"] },
  ],
  limitations: [
    "Synthetic UI demonstration, not an analyzed Loghub dataset or a live incident.",
    "Only six fixture events are available; no normal-period baseline, broker telemetry, metrics, or topology is included.",
    "Hypothesis ranking is illustrative. The initiating root cause remains unconfirmed.",
    "Live MCP result IDs require a server-side investigation data adapter, which is not implemented in this UI slice.",
  ],
};
