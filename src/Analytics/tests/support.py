import copy
import hashlib
import re
import uuid
from collections import defaultdict


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def record(line, duration=None, *, source="source", instance="vm", **changes):
    row = {"schema_version": 1, "dataset_id": "test", "source_file": "input.log",
           "source_sha256": digest(source), "event_id": digest(f"{source}:{line}"),
           "instance_id": instance, "event_time": f"2017-05-14T21:43:{line:02}.000000001Z",
           "build_duration_seconds": duration, "spawn_duration_seconds": None,
           "line_start": line, "line_end": line, "raw_text": "original log line", "line_ending": "\n",
           "component": "nova.compute.manager", "message": "message", "parse_status": "ok",
           "ingestion_run_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, source))}
    return {**row, **changes}


def vm_records():
    return [record(1, component="nova.compute.claims", message="Claim successful"),
            record(2, component="nova.virt.libvirt.driver", message="Creating image"),
            record(3, spawn_duration_seconds=50.72), record(4, 51.59)]


class MemoryClient:
    """A storage double; real SQL semantics are exercised by opt-in integration tests."""

    def __init__(self, records=None):
        self.url, self.database = "http://memory", "test_" + uuid.uuid4().hex
        self.tables = defaultdict(list)
        self.tables["log_events_raw"] = copy.deepcopy(records if records is not None else vm_records())
        self.publications = [{"source_sha256": row["source_sha256"], "ingestion_run_id": row["ingestion_run_id"],
                              "processing_version": "a" * 64}
                             for row in {r["source_sha256"]: r for r in self.tables["log_events_raw"]}.values()]
        self.on_read = None
        self.on_insert = None

    def migrate(self):
        pass

    def current(self):
        return {row["dataset_id"]: row for row in self.tables["analysis_runs"] if row["status"] == "completed"}

    def insert(self, table, rows):
        if self.on_insert:
            self.on_insert(table, rows)
        self.tables[table].extend(copy.deepcopy(rows))

    def rows(self, sql, params=None):
        params = params or {}
        table = re.search(r"FROM (\w+)", sql).group(1)
        if table == "current_ingestions":
            return copy.deepcopy(sorted(self.publications, key=lambda r: r["source_sha256"]))
        if table == "current_analysis_runs":
            return copy.deepcopy([r for k, r in self.current().items() if k == params["dataset"]])
        if table in {"incidents", "incident_evidence"}:
            active = {r["analysis_run_id"] for r in self.current().values()}
            rows = [r for r in self.tables[table + "_raw"] if r["analysis_run_id"] in active]
        else:
            rows = self.tables[table]
        fields = {"dataset": "dataset_id", "source": "source_sha256", "ingestion": "ingestion_run_id",
                  "version": "analysis_version", "run": "analysis_run_id",
                  "id": "event_id" if "evidence" in table else "incident_id"}
        for name, value in params.items():
            rows = [r for r in rows if r[fields[name]] == value]
        if "status='completed'" in sql:
            completed = {r["analysis_run_id"] for r in self.tables["analysis_runs"] if r["status"] == "completed"}
            rows = [r for r in rows if r["analysis_run_id"] in completed
                    and r.get("status", "completed") == "completed"]
        if "count() AS rows" in sql:
            keys = [(r["incident_id"], r.get("event_id")) for r in rows]
            return [{"rows": len(rows), "ids": len(set(keys))}]
        if "LIMIT 1" in sql:
            rows = rows[-1:]
        result = copy.deepcopy(rows)
        if "SELECT DISTINCT" in sql:
            result = list({(r["analysis_run_id"], r["event_json"]): r for r in result}.values())
        if table == "log_events_raw" and self.on_read:
            self.on_read()
        return result
