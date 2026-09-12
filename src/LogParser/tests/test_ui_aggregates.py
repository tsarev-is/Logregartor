"""SQL contract checks against a disposable database, never the user's logs."""

import os
import unittest
import uuid

from pipeline.artifacts import ROOT
from pipeline.storage import ClickHouse


@unittest.skipUnless(os.getenv("LOGPARSER_CLICKHOUSE_TEST") == "1", "set LOGPARSER_CLICKHOUSE_TEST=1")
class UIAggregateTests(unittest.TestCase):
    def setUp(self):
        self.client = ClickHouse.from_env()
        self.client.database = "logparser_ui_test_" + uuid.uuid4().hex
        self.client.execute(f"CREATE DATABASE `{self.client.database}`", use_database=False)
        self.addCleanup(self.client.execute, f"DROP DATABASE `{self.client.database}`", use_database=False)
        # Simulate an existing installation that already has published data.
        for statement in (ROOT / "sql/001_initial.sql").read_text().split(";"):
            if statement.strip():
                self.client.execute(statement)

    def stage(self, levels, durations, *, dataset="ui-test", undated=False):
        run = str(uuid.uuid4())
        events = []
        for index, (level, duration) in enumerate(zip(levels, durations)):
            events.append({
                "schema_version": 1, "event_id": f"{index:064x}", "dataset_id": dataset,
                "source_sha256": "a" * 64, "ingestion_run_id": run,
                "event_time": None if undated else f"2017-05-14 21:43:{index:02}.123456789",
                "component": "nova.api" if level else None, "level": level,
                "http_duration_seconds": duration, "http_status": 500 if level == "ERROR" else 200 if duration is not None else None,
                "http_response_bytes": 10 if duration is not None else None,
                "parse_status": "ok" if level else "unparsed",
                "template_status": "matched" if level else "unknown",
                "template_id": "b" * 64 if level else None, "template_version": "c" * 64,
            })
        self.client.insert("log_events_raw", events)
        marker = {"ingestion_run_id": run, "dataset_id": dataset, "source_sha256": "a" * 64,
                  "source_file": "test.log", "processing_version": "d" * 64,
                  "template_version": "c" * 64, "expected_rows": len(events), "status": "started"}
        self.client.insert("ingestion_runs", [marker])
        return marker

    def publish(self, marker):
        self.client.insert("ingestion_runs", [{**marker, "status": "completed"}])

    def rows(self, view):
        return self.client.rows(f"SELECT * FROM {view} WHERE dataset_id='ui-test'")

    def test_backfill_rates_percentiles_and_migration_repeat(self):
        self.publish(self.stage(["INFO", "INFO", "ERROR", "CRITICAL"], [0, 1, 2, 3]))
        self.publish(self.stage(["ERROR"], [100], dataset="other"))
        self.client.migrate()
        summary = self.rows("ui_dataset_summary")[0]
        self.assertEqual(summary["event_count"], 4)
        self.assertEqual(summary["error_count"], 2)
        self.assertEqual(summary["log_error_rate"], 0.5)
        self.assertEqual(summary["http_server_error_rate"], 0.25)
        self.assertEqual(summary["http_latency_sample_count"], 4)  # Zero is a sample.
        self.assertAlmostEqual(summary["http_p95_seconds"], 3)
        self.assertEqual(summary["service_count"], 1)
        self.assertEqual(summary["error_service_count"], 1)
        minute = self.rows("ui_service_metrics_1m")[0]
        self.assertEqual(minute["bucket"], "2017-05-14 21:43:00")
        self.assertEqual(minute["event_count"], 4)
        self.assertEqual(minute["critical_count"], 1)
        self.assertEqual(sum(row["request_count"] for row in self.rows("ui_http_metrics_1m")), 4)
        self.assertEqual(sum(row["response_bytes"] for row in self.rows("ui_http_metrics_1m")), 40)
        pattern = self.rows("ui_template_metrics_1m")[0]
        self.assertEqual(pattern["event_count"], 4)
        self.assertEqual(pattern["sample_event_id"], "0" * 64)
        types = self.client.rows("SELECT toTypeName(sample_event_id) AS event_type, "
                                 "toTypeName(source_sha256) AS source_type FROM ui_template_metrics_1m LIMIT 1")[0]
        self.assertEqual(types, {"event_type": "String", "source_type": "String"})
        self.assertEqual(self.rows("ui_service_summary")[0]["event_count"], 4)
        self.client.migrate()
        self.assertEqual(self.rows("ui_dataset_summary"), [summary])

    def test_unpublished_replaced_and_retried_ingestions_are_not_counted(self):
        self.publish(self.stage(["ERROR"], [2]))
        self.client.migrate()
        self.stage(["ERROR"] * 3, [9] * 3)  # Abandoned attempt.
        replacement = self.stage(["INFO", "INFO"], [0, 1])
        self.assertEqual(self.rows("ui_dataset_summary")[0]["error_count"], 1)
        self.publish(replacement)
        self.publish(replacement)  # Lost completion acknowledgement, retry marker.
        summary = self.rows("ui_dataset_summary")[0]
        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["error_count"], 0)
        self.assertEqual(self.rows("ui_service_metrics_1m")[0]["event_count"], 2)
        self.assertEqual(self.rows("ui_template_metrics_1m")[0]["event_count"], 2)

    def test_missing_measurements_and_undated_records(self):
        self.publish(self.stage([None], [None], undated=True))
        self.client.migrate()
        summary = self.rows("ui_dataset_summary")[0]
        self.assertEqual(summary["event_count"], 1)
        self.assertEqual(summary["undated_event_count"], 1)
        self.assertEqual(summary["unknown_template_count"], 1)
        self.assertEqual(summary["service_count"], 0)
        for key in ("first_event_time", "last_event_time", "log_error_rate", "http_server_error_rate", "http_p95_seconds"):
            self.assertIsNone(summary[key], key)
        for view in ("ui_service_summary", "ui_service_metrics_1m", "ui_http_metrics_1m", "ui_template_metrics_1m"):
            self.assertEqual(self.rows(view), [])

    def test_empty_database_and_no_http_samples(self):
        self.client.migrate()
        self.assertEqual(self.rows("ui_dataset_summary"), [])
        self.publish(self.stage(["INFO"], [None]))
        self.assertIsNone(self.rows("ui_service_summary")[0]["http_p95_seconds"])
        self.assertIsNone(self.rows("ui_service_metrics_1m")[0]["http_p95_seconds"])
        self.assertEqual(self.rows("ui_http_metrics_1m"), [])
