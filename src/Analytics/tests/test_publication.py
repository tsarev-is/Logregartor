import asyncio
import contextlib
import io
import json
import unittest
import uuid
from unittest.mock import patch

from log_analytics.api import Application
from log_analytics.baseline import RunConfig
from log_analytics.cli import main
from log_analytics.clickhouse import ClickHouseError
from log_analytics.runner import run, writer_lock
from log_analytics.storage import Store
from support import MemoryClient, digest, record


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.client = MemoryClient()
        self.config = RunConfig("test", 30)

    def test_repeat_returns_existing_run_without_new_writes(self):
        first = run(self.client, self.config)
        sizes = {table: len(rows) for table, rows in self.client.tables.items()}
        self.assertEqual(first, run(self.client, self.config))
        self.assertEqual(sizes, {table: len(rows) for table, rows in self.client.tables.items()})

    def test_zero_results_replace_current_and_old_run_remains_readable(self):
        first = run(self.client, self.config)
        empty = run(self.client, RunConfig("test", 100))
        app = Application(self.client)
        self.assertEqual(app.dispatch("GET", "/v1/incidents", "dataset_id=test"), (200, empty))
        card = first["incidents"][0]
        self.assertEqual(app.dispatch("GET", "/v1/incidents/" + card["incident_id"], "")[0], 404)
        self.assertEqual(app.dispatch("GET", "/v1/incidents/" + card["incident_id"],
                                     "analysis_run_id=" + first["analysis_run_id"]), (200, card))
        self.assertEqual(run(self.client, self.config), first)
        self.assertEqual(Store(self.client).current_report("test"), first)

    def test_failed_attempt_hidden_and_restart_uses_new_attempt(self):
        def fail(table, rows):
            if table == "incident_evidence_raw":
                raise ClickHouseError("disconnected")
        self.client.on_insert = fail
        with self.assertRaises(ClickHouseError):
            run(self.client, self.config)
        old_id = self.client.tables["analysis_runs"][0]["analysis_run_id"]
        self.assertEqual(self.client.current(), {})
        app = Application(self.client)
        card = self.client.tables["incidents_raw"][0]
        self.assertEqual(app.dispatch("GET", "/v1/incidents/" + card["incident_id"],
                                     "analysis_run_id=" + old_id)[0], 404)
        self.client.on_insert = None
        self.assertNotEqual(run(self.client, self.config)["analysis_run_id"], old_id)

    def test_replacement_failure_keeps_previous_publication(self):
        first = run(self.client, self.config)
        def fail(table, rows):
            if table == "analysis_runs" and rows[0]["status"] == "completed":
                raise OSError("interrupted")
        self.client.on_insert = fail
        with self.assertRaises(OSError):
            run(self.client, RunConfig("test", 100))
        self.assertEqual(Store(self.client).current_report("test"), first)

    def test_publication_change_during_read_and_before_completion(self):
        for during_read in (True, False):
            client = MemoryClient()
            def change():
                client.publications[0]["ingestion_run_id"] = str(uuid.uuid4())
            if during_read:
                client.on_read = change
            else:
                client.on_insert = lambda table, rows: change() if table == "incident_evidence_raw" else None
            with self.subTest(during_read=during_read), self.assertRaisesRegex(ValueError, "publication changed"):
                run(client, self.config)
            self.assertEqual(client.current(), {})

    def test_snapshot_does_not_follow_parser_reimport(self):
        first = run(self.client, self.config)
        store = Store(self.client)
        event_id = first["incidents"][0]["evidence_ids"][0]
        original = store.event(event_id)
        self.client.tables["log_events_raw"][-1]["raw_text"] = "new parser interpretation"
        self.client.publications[0]["ingestion_run_id"] = str(uuid.uuid4())
        self.assertEqual(store.event(event_id), original)

    def test_empty_published_source_and_missing_dataset(self):
        self.client.tables["log_events_raw"] = []
        self.assertEqual(run(self.client, self.config)["incidents"], [])
        with self.assertRaisesRegex(ValueError, "no published"):
            run(MemoryClient([]), self.config)

    def test_baseline_run_and_identity_canonicalization(self):
        client = MemoryClient([record(1, 22, source="ref"), record(2, 51), record(3, instance="unfinished")])
        config = RunConfig("test", reference_sources=(digest("ref"),), margin_seconds=5)
        result = run(client, config)
        self.assertEqual(result["threshold_seconds"], 27)
        self.assertEqual(result["completed_instances"], 2)
        self.assertEqual(result["incomplete_instances"], 1)
        self.assertEqual(result, run(client, RunConfig("test", reference_sources=(digest("ref"), digest("ref")), margin_seconds=5.0)))

    def test_bad_tail_and_duplicate_ids_never_publish(self):
        for tail in ({**record(5), "event_time": "bad"}, record(4, 51.59)):
            self.client = MemoryClient()
            self.client.tables["log_events_raw"].append(tail)
            with self.assertRaises(ValueError):
                run(self.client, self.config)
            self.assertEqual(self.client.current(), {})

    def test_local_writer_lock(self):
        with writer_lock(self.client):
            with self.assertRaisesRegex(ValueError, "another local"):
                run(self.client, self.config)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = MemoryClient()
        self.report = run(self.client, RunConfig("test", 30))
        self.app = Application(self.client)
        self.card = self.report["incidents"][0]

    def test_card_timeline_and_exact_source_snapshot(self):
        base = "/v1/incidents/" + self.card["incident_id"]
        self.assertEqual(self.app.dispatch("GET", base, ""), (200, self.card))
        status, timeline = self.app.dispatch("GET", base + "/timeline", "")
        self.assertEqual(status, 200)
        ids = {row["event_id"] for row in timeline["events"]}
        for stage in timeline["stages"]:
            self.assertLessEqual(set(stage["evidence_ids"]), ids)
        event = timeline["events"][-1]
        self.assertEqual(self.app.dispatch("GET", "/v1/events/" + event["event_id"], ""),
                         (200, {**event, "analysis_run_id": self.report["analysis_run_id"]}))

    def test_validation_missing_objects_and_read_only_methods(self):
        for path, query, expected in (("/v1/incidents", "", 422),
            ("/v1/incidents", "dataset_id=", 422),
            ("/v1/incidents", "dataset_id=unknown", 404),
            ("/v1/incidents/bad", "", 422), ("/v1/events/" + "f" * 64, "", 404),
            ("/v1/events/" + "f" * 64, "analysis_run_id=bad", 422)):
            with self.subTest(path=path, query=query):
                self.assertEqual(self.app.dispatch("GET", path, query)[0], expected)
        self.assertEqual(self.app.dispatch("POST", "/v1/incidents", "dataset_id=test")[0], 405)

    def test_database_failure_is_503(self):
        with patch.object(self.client, "rows", side_effect=ClickHouseError("database details")):
            status, body = self.app.dispatch("GET", "/v1/incidents", "dataset_id=test")
        self.assertEqual(status, 503)
        self.assertNotIn("database details", json.dumps(body))

    def test_asgi_response(self):
        messages = []
        async def send(message):
            messages.append(message)
        async def inline(function, *args):
            return function(*args)
        # Keep unit tests independent of thread-pool/socket wakeup support in sandboxes.
        with patch("log_analytics.api.asyncio.to_thread", inline):
            asyncio.run(self.app({"type": "http", "method": "GET", "path": "/v1/incidents",
                                  "query_string": b"dataset_id=test"}, None, send))
        self.assertEqual(messages[0]["status"], 200)
        self.assertEqual(json.loads(messages[1]["body"]), self.report)


class RunCliTests(unittest.TestCase):
    def test_mutually_exclusive_arguments(self):
        for args in (["--threshold-seconds", "30", "--reference-source", "a" * 64],
                     ["--reference-source", "a" * 64],
                     ["--threshold-seconds", "30", "--margin-seconds", "5"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
                main(["run", "--dataset-id", "test", *args])
            self.assertEqual(result.exception.code, 2)

    def test_run_success_and_failed_read_stdout_contract(self):
        for failure in (False, True):
            client = MemoryClient()
            if failure:
                client.tables["log_events_raw"][-1]["event_time"] = "broken"
            output, error = io.StringIO(), io.StringIO()
            with patch("log_analytics.cli.ClickHouse.from_env", return_value=client), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                status = main(["run", "--dataset-id", "test", "--threshold-seconds", "30"])
            self.assertEqual(status, 1 if failure else 0)
            if failure:
                self.assertEqual(output.getvalue(), "")
            else:
                self.assertIn("analysis_run_id", json.loads(output.getvalue()))
