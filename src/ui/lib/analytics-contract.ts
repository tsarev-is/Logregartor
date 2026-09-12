import { z } from "zod";

export const EvidenceIdSchema = z.string().regex(/^[0-9a-f]{64}$/);
export const RunIdSchema = z.string().uuid();
const count = z.number().int().nonnegative();
const seconds = z.number().nonnegative();

export const StageSchema = z.object({
  name: z.enum(["allocate", "image", "spawn", "build"]),
  found: z.boolean(),
  duration_seconds: seconds.nullable(),
  evidence_ids: z.array(EvidenceIdSchema),
});
const CompletenessSchema = z.object({
  status: z.enum(["complete", "incomplete"]),
  missing_stages: z.array(z.string()),
  undated_event_ids: z.array(EvidenceIdSchema),
  parse_issue_event_ids: z.array(EvidenceIdSchema),
});
const BaselineSchema = z.object({
  reference_sources: z.array(EvidenceIdSchema),
  margin_seconds: seconds,
  threshold_seconds: seconds,
  completed_instances: count,
  incomplete_instances: count,
  median_seconds: seconds,
  max_seconds: seconds,
}).nullable();

export const IncidentSchema = z.object({
  incident_id: EvidenceIdSchema,
  dataset_id: z.string(),
  analysis_run_id: RunIdSchema,
  source_sha256: EvidenceIdSchema,
  instance_id: z.string(),
  detector: z.string(),
  detector_version: z.string(),
  event_time: z.string().nullable(),
  observed_seconds: seconds,
  threshold_seconds: seconds,
  excess_seconds: seconds,
  evidence_ids: z.array(EvidenceIdSchema),
  baseline: BaselineSchema,
  stages: z.array(StageSchema),
  completeness: CompletenessSchema,
});
export const ReportSchema = z.object({
  schema_version: z.literal(1),
  dataset_id: z.string(),
  analysis_run_id: RunIdSchema,
  threshold_seconds: seconds,
  events_read: count,
  instances_observed: count,
  completed_instances: count,
  incomplete_instances: count,
  baseline: BaselineSchema,
  incidents: z.array(IncidentSchema),
});
export const EventSchema = z.object({
  event_id: EvidenceIdSchema,
  dataset_id: z.string(),
  source_sha256: EvidenceIdSchema,
  source_file: z.string(),
  ingestion_run_id: RunIdSchema,
  line_start: count,
  line_end: count,
  raw_text: z.string(),
  line_ending: z.string(),
  event_time: z.string().nullable(),
  component: z.string().nullable(),
  instance_id: z.string().nullable(),
  message: z.string(),
  parse_status: z.string(),
});
export const EvidenceSchema = EventSchema.extend({ analysis_run_id: RunIdSchema });
export const TimelineSchema = z.object({
  incident_id: EvidenceIdSchema,
  analysis_run_id: RunIdSchema,
  events: z.array(EventSchema),
  undated_events: z.array(EventSchema),
  stages: z.array(StageSchema),
  completeness: CompletenessSchema,
});
export const DatasetsSchema = z.object({
  datasets: z.array(z.object({
    dataset_id: z.string(),
    ingested_sources: count,
    analysis_run_id: RunIdSchema.nullable(),
    incident_count: count.nullable(),
    analysis_stale: z.boolean(),
  })),
});
export type Incident = z.infer<typeof IncidentSchema>;
export type AnalysisReport = z.infer<typeof ReportSchema>;
export type Timeline = z.infer<typeof TimelineSchema>;
export type Evidence = z.infer<typeof EvidenceSchema>;
export type Dataset = z.infer<typeof DatasetsSchema>["datasets"][number];

export function snapshotQuery(runId: string) {
  return new URLSearchParams({ analysis_run_id: RunIdSchema.parse(runId) });
}
