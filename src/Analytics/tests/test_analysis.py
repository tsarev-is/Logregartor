import unittest

from log_analytics.baseline import RunConfig, resolve_threshold
from log_analytics.config import DetectorConfig
from log_analytics.detectors.build_duration import detect
from log_analytics.events import AnalysisEvent, utc_time
from log_analytics.models import BuildEvent
from log_analytics.stages import episode
from support import digest, record, vm_records


class BaselineTests(unittest.TestCase):
    def test_reference_counts_maximum_per_vm_and_median(self):
        rows = [record(1, 10), record(2, 20), record(3, 22, instance="second"),
                record(4, instance="unfinished"), record(5, 1000, source="target"),
                record(6, 9999, instance=None)]
        threshold, baseline = resolve_threshold([BuildEvent.from_record(r) for r in rows],
            RunConfig("test", reference_sources=(digest("source"),), margin_seconds=5),
            {digest("source"), digest("target")})
        self.assertEqual(threshold, 27)
        self.assertEqual(baseline["median_seconds"], 21)
        self.assertEqual(baseline["completed_instances"], 2)
        self.assertEqual(baseline["incomplete_instances"], 1)

    def test_empty_and_unpublished_reference(self):
        config = RunConfig("test", reference_sources=(digest("source"),), margin_seconds=5)
        for sources in (set(), {digest("source")}):
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                resolve_threshold([], config, sources)

    def test_configuration_cannot_mix_threshold_modes(self):
        for kwargs in ({}, {"threshold_seconds": 30, "margin_seconds": 5},
                       {"threshold_seconds": 30, "reference_sources": (digest("source"),)},
                       {"reference_sources": (digest("source"),)},
                       {"reference_sources": ("input.log",), "margin_seconds": 5},
                       {"reference_sources": (digest("source"),), "margin_seconds": float("nan")},
                       {"reference_sources": (digest("source"),), "margin_seconds": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RunConfig("test", **kwargs)


class EpisodeTests(unittest.TestCase):
    def analyze(self, rows):
        events = [AnalysisEvent.from_record(r) for r in rows]
        incident = detect([e.build for e in events], DetectorConfig("test", 30)).incidents[0]
        return episode(events, incident)

    def test_stages_and_overlapping_durations(self):
        stages, completeness, timeline = self.analyze(vm_records())
        self.assertEqual([s["found"] for s in stages], [True] * 4)
        self.assertEqual([s["duration_seconds"] for s in stages], [None, None, 50.72, 51.59])
        self.assertEqual(completeness["status"], "complete")
        self.assertEqual(len(timeline["events"]), 4)

    def test_previous_build_and_destroy_do_not_leak(self):
        rows = [record(1, 40), *vm_records()[1:], record(5, message="destroyed"),
                record(6, 35), record(7, message="later attempt")]
        stages, completeness, timeline = self.analyze(rows)
        self.assertEqual([e["line_start"] for e in timeline["events"]], [2, 3, 4])
        self.assertEqual(completeness["missing_stages"], ["allocate"])

    def test_other_source_uuid_and_unattributed_events_excluded(self):
        rows = vm_records() + [record(2, source="other"), record(2, instance=None),
                              record(2, instance="other"), record(2, dataset_id="other")]
        _, _, timeline = self.analyze(rows)
        self.assertEqual(len(timeline["events"]), 4)

    def test_missing_spawn_preserves_build_evidence(self):
        stages, completeness, _ = self.analyze([vm_records()[0], vm_records()[1], vm_records()[3]])
        self.assertEqual(completeness["missing_stages"], ["spawn"])
        self.assertEqual(stages[3]["evidence_ids"], [vm_records()[3]["event_id"]])

    def test_nanosecond_order_and_offset_conversion(self):
        rows = [record(1, event_time="2017-05-14T22:43:02.000000002+01:00"),
                record(2, event_time="2017-05-14T21:43:02.000000001Z"), record(4, 51)]
        _, _, timeline = self.analyze(rows)
        self.assertEqual([e["line_start"] for e in timeline["events"]], [2, 1, 4])
        self.assertEqual(timeline["events"][1]["event_time"], "2017-05-14T21:43:02.000000002Z")
        self.assertEqual(utc_time("2017-05-14 21:43:02.123456789")[0], "2017-05-14T21:43:02.123456789Z")

    def test_equal_time_line_then_event_id_and_reordered_input(self):
        rows = vm_records()
        rows[0]["event_time"] = rows[1]["event_time"]
        rows.insert(1, {**rows[0], "event_id": "f" * 64})
        first = self.analyze(rows)
        self.assertEqual(first, self.analyze(reversed(rows)))
        self.assertEqual([r["line_start"] for r in first[2]["events"]], [1, 1, 2, 3, 4])

    def test_undated_events_are_separate_and_bounded(self):
        rows = [record(1, 20), record(2, event_time=None), record(3, 51), record(4, event_time=None)]
        _, completeness, timeline = self.analyze(rows)
        self.assertEqual([e["line_start"] for e in timeline["events"]], [3])
        self.assertEqual([e["line_start"] for e in timeline["undated_events"]], [2])
        self.assertEqual(completeness["status"], "incomplete")

    def test_undated_build_still_has_evidence(self):
        stages, completeness, timeline = self.analyze([record(1, 20), record(2), record(3, 51, event_time=None)])
        self.assertEqual([e["line_start"] for e in timeline["events"]], [2])
        self.assertEqual(stages[3]["evidence_ids"], [record(3)["event_id"]])
        self.assertEqual(completeness["undated_event_ids"], [record(3)["event_id"]])

    def test_malformed_projection(self):
        for changes in ({"event_time": "bad"}, {"spawn_duration_seconds": float("inf")},
                        {"spawn_duration_seconds": True}, {"ingestion_run_id": "bad"},
                        {"line_start": 0}, {"line_end": 0}, {"parse_status": "unknown"},
                        {"message": None}, {"component": 42}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                AnalysisEvent.from_record(record(1, **changes))
