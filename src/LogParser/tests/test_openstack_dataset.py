"""Optional acceptance test against the pinned complete archive and existing audit."""

import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from pipeline.artifacts import ROOT, load_json, read_events, read_report
from pipeline.__main__ import parse_with_go
from pipeline.prepare import LOG_FILES
from tests.support import binary


@unittest.skipUnless(os.getenv("LOGPARSER_DATA_DIR"), "set LOGPARSER_DATA_DIR after pipeline prepare")
class OpenStackDatasetTests(unittest.TestCase):
    def test_full_archive_matches_independent_audit(self):
        data = Path(os.environ["LOGPARSER_DATA_DIR"])
        audit = load_json(ROOT / "tests/fixtures/openstack_audit.json")
        with tempfile.TemporaryDirectory() as temp:
            output, report_path = parse_with_go(binary(), [data / name for name in LOG_FILES], "openstack", "UTC", Path(temp) / "events.jsonl")
            report = read_report(output, report_path)
            self.assertEqual(report["physical_lines"], audit["total_physical_log_lines"])
            self.assertEqual(sum(f["headers_without_request_context"] for f in report["files"]), 184)
            self.assertEqual(sum(f["empty_messages"] for f in report["files"]), 8)
            for file in report["files"]:
                expected = audit["files"][file["source_file"]]
                self.assertEqual(file["physical_lines"], expected["physical_lines"])
                self.assertEqual(file["parse_counts"], {"ok": expected["physical_lines"]})
                self.assertEqual(file["headers_without_request_context"], expected["headers_without_request_context"])
                self.assertEqual(file["features"]["instance_id"], expected["lines_with_explicit_instance_id"])
            levels = {name: Counter() for name in LOG_FILES}
            statuses = {name: Counter() for name in LOG_FILES}
            builds = {name: {} for name in LOG_FILES}
            evidence = {}
            for event in read_events(output, report):
                name = event["source_file"]
                levels[name][event["level"]] += 1
                if event["http_status"] is not None:
                    statuses[name][str(event["http_status"])] += 1
                value = event["build_duration_seconds"]
                if value is not None and event["instance_id"]:
                    instance = event["instance_id"]
                    builds[name][instance] = max(value, builds[name].get(instance, 0))
                    evidence[name, event["line_start"]] = (instance, value)
            for name in LOG_FILES:
                expected = audit["files"][name]
                self.assertEqual(dict(levels[name]), expected["levels"])
                self.assertEqual(dict(statuses[name]), expected["http_statuses"])
                self.assertEqual(len(builds[name]), expected["instances_with_completed_build"])
                self.assertEqual(max(builds[name].values()), expected["max_build_seconds"])
            for row in audit["files"]["openstack_abnormal.log"]["labeled_build_evidence"]:
                self.assertEqual(evidence["openstack_abnormal.log", row["line"]], (row["instance_id"], row["duration_seconds"]))


if __name__ == "__main__":
    unittest.main()
