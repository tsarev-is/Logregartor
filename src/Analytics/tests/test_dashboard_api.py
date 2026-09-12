import unittest
from unittest.mock import Mock

from log_analytics.api import Application
from log_analytics.baseline import RunConfig
from log_analytics.clickhouse import ClickHouseError
from log_analytics.runner import run
from support import MemoryClient


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.memory = MemoryClient()
        self.report = run(self.memory, RunConfig("test", 30))
        self.reports = list(self.memory.current().values())
        self.inputs = [{"dataset_id": "test", **row} for row in self.memory.publications]
        self.parser_present = True
        self.client = Mock()
        self.client.rows.side_effect = self.rows
        self.app = Application(self.client)

    def rows(self, sql, params=None):
        if "FROM system.tables" in sql:
            return [{"name": "current_ingestions"}] if self.parser_present else []
        if "FROM current_ingestions" in sql:
            return self.inputs
        if "FROM current_analysis_runs" in sql:
            return self.reports
        raise AssertionError(sql)

    def test_discovery_distinguishes_unanalyzed_and_empty_publications(self):
        self.inputs.append({**self.inputs[0], "dataset_id": "pending"})
        status, result = self.app.dispatch("GET", "/v1/datasets", "")
        self.assertEqual(status, 200)
        pending, analyzed = result["datasets"]
        self.assertEqual(pending, {"dataset_id": "pending", "ingested_sources": 1,
                                  "analysis_run_id": None, "incident_count": None, "analysis_stale": False})
        self.assertEqual(analyzed["analysis_run_id"], self.report["analysis_run_id"])
        self.assertEqual(analyzed["incident_count"], 1)
        self.assertFalse(analyzed["analysis_stale"])
        empty = run(self.memory, RunConfig("test", 100))
        self.reports = list(self.memory.current().values())
        datasets = self.app.dispatch("GET", "/v1/datasets", "")[1]["datasets"]
        self.assertEqual(datasets[-1]["incident_count"], 0)
        self.assertEqual(datasets[-1]["analysis_run_id"], empty["analysis_run_id"])

    def test_changed_ingestion_marks_analysis_stale_without_replacing_snapshot(self):
        self.inputs[0]["ingestion_run_id"] = "00000000-0000-4000-8000-000000000001"
        result = self.app.dispatch("GET", "/v1/datasets", "")[1]["datasets"][0]
        self.assertTrue(result["analysis_stale"])
        self.assertEqual(result["analysis_run_id"], self.report["analysis_run_id"])

    def test_fresh_install_without_logparser_schema_is_empty(self):
        self.parser_present = False
        self.reports = []
        self.assertEqual(self.app.dispatch("GET", "/v1/datasets", ""), (200, {"datasets": []}))
        self.assertEqual(self.app.dispatch("GET", "/health", ""), (200, {"status": "ok"}))

    def test_health_and_discovery_report_database_failure(self):
        self.client.rows.side_effect = ClickHouseError("private details")
        for path in ["/health", "/v1/datasets"]:
            status, result = self.app.dispatch("GET", path, "")
            self.assertEqual(status, 503)
            self.assertNotIn("private details", str(result))
            self.assertEqual(self.app.dispatch("POST", path, "")[0], 405)
