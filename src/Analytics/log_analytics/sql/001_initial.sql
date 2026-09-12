CREATE TABLE IF NOT EXISTS analysis_runs
(
    analysis_run_id UUID,
    dataset_id String,
    analysis_version FixedString(64),
    input_snapshot_json String,
    configuration_json String,
    report_json String,
    status Enum8('started' = 1, 'completed' = 2),
    recorded_at DateTime64(9, 'UTC') DEFAULT now64(9)
)
ENGINE = MergeTree
ORDER BY (dataset_id, analysis_version, analysis_run_id, status);

CREATE TABLE IF NOT EXISTS incidents_raw
(
    analysis_run_id UUID,
    dataset_id String,
    incident_id FixedString(64),
    source_sha256 FixedString(64),
    instance_id String,
    excess_seconds Float64,
    card_json String,
    timeline_json String
)
ENGINE = MergeTree
ORDER BY (dataset_id, analysis_run_id, incident_id);

CREATE TABLE IF NOT EXISTS incident_evidence_raw
(
    analysis_run_id UUID,
    dataset_id String,
    incident_id FixedString(64),
    event_id FixedString(64),
    ingestion_run_id UUID,
    event_json String
)
ENGINE = MergeTree
ORDER BY (dataset_id, analysis_run_id, incident_id, event_id);

CREATE VIEW IF NOT EXISTS current_analysis_runs AS
SELECT r.dataset_id,
       argMax(r.analysis_run_id, tuple(r.recorded_at, toString(r.analysis_run_id))) AS analysis_run_id,
       argMax(r.analysis_version, tuple(r.recorded_at, toString(r.analysis_run_id))) AS analysis_version,
       argMax(r.report_json, tuple(r.recorded_at, toString(r.analysis_run_id))) AS report_json
FROM analysis_runs AS r
WHERE r.status = 'completed'
GROUP BY dataset_id;

CREATE VIEW IF NOT EXISTS incidents AS
SELECT * FROM incidents_raw
WHERE analysis_run_id IN (SELECT analysis_run_id FROM current_analysis_runs);

CREATE VIEW IF NOT EXISTS incident_evidence AS
SELECT * FROM incident_evidence_raw
WHERE analysis_run_id IN (SELECT analysis_run_id FROM current_analysis_runs);
