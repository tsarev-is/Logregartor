export type EvidenceView = "timeline" | "logs" | "patterns";
export type InvestigationSelection = {
  view: "overview" | EvidenceView;
  evidenceId: string | null;
  templateId: string | null;
  service: string | null;
};
export type LogEvidence = {
  id: string;
  timestamp: string;
  level: "info" | "warn" | "error" | "critical";
  service: string;
  entity: { kind: string; id: string };
  templateId: string;
  message: string;
  raw: string;
  fields: Record<string, string>;
  source: { file: string; line: number };
  redacted: boolean;
  role: "observation" | "symptom" | "possible_trigger";
  correlationBasis: string;
};
export type EventTemplate = { id: string; pattern: string; variables: string[] };
export type AnomalyFinding = {
  id: string;
  title: string;
  anomalyClass: string;
  method: string;
  explanation: string;
  observed: number | null;
  baseline: number | null;
  unit: string;
  threshold: string;
  baselineWindow: { start: string; end: string } | null;
  evidenceIds: string[];
};
export type RootCauseHypothesis = {
  id: string;
  rank: number;
  title: string;
  reasoning: string;
  status: "suspected" | "supported" | "ruled_out";
  confidence: "low" | "medium" | "high" | "unknown";
  confidenceReason: string;
  supportingEvidenceIds: string[];
  contradictingEvidenceIds: string[];
  missingEvidence: string[];
};
export type NextCheck = {
  id: string;
  title: string;
  description: string;
  expectedResult: string;
  evidenceIds: string[];
};
export type Investigation = {
  id: string;
  title: string;
  summary: string;
  status: "investigating" | "insufficient_evidence" | "resolved";
  source: {
    dataset: string;
    mode: "synthetic" | "live";
    start: string;
    end: string;
    coverage: "complete" | "partial" | "sample";
    queryDescription: string;
  };
  entities: string[];
  anomalies: AnomalyFinding[];
  hypotheses: RootCauseHypothesis[];
  evidence: LogEvidence[];
  templates: EventTemplate[];
  nextChecks: NextCheck[];
  limitations: string[];
};
