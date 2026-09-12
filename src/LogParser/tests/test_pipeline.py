import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.artifacts import canonical, load_json, read_events, read_report, sha256, write_json
from pipeline.evaluate import grouping_metrics
from pipeline.templates import fit, load_state, transform
from pipeline.prepare import prepare
from tests.support import HEADER, INSTANCE, NORMAL, enriched, parsed


class ArtifactAndTemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_go_python_contract_and_frozen_inference(self):
        reference, report = parsed(self.path)
        first = fit(reference, report, self.path / "state")
        second = fit(reference, report, self.path / "state2")
        self.assertEqual(first["template_version"], second["template_version"])
        self.assertEqual(first["catalog_sha256"], second["catalog_sha256"])
        raw = (f"{HEADER} [-] {INSTANCE} Took 51.59 seconds to build instance.\r\n"
               f"{HEADER} [-] Completely new protocol announcement xyz\n"
               f"{HEADER}\n"
               "broken header\n\n")
        events, event_report = parsed(self.path, raw, "target")
        snapshot = sha256(self.path / "state/snapshot.bin")
        for i in range(2):
            transform(events, event_report, self.path / f"out{i}", self.path / f"report{i}", self.path / "state")
        self.assertEqual(sha256(self.path / "out0"), sha256(self.path / "out1"))
        self.assertEqual(snapshot, sha256(self.path / "state/snapshot.bin"))
        rows = list(read_events(self.path / "out0", read_report(self.path / "out0", self.path / "report0")))
        self.assertEqual([r["template_status"] for r in rows], ["matched", "unknown", "skipped", "skipped", "skipped"])
        self.assertEqual(rows[0]["build_duration_seconds"], 51.59)
        self.assertIsNone(rows[0]["host"])
        self.assertIsNone(rows[1]["template_id"])
        self.assertEqual(rows[2]["parse_status"], "ok")
        self.assertEqual(rows[3]["parse_status"], "unparsed")
        self.assertEqual(rows[4]["parse_status"], "empty")
        self.assertEqual("".join(r["raw_text"] + r["line_ending"] for r in rows), raw)

    def test_truncated_jsonl_and_forged_identity_are_rejected(self):
        events, path = parsed(self.path)
        report = load_json(path)
        lines = events.read_text().splitlines()
        events.write_text(lines[0] + "\n")
        with self.assertRaisesRegex(ValueError, "hash differs"):
            read_report(events, path)
        report["events_sha256"] = sha256(events)
        with self.assertRaisesRegex(ValueError, "coverage"):
            list(read_events(events, report))
        row = json.loads(lines[0]); row["event_id"] = "f" * 64
        events.write_text(canonical(row) + "\n" + lines[1] + "\n")
        report["events_sha256"] = sha256(events)
        with self.assertRaisesRegex(ValueError, "identity"):
            list(read_events(events, report))

    def test_schema_rejects_missing_fields_and_nonfinite_values(self):
        events, path = parsed(self.path)
        rows = [json.loads(line) for line in events.read_text().splitlines()]
        del rows[0]["raw_text"]
        events.write_text("\n".join(canonical(row) for row in rows) + "\n")
        report = load_json(path); report["events_sha256"] = sha256(events)
        with self.assertRaises(ValueError):
            list(read_events(events, report))
        # json.loads otherwise accepts NaN; it must not reach JSONEachRow.
        events.write_text('{"value": NaN}\n')
        report["events_sha256"] = sha256(events)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            list(read_events(events, report))

    def test_structured_instance_prefix_and_proxy_addresses_do_not_split_templates(self):
        raw = (f'{HEADER} [-] 10.0.0.1 "GET /v2/servers/detail HTTP/1.1" status: 200 len: 4 time: 0.1\n'
               f'{HEADER} [-] 10.0.0.1,10.0.0.2 "GET /v2/servers/detail HTTP/1.1" status: 200 len: 6 time: 0.2\n'
               f'{HEADER} [-] {INSTANCE} VM Started (Lifecycle Event)\n'
               f'{HEADER} [-] {INSTANCE} VM Paused (Lifecycle Event)\n')
        events, report = parsed(self.path, raw)
        state = self.path / "state"
        fit(events, report, state)
        output, metadata = self.path / "out", self.path / "report"
        transform(events, report, output, metadata, state)
        rows = list(read_events(output, read_report(output, metadata)))
        self.assertEqual(rows[0]["template_id"], rows[1]["template_id"])
        self.assertNotEqual(rows[2]["template_id"], rows[3]["template_id"])
        self.assertTrue(rows[2]["message"].startswith(INSTANCE))
        _, _, catalog = load_state(state)
        self.assertTrue(all("[instance:" not in row["template_text"] for row in catalog))

    def test_modified_snapshot_and_wrong_runtime_are_rejected(self):
        _, _, state = enriched(self.path)
        with patch("pipeline.templates.versions", return_value={"drain3": "different"}):
            with self.assertRaisesRegex(ValueError, "runtime"):
                load_state(state)
        with (state / "snapshot.bin").open("ab") as out:
            out.write(b"changed")
        with self.assertRaisesRegex(ValueError, "checksum"):
            load_state(state)

    def test_transform_failure_preserves_existing_output(self):
        events, report = parsed(self.path)
        state = self.path / "state"
        fit(events, report, state)
        output, target_report = self.path / "out", self.path / "report"
        output.write_text("previous output")
        rows = events.read_text().splitlines()
        row = json.loads(rows[1]); row["event_id"] = "f" * 64
        events.write_text(rows[0] + "\n" + canonical(row) + "\n")
        metadata = load_json(report); metadata["events_sha256"] = sha256(events); write_json(report, metadata)
        with self.assertRaises(ValueError):
            transform(events, report, output, target_report, state)
        self.assertEqual(output.read_text(), "previous output")

    def test_empty_file_retains_manifest(self):
        events, report, _ = enriched(self.path, content="")
        metadata = read_report(events, report)
        self.assertEqual(metadata["physical_lines"], 0)
        self.assertEqual(len(metadata["files"]), 1)
        self.assertEqual(list(read_events(events, metadata)), [])

    def test_prepare_rejects_changed_download_without_extracting(self):
        cache = self.path / "cache"; cache.mkdir()
        (cache / "OpenStack.tar.gz").write_bytes(b"not the expected archive")
        with self.assertRaisesRegex(ValueError, "checksum"):
            prepare(self.path / "data", cache)
        self.assertFalse((self.path / "data/openstack_normal1.log").exists())


class GroupingTests(unittest.TestCase):
    def test_exact_grouping_ignores_cluster_names(self):
        scores = grouping_metrics(["a", "a", "b", "b"], ["2", "2", "1", "1"])
        self.assertEqual(scores["pairwise_f1"], 1)
        self.assertEqual(scores["grouping_accuracy"], 1)

    def test_merged_and_split_groups(self):
        merged = grouping_metrics(["a", "a", "b", "b"], ["x"] * 4)
        self.assertAlmostEqual(merged["pairwise_precision"], 1 / 3)
        self.assertEqual(merged["grouping_accuracy"], 0)
        split = grouping_metrics(["a", "a"], ["x", "y"])
        self.assertEqual(split["pairwise_recall"], 0)
        self.assertEqual(split["grouping_accuracy"], 0)


if __name__ == "__main__":
    unittest.main()
