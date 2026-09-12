import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from log_analytics.cli import main


def record():
    source = hashlib.sha256(b"synthetic source").hexdigest()
    return {
        "schema_version": 1,
        "event_id": hashlib.sha256(f"{source}:1".encode()).hexdigest(),
        "dataset_id": "openstack",
        "source_sha256": source,
        "instance_id": "00000000-0000-0000-0000-000000000001",
        "event_time": "2017-05-14T21:43:33.901Z",
        "build_duration_seconds": 51.59,
        "level": "INFO",
    }


class CliTests(unittest.TestCase):
    def run_cli(self, content, threshold="30"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(content, encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = main(["detect", "--input", str(path), "--dataset-id", "openstack",
                               "--threshold-seconds", threshold])
            return status, stdout.getvalue(), stderr.getvalue()

    def test_info_event_detected_without_labels(self):
        source = record()
        status, output, error = self.run_cli(json.dumps(source) + "\n")
        self.assertEqual((status, error), (0, ""))
        incident = json.loads(output)["incidents"][0]
        self.assertEqual(incident["evidence_ids"], [source["event_id"]])
        self.assertEqual(incident["observed_seconds"], 51.59)

    def test_malformed_tail_does_not_publish_partial_report(self):
        status, output, error = self.run_cli(json.dumps(record()) + "\nnot-json\n")
        self.assertEqual((status, output), (1, ""))
        self.assertIn("events.jsonl:2:", error)

    def test_invalid_event_contract(self):
        for field, value in (("schema_version", 2), ("event_id", "bad"),
                             ("build_duration_seconds", -1),
                             ("build_duration_seconds", float("nan")),
                             ("build_duration_seconds", True)):
            with self.subTest(field=field, value=value):
                source = record()
                source[field] = value
                status, output, error = self.run_cli(json.dumps(source))
                self.assertEqual((status, output), (1, ""))
                self.assertIn("events.jsonl:1:", error)

    def test_missing_field(self):
        source = record()
        del source["build_duration_seconds"]
        status, output, error = self.run_cli(json.dumps(source))
        self.assertEqual((status, output), (1, ""))
        self.assertIn("missing field", error)

    def test_empty_input_produces_empty_report(self):
        status, output, error = self.run_cli("")
        self.assertEqual((status, error), (0, ""))
        self.assertEqual(json.loads(output)["incidents"], [])

    def test_nonfinite_threshold_is_rejected(self):
        status, output, error = self.run_cli("", "nan")
        self.assertEqual((status, output), (1, ""))
        self.assertIn("threshold_seconds", error)
