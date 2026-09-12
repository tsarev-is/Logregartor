import { analyticsGet, AnalyticsError } from "./analytics-client.ts";
import { EvidenceSchema, IncidentSchema, ReportSchema, snapshotQuery } from "./analytics-contract.ts";
import type { ChatRequest, UiAction } from "./chat-contract.ts";

export async function investigationContext(context: ChatRequest["context"]) {
  if (!context) return null;
  if (context.eventId) {
    if (!context.analysisRunId) throw new AnalyticsError(422, "Evidence context requires an analysis run.");
    const event = EvidenceSchema.parse(await analyticsGet(`events/${context.eventId}`, snapshotQuery(context.analysisRunId)));
    if (event.event_id !== context.eventId || event.dataset_id !== context.datasetId || event.analysis_run_id !== context.analysisRunId) {
      throw new AnalyticsError(422, "Evidence context does not belong to this dataset and run.");
    }
    // Source filenames can contain evaluation labels; original text stays in the evidence viewer.
    return {
      dataset_id: event.dataset_id, analysis_run_id: event.analysis_run_id, event_id: event.event_id,
      source_sha256: event.source_sha256, instance_id: event.instance_id, event_time: event.event_time,
      component: event.component, parse_status: event.parse_status,
    };
  }
  if (context.incidentId) {
    if (!context.analysisRunId) throw new AnalyticsError(422, "Incident context requires an analysis run.");
    const card = IncidentSchema.parse(await analyticsGet(
      `incidents/${context.incidentId}`, snapshotQuery(context.analysisRunId),
    ));
    if (card.incident_id !== context.incidentId || card.dataset_id !== context.datasetId || card.analysis_run_id !== context.analysisRunId) {
      throw new AnalyticsError(422, "Incident context does not belong to this dataset and run.");
    }
    return card;
  }
  const report = ReportSchema.parse(await analyticsGet("incidents", new URLSearchParams({ dataset_id: context.datasetId })));
  if (report.dataset_id !== context.datasetId) throw new AnalyticsError(422, "Unexpected dataset in investigation context.");
  if (context.analysisRunId && report.analysis_run_id !== context.analysisRunId) {
    throw new AnalyticsError(422, "The dataset publication changed. Refresh the incident list before investigating.");
  }
  return report;
}

export async function verifiedActions(actions: UiAction[]): Promise<UiAction[]> {
  const results = await Promise.all(actions.map(async (action) => {
    try {
      const path = action.kind === "show_logs" ? `events/${action.targetId}` : `incidents/${action.targetId}`;
      const record = await analyticsGet(path, snapshotQuery(action.analysisRunId)) as {
        dataset_id: string; analysis_run_id: string; event_id?: string; incident_id?: string;
      };
      const id = action.kind === "show_logs" ? record.event_id : record.incident_id;
      return id === action.targetId && record.dataset_id === action.datasetId &&
        record.analysis_run_id === action.analysisRunId ? action : null;
    } catch {
      return null;
    }
  }));
  return results.filter((action): action is UiAction => action !== null);
}
