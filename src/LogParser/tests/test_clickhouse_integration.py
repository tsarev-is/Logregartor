"""Opt in with LOGPARSER_CLICKHOUSE_TEST=1; uses only a unique temporary database."""

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from pipeline.artifacts import ROOT, load_json, write_json
from pipeline.storage import ClickHouse, load
from pipeline.templates import fit, transform
from tests.support import HEADER, INSTANCE, NORMAL, enriched


class FaultClient:
    def __init__(self, client, table, after=True, status=None):
        self.client, self.table, self.after, self.status = client, table, after, status
        self.armed = True
        self.url, self.database = client.url, client.database

    def __getattr__(self, name):
        return getattr(self.client, name)

    def insert(self, table, rows):
        fail = self.armed and table == self.table and rows and (self.status is None or rows[0].get("status") == self.status)
        if fail and not self.after:
            self.armed = False
            raise OSError("simulated interruption before publication")
        result = self.client.insert(table, rows)
        if fail:
            self.armed = False
            raise OSError("simulated lost response after accepted INSERT")
        return result


@unittest.skipUnless(os.getenv("LOGPARSER_CLICKHOUSE_TEST") == "1", "set LOGPARSER_CLICKHOUSE_TEST=1 for local ClickHouse")
class ClickHouseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = ClickHouse.from_env()
        cls.client.database = "logparser_test_" + uuid.uuid4().hex
        cls.client.migrate()

    @classmethod
    def tearDownClass(cls):
        cls.client.execute(f"DROP DATABASE `{cls.client.database}`", use_database=False)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)
        self.dataset = "test_" + uuid.uuid4().hex
        self.artifacts = enriched(self.path, dataset=self.dataset)

    def visible(self):
        return self.client.rows("SELECT event_id, ingestion_run_id, raw_text, line_ending, "
                                "build_duration_seconds, event_time FROM log_events "
                                "WHERE dataset_id={dataset:String} ORDER BY line_start", {"dataset": self.dataset})

    def test_repeat_and_exact_evidence(self):
        first = load(*self.artifacts, self.client, batch_size=1)
        visible = self.visible()
        self.assertEqual(len(visible), 2)
        self.assertEqual("".join(r["raw_text"] + r["line_ending"] for r in visible), NORMAL)
        self.assertEqual(visible[0]["build_duration_seconds"], 19.05)
        self.assertTrue(visible[0]["event_time"].startswith("2017-05-14 21:43:33.901"))
        second = load(*self.artifacts, self.client, batch_size=1)
        self.assertEqual(first["files"][0]["ingestion_run_id"], second["files"][0]["ingestion_run_id"])
        self.assertEqual(second["files"][0]["status"], "skipped")
        self.assertEqual(visible, self.visible())

    def test_partial_insert_hidden_and_restart(self):
        with self.assertRaises(OSError):
            load(*self.artifacts, FaultClient(self.client, "log_events_raw"), batch_size=1)
        self.assertEqual(self.visible(), [])
        load(*self.artifacts, self.client, batch_size=1)
        self.assertEqual(len(self.visible()), 2)
        counts = self.client.rows("SELECT count() AS n FROM log_events_raw WHERE dataset_id={dataset:String}", {"dataset": self.dataset})
        self.assertEqual(int(counts[0]["n"]), 3)

    def test_interruption_before_publication(self):
        with self.assertRaises(OSError):
            load(*self.artifacts, FaultClient(self.client, "ingestion_runs", after=False, status="completed"))
        self.assertEqual(self.visible(), [])
        load(*self.artifacts, self.client)
        self.assertEqual(len(self.visible()), 2)

    def test_lost_publication_ack_is_skipped_on_restart(self):
        with self.assertRaises(OSError):
            load(*self.artifacts, FaultClient(self.client, "ingestion_runs", status="completed"))
        visible = self.visible()
        self.assertEqual(len(visible), 2)
        result = load(*self.artifacts, self.client)
        self.assertEqual(result["files"][0]["status"], "skipped")
        self.assertEqual(visible, self.visible())

    def test_replacement_keeps_previous_version_until_complete(self):
        load(*self.artifacts, self.client)
        previous = self.visible()
        config = load_json(ROOT / "config/drain.json"); config["sim_th"] = 0.6
        write_json(self.path / "config.json", config)
        state = self.path / "state2"
        source = self.path / "source.jsonl"; report = self.path / "source.jsonl.report.json"
        fit(source, report, state, self.path / "config.json")
        out, metadata = self.path / "out2", self.path / "report2"
        transform(source, report, out, metadata, state)
        with self.assertRaises(OSError):
            load(out, metadata, state, FaultClient(self.client, "log_events_raw"), batch_size=1)
        self.assertEqual(previous, self.visible())
        load(out, metadata, state, self.client, batch_size=1)
        current = self.visible()
        self.assertEqual([r["event_id"] for r in previous], [r["event_id"] for r in current])
        self.assertNotEqual(previous[0]["ingestion_run_id"], current[0]["ingestion_run_id"])

    def test_empty_and_malformed_input_can_be_published(self):
        second = self.path / "empty"; second.mkdir()
        artifacts = enriched(second, content="", dataset=self.dataset + "_empty")
        result = load(*artifacts, self.client)
        self.assertEqual(result["files"][0]["physical_lines"], 0)
        third = self.path / "malformed"; third.mkdir()
        artifacts = enriched(third, content=f"broken\n\n{HEADER}\n", dataset=self.dataset + "_malformed")
        load(*artifacts, self.client)
        rows = self.client.rows("SELECT parse_status, event_time FROM log_events WHERE dataset_id={dataset:String} ORDER BY line_start",
                                {"dataset": self.dataset + "_malformed"})
        self.assertEqual([r["parse_status"] for r in rows], ["unparsed", "empty", "ok"])
        self.assertIsNone(rows[0]["event_time"])


if __name__ == "__main__":
    unittest.main()
