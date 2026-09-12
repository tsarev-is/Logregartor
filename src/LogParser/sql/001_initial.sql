CREATE TABLE IF NOT EXISTS log_events_raw
(
    schema_version UInt16,
    parser_version LowCardinality(String),
    event_id FixedString(64),
    dataset_id String,
    source_file String,
    source_sha256 FixedString(64),
    line_start UInt64,
    line_end UInt64,
    raw_text String,
    line_ending String,
    timestamp_raw Nullable(String),
    event_time Nullable(DateTime64(9, 'UTC')),
    timezone_assumption LowCardinality(String),
    source_name Nullable(String),
    pid Nullable(UInt64),
    level LowCardinality(Nullable(String)),
    component LowCardinality(Nullable(String)),
    context_raw Nullable(String),
    message String,
    request_id Nullable(String),
    instance_id Nullable(String),
    host Nullable(String),
    http_method LowCardinality(Nullable(String)),
    http_url Nullable(String),
    http_status Nullable(UInt16),
    http_duration_seconds Nullable(Float64),
    http_response_bytes Nullable(UInt64),
    build_duration_seconds Nullable(Float64),
    spawn_duration_seconds Nullable(Float64),
    destroy_duration_seconds Nullable(Float64),
    parameters Map(String, Float64),
    parse_status LowCardinality(String),
    parse_errors Array(String),
    template_id Nullable(String),
    template_version Nullable(String),
    template_status LowCardinality(String),
    ingestion_run_id UUID
)
ENGINE = MergeTree
ORDER BY (dataset_id, source_sha256, ifNull(instance_id, ''),
          ifNull(event_time, toDateTime64('1970-01-01 00:00:00', 9, 'UTC')),
          event_id, ingestion_run_id);

CREATE TABLE IF NOT EXISTS event_templates_raw
(
    ingestion_run_id UUID,
    template_id FixedString(64),
    template_version FixedString(64),
    template_text String
)
ENGINE = MergeTree
ORDER BY (ingestion_run_id, template_version, template_id);

CREATE TABLE IF NOT EXISTS ingestion_runs
(
    ingestion_run_id UUID,
    dataset_id String,
    source_sha256 FixedString(64),
    source_file String,
    processing_version FixedString(64),
    template_version FixedString(64),
    expected_rows UInt64,
    status Enum8('started' = 1, 'completed' = 2),
    recorded_at DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = MergeTree
ORDER BY (dataset_id, source_sha256, ingestion_run_id, status);

CREATE VIEW IF NOT EXISTS current_ingestions AS
SELECT dataset_id, source_sha256,
       argMax(r.ingestion_run_id, tuple(r.recorded_at, toString(r.ingestion_run_id))) AS ingestion_run_id,
       argMax(r.processing_version, tuple(r.recorded_at, toString(r.ingestion_run_id))) AS processing_version
FROM ingestion_runs AS r
WHERE status = 'completed'
GROUP BY dataset_id, source_sha256;

CREATE VIEW IF NOT EXISTS log_events AS
SELECT * FROM log_events_raw
WHERE ingestion_run_id IN (SELECT ingestion_run_id FROM current_ingestions);

CREATE VIEW IF NOT EXISTS event_templates AS
SELECT DISTINCT template_id, template_version, template_text
FROM event_templates_raw
WHERE ingestion_run_id IN (SELECT ingestion_run_id FROM current_ingestions);
