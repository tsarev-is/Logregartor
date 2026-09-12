"""Opt-in end-to-end tests. Only a unique temporary ClickHouse database is changed."""

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from log_analytics.api import Application
from log_analytics.baseline import RunConfig
from log_analytics.clickhouse import ClickHouse
from log_analytics.config import DetectorConfig
from log_analytics.detectors.build_duration import detect
from log_analytics.runner import run
from log_analytics.storage import Store

PARSER = Path(__file__).resolve().parents[2] / "LogParser"
ANALYTICS = Path(__file__).resolve().parents[1]
INSTANCE = "a445709b-6ad0-40ec-8860-bec60b6ca0c2"


class FaultClient:
    def __init__(self, client, table, *, after=False, completed=False):
        self.client, self.table, self.after, self.completed = client, table, after, completed
        self.armed = True

    def __getattr__(self, name):
        return getattr(self.client, name)

    def insert(self, table, rows):
        fail = self.armed and table == self.table and rows and (not self.completed or rows[0]["status"] == "completed")
        if fail:
            self.armed = False
            if self.after:
                self.client.insert(table, rows)
            raise OSError("simulated interruption")
        self.client.insert(table, rows)


@unittest.skipUnless(os.getenv("ANALYTICS_CLICKHOUSE_TEST") == "1", "set ANALYTICS_CLICKHOUSE_TEST=1")
class ClickHouseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="analytics-integration-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.path = Path(cls.temp.name)
        cls.client = ClickHouse.from_env()
        cls.client.database = "analytics_test_" + uuid.uuid4().hex
        cls.addClassCleanup(cls.client.execute, f"DROP DATABASE `{cls.client.database}`", use_database=False)
        cls.client.migrate()
        cls.binary = os.getenv("LOGPARSER_BINARY", str(cls.path / "logparser"))
        if not os.getenv("LOGPARSER_BINARY"):
            env = {**os.environ, "GOCACHE": str(cls.path / "go-cache")}
            subprocess.run(["go", "build", "-o", cls.binary, "."], cwd=PARSER, env=env, check=True,
                           capture_output=True)
        cls.python = os.getenv("LOGPARSER_PYTHON", sys.executable)

    def setUp(self):
        self.dataset = "dataset_" + uuid.uuid4().hex
        self.work = self.path / self.dataset
        self.work.mkdir()
        def line(second, component, message):
            return (f"nova-compute.log 2017-05-14 21:43:{second:02}.123456789 2931 INFO {component} "
                    f"[-] [instance: {INSTANCE}] {message}\n")
        self.reference = self.work / "reference.log"
        self.reference.write_text(line(1, "nova.compute.manager", "Took 22.91 seconds to build instance."))
        self.target = self.work / "target.log"
        self.target.write_text(
            line(1, "nova.compute.claims", "Claim successful")
            + line(2, "nova.virt.libvirt.driver", "Creating image")
            + line(3, "nova.compute.manager", "Took 50.72 seconds to spawn the instance on the hypervisor.")
            + line(4, "nova.compute.manager", "Took 51.59 seconds to build instance.")
            + line(5, "nova.compute.manager", "Took 0.10 seconds to destroy the instance.")
            + "malformed line\n")
        self.import_files([self.reference, self.target], self.reference)
        self.config = RunConfig(self.dataset, 30)

    def import_files(self, paths, reference, config_path=None):
        suffix = uuid.uuid4().hex
        command = [self.python, "-m", "pipeline", "run", "--reference", str(reference),
                   "--dataset-id", self.dataset, "--parser", self.binary,
                   "--state-dir", str(self.work / ("state_" + suffix)),
                   "--work-dir", str(self.work / ("run_" + suffix))]
        for path in paths:
            command.extend(["--input", str(path)])
        if config_path:
            command.extend(["--config", str(config_path)])
        result = subprocess.run(command, cwd=PARSER, env={**os.environ, "CLICKHOUSE_DB": self.client.database},
                                capture_output=True, text=True)
        if result.returncode:
            self.fail("LogParser CLI failed: " + result.stderr[-3000:])

    def test_import_baseline_run_api_and_original_line(self):
        sources = Store(self.client).snapshot(self.dataset)
        import hashlib
        reference_hash = hashlib.sha256(self.reference.read_bytes()).hexdigest()
        report = run(self.client, RunConfig(self.dataset, reference_sources=(reference_hash,), margin_seconds=5))
        self.assertEqual(len(sources), 2)
        self.assertEqual(report["threshold_seconds"], 27.91)
        self.assertEqual(report["completed_instances"], 2)
        self.assertEqual(report["baseline"]["completed_instances"], 1)
        self.assertEqual(len(report["incidents"]), 1)
        card = report["incidents"][0]
        self.assertEqual(card["completeness"]["status"], "complete")
        self.assertEqual(card["stages"][2]["duration_seconds"], 50.72)
        self.assertEqual(card["event_time"], "2017-05-14T21:43:04.123456789Z")
        app = Application(self.client)
        self.assertEqual(app.dispatch("GET", "/v1/incidents/" + card["incident_id"], ""), (200, card))
        status, timeline = app.dispatch("GET", "/v1/incidents/" + card["incident_id"] + "/timeline", "")
        self.assertEqual(status, 200)
        self.assertEqual([r["line_start"] for r in timeline["events"]], [1, 2, 3, 4])
        status, event = app.dispatch("GET", "/v1/events/" + card["evidence_ids"][0], "")
        self.assertEqual(status, 200)
        self.assertEqual(event["raw_text"] + event["line_ending"], self.target.read_text().splitlines(keepends=True)[3])
        self.assertEqual(self.client.rows("SELECT count() AS n FROM incidents WHERE dataset_id={dataset:String}",
                                         {"dataset": self.dataset})[0]["n"], 1)

    def test_repeat_zero_replacement_and_historical_snapshot(self):
        first = run(self.client, self.config)
        self.assertEqual(run(self.client, self.config), first)
        empty = run(self.client, RunConfig(self.dataset, 100))
        self.assertEqual(empty["incidents"], [])
        self.assertEqual(Store(self.client).current_report(self.dataset), empty)
        self.assertEqual(self.client.rows("SELECT count() AS n FROM incidents WHERE dataset_id={dataset:String}",
                                         {"dataset": self.dataset})[0]["n"], 0)
        card = first["incidents"][0]
        self.assertEqual(Store(self.client).incident(card["incident_id"], first["analysis_run_id"])[0], card)
        self.assertEqual(run(self.client, self.config), first)
        self.assertEqual(Store(self.client).current_report(self.dataset), first)

    def test_failure_before_completion_and_lost_acknowledgement(self):
        with self.assertRaises(OSError):
            run(FaultClient(self.client, "incident_evidence_raw", after=True), self.config)
        self.assertEqual(Application(self.client).dispatch("GET", "/v1/incidents", "dataset_id=" + self.dataset)[0], 404)
        first = run(self.client, self.config)
        with self.assertRaises(OSError):
            run(FaultClient(self.client, "analysis_runs", completed=True), RunConfig(self.dataset, 100))
        self.assertEqual(Store(self.client).current_report(self.dataset), first)
        with self.assertRaises(OSError):
            run(FaultClient(self.client, "analysis_runs", after=True, completed=True), RunConfig(self.dataset, 100))
        published = Store(self.client).current_report(self.dataset)
        self.assertEqual(published, run(self.client, RunConfig(self.dataset, 100)))

    def test_parser_reimport_keeps_analysis_snapshot(self):
        first = run(self.client, self.config)
        store = Store(self.client)
        before = store.snapshot(self.dataset)
        event_id = first["incidents"][0]["evidence_ids"][0]
        evidence = store.event(event_id, first["analysis_run_id"])
        config = json.loads((PARSER / "config/drain.json").read_text())
        config["sim_th"] = 0.6
        config_path = self.work / "config.json"
        config_path.write_text(json.dumps(config))
        self.import_files([self.reference, self.target], self.reference, config_path)
        self.assertNotEqual(store.snapshot(self.dataset), before)
        self.assertEqual(store.event(event_id, first["analysis_run_id"]), evidence)
        self.assertEqual(store.current_report(self.dataset), first)
        updated = run(self.client, self.config)
        self.assertNotEqual(updated["analysis_run_id"], first["analysis_run_id"])
        self.assertEqual(updated["incidents"][0]["incident_id"], first["incidents"][0]["incident_id"])
        self.assertEqual(store.event(event_id, first["analysis_run_id"]), evidence)

    @unittest.skipUnless(importlib.util.find_spec("uvicorn"), "install .[api] for real HTTP test")
    def test_serve_over_http(self):
        report = run(self.client, self.config)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with (self.work / "server.log").open("w+") as log:
            process = subprocess.Popen([sys.executable, "-m", "log_analytics", "serve", "--port", str(port)],
                                       cwd=ANALYTICS, env={**os.environ, "CLICKHOUSE_DB": self.client.database},
                                       stdout=log, stderr=log)
            try:
                url = f"http://127.0.0.1:{port}/v1/incidents?dataset_id={self.dataset}"
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(url, timeout=1) as response:
                            self.assertEqual(json.load(response), report)
                        break
                    except urllib.error.URLError:
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail(log.read())
                        time.sleep(0.1)
                else:
                    self.fail("HTTP server did not start")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/incidents")
                self.assertEqual(error.exception.code, 422)
                error.exception.close()
            finally:
                process.terminate()
                process.wait(timeout=10)

    @unittest.skipUnless(os.getenv("LOGPARSER_DATA_DIR"), "set LOGPARSER_DATA_DIR for full archive acceptance")
    def test_full_openstack_archive(self):
        import hashlib
        data = Path(os.environ["LOGPARSER_DATA_DIR"])
        paths = [data / f"openstack_{name}.log" for name in ("normal1", "normal2", "abnormal")]
        # Use a new dataset: run always analyzes every published source of that dataset.
        self.dataset += "_archive"
        self.import_files(paths, paths[0])
        reference = hashlib.sha256(paths[0].read_bytes()).hexdigest()
        report = run(self.client, RunConfig(self.dataset, reference_sources=(reference,), margin_seconds=5))
        self.assertEqual(report["threshold_seconds"], 27.91)
        self.assertEqual([r["observed_seconds"] for r in report["incidents"]], [51.59, 42.81, 32.12, 30.32])
        store = Store(self.client)
        events = store.read_events(self.dataset, store.snapshot(self.dataset))
        evaluation = detect((e.build for e in events if e.build.source_sha256 != reference),
                            DetectorConfig(self.dataset, report["threshold_seconds"]))
        self.assertEqual(evaluation.completed_instances, 1510)
        self.assertEqual(evaluation.incomplete_instances, 3)
        self.assertEqual(report["incidents"][0]["stages"][2]["duration_seconds"], 50.72)
        self.assertTrue(all(r["completeness"]["status"] == "complete" for r in report["incidents"]))
