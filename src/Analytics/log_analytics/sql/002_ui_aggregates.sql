-- These projections retain the completed analysis snapshot even after reimport.
CREATE OR REPLACE VIEW ui_incident_details AS
SELECT analysis_run_id, dataset_id, toString(incident_id) AS incident_id,
       toString(source_sha256) AS source_sha256, instance_id,
       JSONExtractString(card_json, 'detector') AS detector,
       parseDateTime64BestEffortOrNull(JSONExtractString(card_json, 'event_time'), 9, 'UTC') AS event_time,
       JSONExtractFloat(card_json, 'observed_seconds') AS observed_seconds,
       JSONExtractFloat(card_json, 'threshold_seconds') AS threshold_seconds,
       excess_seconds,
       JSONExtractString(card_json, 'completeness', 'status') AS completeness_status,
       JSONExtract(card_json, 'evidence_ids', 'Array(String)') AS evidence_ids
FROM incidents;

CREATE OR REPLACE VIEW ui_incident_evidence_summary AS
SELECT analysis_run_id, dataset_id, toString(incident_id) AS incident_id,
       count() AS evidence_count,
       countIf(event_time IS NULL) AS undated_evidence_count,
       min(event_time) AS first_event_time,
       max(event_time) AS last_event_time,
       uniqExactIf(service, service != '') AS affected_service_count,
       arraySort(groupUniqArrayIf(service, service != '')) AS affected_services
FROM
(
    SELECT analysis_run_id, dataset_id, incident_id,
           JSONExtractString(event_json, 'component') AS service,
           parseDateTime64BestEffortOrNull(JSONExtractString(event_json, 'event_time'), 9, 'UTC') AS event_time
    FROM incident_evidence
)
GROUP BY analysis_run_id, dataset_id, incident_id;

CREATE OR REPLACE VIEW ui_incident_metrics_1m AS
SELECT analysis_run_id, dataset_id, toStartOfMinute(event_time) AS bucket, detector,
       count() AS anomaly_count,
       uniqExact(tuple(source_sha256, instance_id)) AS affected_instance_count,
       max(excess_seconds) AS max_excess_seconds
FROM ui_incident_details
WHERE event_time IS NOT NULL
GROUP BY analysis_run_id, dataset_id, bucket, detector;

-- One row even for a completed run with zero incidents. No row means no analysis.
CREATE OR REPLACE VIEW ui_analysis_summary AS
SELECT analysis_run_id, dataset_id, toString(analysis_version) AS analysis_version,
       JSONExtractString(report_json, 'detector') AS detector,
       JSONExtractFloat(report_json, 'threshold_seconds') AS threshold_seconds,
       JSONExtractUInt(report_json, 'events_read') AS events_read,
       JSONExtractUInt(report_json, 'instances_observed') AS instances_observed,
       JSONExtractUInt(report_json, 'completed_instances') AS completed_instances,
       JSONExtractUInt(report_json, 'incomplete_instances') AS incomplete_instances,
       length(JSONExtractArrayRaw(report_json, 'incidents')) AS anomaly_count
FROM current_analysis_runs;
