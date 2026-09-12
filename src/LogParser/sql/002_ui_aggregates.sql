-- Aggregate views read only the current completed ingestions. They also cover
-- existing data and switch versions without counting abandoned/replaced rows.
CREATE OR REPLACE VIEW ui_dataset_summary AS
SELECT dataset_id,
       count() AS event_count,
       uniqExact(source_sha256) AS source_count,
       min(event_time) AS first_event_time,
       max(event_time) AS last_event_time,
       countIf(event_time IS NULL) AS undated_event_count,
       countIf(parse_status NOT IN ('ok', 'empty')) AS parse_issue_count,
       countIf(level IS NOT NULL) AS leveled_event_count,
       countIf(level IN ('ERROR', 'CRITICAL', 'FATAL')) AS error_count,
       error_count / nullIf(leveled_event_count, 0) AS log_error_rate,
       uniqExactIf(component, ifNull(component, '') != '') AS service_count,
       uniqExactIf(component, ifNull(component, '') != '' AND level IN ('ERROR', 'CRITICAL', 'FATAL')) AS error_service_count,
       uniqExact(tuple(source_sha256, instance_id)) FILTER (WHERE instance_id IS NOT NULL) AS instance_count,
       uniqExact(tuple(template_version, template_id)) FILTER (WHERE template_id IS NOT NULL) AS template_count,
       countIf(template_status = 'unknown') AS unknown_template_count,
       countIf(http_status IS NOT NULL) AS http_request_count,
       countIf(http_status >= 500) AS http_server_error_count,
       http_server_error_count / nullIf(http_request_count, 0) AS http_server_error_rate,
       countIf(http_duration_seconds IS NOT NULL) AS http_latency_sample_count,
       quantileTDigestOrNullIf(0.95)(assumeNotNull(http_duration_seconds), http_duration_seconds IS NOT NULL) AS http_p95_seconds
FROM log_events
GROUP BY dataset_id;

-- A service is an observed OpenStack component, not an inferred topology node.
CREATE OR REPLACE VIEW ui_service_summary AS
SELECT dataset_id, component AS service,
       count() AS event_count,
       min(event_time) AS first_event_time,
       max(event_time) AS last_event_time,
       countIf(level IS NOT NULL) AS leveled_event_count,
       countIf(level IN ('ERROR', 'CRITICAL', 'FATAL')) AS error_count,
       error_count / nullIf(leveled_event_count, 0) AS log_error_rate,
       countIf(http_duration_seconds IS NOT NULL) AS http_latency_sample_count,
       quantileTDigestOrNullIf(0.95)(assumeNotNull(http_duration_seconds), http_duration_seconds IS NOT NULL) AS http_p95_seconds
FROM log_events
WHERE ifNull(component, '') != ''
GROUP BY dataset_id, component;

CREATE OR REPLACE VIEW ui_service_metrics_1m AS
SELECT dataset_id, toString(source_sha256) AS source_sha256, toStartOfMinute(event_time) AS bucket,
       component AS service,
       count() AS event_count,
       countIf(level IS NOT NULL) AS leveled_event_count,
       countIf(level IN ('ERROR', 'CRITICAL', 'FATAL')) AS error_count,
       countIf(level IN ('WARN', 'WARNING')) AS warning_count,
       countIf(level IN ('CRITICAL', 'FATAL')) AS critical_count,
       error_count / nullIf(leveled_event_count, 0) AS log_error_rate,
       countIf(template_status = 'unknown') AS unknown_template_count,
       countIf(http_duration_seconds IS NOT NULL) AS http_latency_sample_count,
       quantileTDigestOrNullIf(0.95)(assumeNotNull(http_duration_seconds), http_duration_seconds IS NOT NULL) AS http_p95_seconds
FROM log_events
WHERE event_time IS NOT NULL
GROUP BY dataset_id, source_sha256, bucket, component;

CREATE OR REPLACE VIEW ui_http_metrics_1m AS
SELECT dataset_id, toString(source_sha256) AS source_sha256, toStartOfMinute(event_time) AS bucket,
       component AS service, http_method, http_status,
       count() AS request_count,
       countIf(http_status >= 400 AND http_status < 500) AS client_error_count,
       countIf(http_status >= 500) AS server_error_count,
       countIf(http_duration_seconds IS NOT NULL) AS latency_sample_count,
       quantileTDigestOrNullIf(0.95)(assumeNotNull(http_duration_seconds), http_duration_seconds IS NOT NULL) AS p95_seconds,
       sumOrNull(http_response_bytes) AS response_bytes
FROM log_events
WHERE event_time IS NOT NULL AND http_status IS NOT NULL
GROUP BY dataset_id, source_sha256, bucket, component, http_method, http_status;

CREATE OR REPLACE VIEW ui_template_metrics_1m AS
SELECT dataset_id, toString(source_sha256) AS source_sha256, toStartOfMinute(event_time) AS bucket,
       component AS service, template_version, template_id, template_status,
       count() AS event_count,
       countIf(level IN ('ERROR', 'CRITICAL', 'FATAL')) AS error_count,
       min(event_time) AS first_event_time,
       max(event_time) AS last_event_time,
       min(toString(event_id)) AS sample_event_id
FROM log_events
WHERE event_time IS NOT NULL
GROUP BY dataset_id, source_sha256, bucket, component, template_version, template_id, template_status;
