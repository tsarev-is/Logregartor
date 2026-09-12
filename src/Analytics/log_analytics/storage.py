"""Storage boundaries and immutable reads pinned to completed analysis attempts."""

import json

from .clickhouse import canonical
from .events import AnalysisEvent

EVENT_COLUMNS = """schema_version, event_id, dataset_id, source_file, source_sha256,
line_start, line_end, raw_text, line_ending, timestamp_raw, event_time, timezone_assumption,
component, instance_id, message, build_duration_seconds, spawn_duration_seconds,
parse_status, ingestion_run_id"""


class NotFound(ValueError):
    pass


class Store:
    def __init__(self, client):
        self.client = client

    def health(self):
        self.client.rows("SELECT analysis_run_id FROM current_analysis_runs LIMIT 1")
        return {"status": "ok"}

    def datasets(self):
        # A fresh Analytics installation may precede the first LogParser import.
        parser = self.client.rows(
            "SELECT name FROM system.tables WHERE database=currentDatabase() AND name='current_ingestions'")
        inputs = self.client.rows(
            "SELECT dataset_id, source_sha256, ingestion_run_id, processing_version "
            "FROM current_ingestions ORDER BY dataset_id, source_sha256") if parser else []
        snapshots = {}
        for row in inputs:
            snapshots.setdefault(row["dataset_id"], []).append(
                {key: row[key] for key in ("source_sha256", "ingestion_run_id", "processing_version")})
        reports = {row["dataset_id"]: json.loads(row["report_json"]) for row in self.client.rows(
            "SELECT dataset_id, report_json FROM current_analysis_runs ORDER BY dataset_id")}
        datasets = []
        for dataset in sorted(snapshots.keys() | reports.keys()):
            report = reports.get(dataset)
            snapshot = snapshots.get(dataset, [])
            datasets.append({"dataset_id": dataset, "ingested_sources": len(snapshot),
                             "analysis_run_id": report["analysis_run_id"] if report else None,
                             "incident_count": len(report["incidents"]) if report else None,
                             "analysis_stale": bool(report and report["input_ingestions"] != snapshot)})
        return {"datasets": datasets}

    def snapshot(self, dataset):
        return self.client.rows(
            "SELECT source_sha256, ingestion_run_id, processing_version FROM current_ingestions "
            "WHERE dataset_id={dataset:String} ORDER BY source_sha256", {"dataset": dataset})

    def read_events(self, dataset, snapshot):
        events = []
        for source in snapshot:
            records = self.client.rows(
                f"SELECT {EVENT_COLUMNS} FROM log_events_raw WHERE dataset_id={{dataset:String}} "
                "AND source_sha256={source:String} AND ingestion_run_id={ingestion:UUID}",
                {"dataset": dataset, "source": source["source_sha256"], "ingestion": source["ingestion_run_id"]})
            seen = set()
            for record in records:
                event = AnalysisEvent.from_record(record)
                if (event.build.dataset_id != dataset or event.build.source_sha256 != source["source_sha256"]
                        or record["ingestion_run_id"] != source["ingestion_run_id"]):
                    raise ValueError("event does not belong to the pinned ingestion")
                if event.build.event_id in seen:
                    raise ValueError("duplicate event_id in published ingestion")
                seen.add(event.build.event_id)
                events.append(event)
        return events

    def assert_snapshot(self, dataset, snapshot):
        if snapshot != self.snapshot(dataset):
            raise ValueError("LogParser publication changed during analysis; no result published, rerun")

    def completed(self, dataset, version):
        rows = self.client.rows(
            "SELECT analysis_run_id, dataset_id, analysis_version, input_snapshot_json, configuration_json, report_json "
            "FROM analysis_runs WHERE dataset_id={dataset:String} AND analysis_version={version:String} "
            "AND status='completed' ORDER BY recorded_at DESC, analysis_run_id DESC LIMIT 1",
            {"dataset": dataset, "version": version})
        return rows[0] if rows else None

    def stage(self, report, timelines, batch_size=1000):
        cards, evidence = [], []
        for card in report["incidents"]:
            timeline = timelines[card["incident_id"]]
            common = {"analysis_run_id": report["analysis_run_id"], "dataset_id": report["dataset_id"],
                      "incident_id": card["incident_id"]}
            cards.append({**common, "source_sha256": card["source_sha256"], "instance_id": card["instance_id"],
                          "excess_seconds": card["excess_seconds"], "card_json": canonical(card),
                          "timeline_json": canonical(timeline)})
            for event in timeline["events"] + timeline["undated_events"]:
                evidence.append({**common, "event_id": event["event_id"],
                                 "ingestion_run_id": event["ingestion_run_id"], "event_json": canonical(event)})
        for table, rows in (("incidents_raw", cards), ("incident_evidence_raw", evidence)):
            for start in range(0, len(rows), batch_size):
                self.client.insert(table, rows[start:start + batch_size])
            counts = self.client.rows(
                f"SELECT count() AS rows, uniqExact(tuple(incident_id{', event_id' if table == 'incident_evidence_raw' else ''})) AS ids "
                f"FROM {table} WHERE analysis_run_id={{run:UUID}}", {"run": report["analysis_run_id"]})[0]
            if int(counts["rows"]) != len(rows) or int(counts["ids"]) != len(rows):
                raise ValueError("staged Analytics count/uniqueness check failed; attempt remains unpublished")

    def current_report(self, dataset):
        rows = self.client.rows("SELECT report_json FROM current_analysis_runs WHERE dataset_id={dataset:String}",
                                {"dataset": dataset})
        if not rows:
            raise NotFound("no published analysis for dataset")
        return json.loads(rows[0]["report_json"])

    def incident(self, incident_id, run=None):
        table = "incidents" if run is None else "incidents_raw"
        condition = "" if run is None else (
            " AND analysis_run_id={run:UUID} AND analysis_run_id IN "
            "(SELECT analysis_run_id FROM analysis_runs WHERE status='completed')")
        rows = self.client.rows(f"SELECT card_json, timeline_json FROM {table} "
                                "WHERE incident_id={id:String}" + condition,
                                {"id": incident_id, **({"run": run} if run else {})})
        if not rows:
            raise NotFound("incident not found in published analysis")
        return json.loads(rows[0]["card_json"]), json.loads(rows[0]["timeline_json"])

    def event(self, event_id, run=None):
        table = "incident_evidence" if run is None else "incident_evidence_raw"
        condition = "" if run is None else (
            " AND analysis_run_id={run:UUID} AND analysis_run_id IN "
            "(SELECT analysis_run_id FROM analysis_runs WHERE status='completed')")
        rows = self.client.rows(f"SELECT DISTINCT analysis_run_id, event_json FROM {table} "
                                "WHERE event_id={id:String}" + condition,
                                {"id": event_id, **({"run": run} if run else {})})
        if not rows:
            raise NotFound("event not found in published evidence")
        if len(rows) > 1:
            raise ValueError("event appears in multiple datasets; specify analysis_run_id")
        return {**json.loads(rows[0]["event_json"]), "analysis_run_id": rows[0]["analysis_run_id"]}
