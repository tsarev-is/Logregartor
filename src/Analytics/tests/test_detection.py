import hashlib
import unittest

from log_analytics.config import DetectorConfig
from log_analytics.detectors.build_duration import detect
from log_analytics.models import BuildEvent


def event(line, duration, *, instance="vm-1", source="a", dataset="openstack"):
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    return BuildEvent(
        event_id=hashlib.sha256(f"{source_hash}:{line}".encode()).hexdigest(),
        dataset_id=dataset,
        source_sha256=source_hash,
        instance_id=instance,
        event_time="2017-05-14T21:43:33.901Z",
        build_duration_seconds=duration,
    )


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.config = DetectorConfig("openstack", 30)

    def test_strict_threshold_and_ranking(self):
        records = [event(1, 30, instance="at-threshold"), event(2, 20),
                   event(3, 32, instance="slow"), event(4, 51, instance="slowest")]
        report = detect(records, self.config)
        self.assertEqual([row.observed_seconds for row in report.incidents], [51, 32])
        self.assertEqual(report.incidents[0].evidence_ids, (records[3].event_id,))
        self.assertEqual(report.incidents[0].excess_seconds, 21)

    def test_instances_are_scoped_by_source_and_dataset(self):
        records = [event(1, 51), event(2, 42, source="b"),
                   event(3, 100, dataset="other")]
        report = detect(records, self.config)
        self.assertEqual(report.completed_instances, 2)
        self.assertEqual(len({row.incident_id for row in report.incidents}), 2)

    def test_maximum_per_vm_and_repeatable_evidence(self):
        records = [event(1, 42), event(2, 51), event(3, 51), event(2, 51)]
        report = detect(records, self.config)
        self.assertEqual(report, detect(reversed(records), self.config))
        self.assertEqual(len(report.incidents), 1)
        self.assertEqual(report.incidents[0].observed_seconds, 51)
        self.assertEqual(report.incidents[0].evidence_ids,
                         (max(records[1].event_id, records[2].event_id),))

    def test_incomplete_and_unattributed_events_do_not_create_incidents(self):
        report = detect([event(1, None), event(2, 100, instance=None)], self.config)
        self.assertEqual(report.incomplete_instances, 1)
        self.assertEqual(report.completed_instances, 0)
        self.assertEqual(report.incidents, ())

    def test_empty_input(self):
        report = detect([], self.config)
        self.assertEqual(report.events_read, 0)
        self.assertEqual(report.instances_observed, 0)
        self.assertEqual(report.incidents, ())

    def test_invalid_threshold(self):
        for value in (-1, 0, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DetectorConfig("openstack", value)
