import copy
import tempfile
import unittest
from pathlib import Path

from pipeline.storage import ClickHouse, load, writer_lock
from tests.support import enriched


class MemoryClickHouse:
    def __init__(self):
        self.url = "http://localhost:8123"
        self.database = "memory_test"
        self.tables = {name: [] for name in ("log_events_raw", "event_templates_raw", "ingestion_runs")}
        self.failure = None

    def migrate(self):
        pass

    def insert(self, table, rows):
        self.tables[table].extend(copy.deepcopy(rows))
        if rows and self.failure == table:
            self.failure = None
            raise OSError("simulated lost response after server accepted insert")

    def current(self):
        result = {}
        for row in self.tables["ingestion_runs"]:
            if row["status"] == "completed":
                result[row["dataset_id"], row["source_sha256"]] = row
        return result

    def visible(self):
        active = {r["ingestion_run_id"] for r in self.current().values()}
        return [r for r in self.tables["log_events_raw"] if r["ingestion_run_id"] in active]

    def rows(self, sql, params=None):
        if "FROM current_ingestions" in sql:
            row = self.current().get((params["dataset"], params["source"]))
            return [row] if row else []
        if "FROM log_events_raw" in sql:
            rows = [r for r in self.tables["log_events_raw"] if r["ingestion_run_id"] == params["run"]]
            return [{"rows": len(rows), "ids": len({r["event_id"] for r in rows})}]
        if "FROM event_templates_raw" in sql:
            rows = [r for r in self.tables["event_templates_raw"] if r["ingestion_run_id"] == params["run"]]
            return [{"ids": len({r["template_id"] for r in rows})}]
        raise AssertionError(sql)


class StorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.artifacts = enriched(Path(temporary.name))
        self.client = MemoryClickHouse()

    def test_repeat_import_is_skipped(self):
        first = load(*self.artifacts, self.client, batch_size=1)
        second = load(*self.artifacts, self.client, batch_size=1)
        self.assertEqual(len(self.client.visible()), 2)
        self.assertEqual(len(self.client.tables["log_events_raw"]), 2)
        self.assertEqual(second["files"][0]["status"], "skipped")
        self.assertEqual(first["files"][0]["ingestion_run_id"], second["files"][0]["ingestion_run_id"])

    def test_lost_insert_response_and_restart(self):
        self.client.failure = "log_events_raw"
        with self.assertRaises(OSError):
            load(*self.artifacts, self.client, batch_size=1)
        self.assertEqual(self.client.visible(), [])
        self.assertEqual(len(self.client.tables["log_events_raw"]), 1)
        load(*self.artifacts, self.client, batch_size=1)
        self.assertEqual(len(self.client.visible()), 2)
        self.assertEqual(len({r["event_id"] for r in self.client.visible()}), 2)

    def test_local_writer_lock_rejects_overlap(self):
        with writer_lock(self.client):
            with self.assertRaisesRegex(ValueError, "another local importer"):
                with writer_lock(self.client):
                    self.fail("second writer acquired lock")

    def test_invalid_clickhouse_configuration(self):
        for url, database in (("http://user:secret@localhost", "logs"), ("file:///tmp/db", "logs"),
                              ("http://localhost:8123?x=1", "logs"), ("http://localhost", "logs;DROP TABLE x")):
            with self.assertRaises(ValueError):
                ClickHouse(url, database, "u", "p")


if __name__ == "__main__":
    unittest.main()
