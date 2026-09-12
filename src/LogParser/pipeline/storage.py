"""Публикация проверенных файлов: незавершённые попытки не видны потребителям."""

import base64
import fcntl
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import VERSION
from .artifacts import ROOT, canonical, digest, read_events, read_report
from .templates import load_state


class ClickHouseError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ClickHouseError("ClickHouse redirects are not supported")


class ClickHouse:
    def __init__(self, url, database, user, password, timeout=60):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("CLICKHOUSE_URL must be an HTTP(S) endpoint without credentials, query or fragment")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
            raise ValueError("invalid ClickHouse database name")
        if timeout <= 0:
            raise ValueError("ClickHouse timeout must be positive")
        self.url, self.database, self.timeout = url.rstrip("/"), database, timeout
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.opener = urllib.request.build_opener(NoRedirect())

    @classmethod
    def from_env(cls):
        return cls(os.getenv("CLICKHOUSE_URL", "http://localhost:8123"),
                   os.getenv("CLICKHOUSE_DB", "logs"), os.getenv("CLICKHOUSE_USER", "logregartor"),
                   os.getenv("CLICKHOUSE_PASSWORD", "localdev"), float(os.getenv("CLICKHOUSE_TIMEOUT", "60")))

    def execute(self, sql, params=None, data=None, use_database=True):
        query = {"wait_end_of_query": "1", "date_time_input_format": "best_effort", "async_insert": "0"}
        if use_database:
            query["database"] = self.database
        for key, value in (params or {}).items():
            query["param_" + key] = str(value)
        if data is None:
            body = sql.encode()
        else:
            query["query"] = sql
            body = data
        request = urllib.request.Request(self.url + "/?" + urllib.parse.urlencode(query), data=body,
                                         headers={"Authorization": self.auth, "Content-Type": "application/octet-stream"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                result = response.read().decode("utf-8")
                if response.headers.get("X-ClickHouse-Exception-Code"):
                    raise ClickHouseError(result[:1500])
                return result
        except urllib.error.HTTPError as exc:
            raise ClickHouseError(f"ClickHouse HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:1500]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # A disconnected INSERT may already have succeeded. Never blindly retry.
            raise ClickHouseError("ClickHouse request failed; INSERT outcome may be unknown. Rerun the load as a new attempt.") from exc

    def rows(self, sql, params=None):
        return [json.loads(line) for line in self.execute(sql + " FORMAT JSONEachRow", params).splitlines() if line]

    def insert(self, table, rows):
        if table not in {"log_events_raw", "event_templates_raw", "ingestion_runs"}:
            raise ValueError("unexpected insertion table")
        if rows:
            self.execute(f"INSERT INTO {table} FORMAT JSONEachRow",
                         data=("\n".join(canonical(row) for row in rows) + "\n").encode())

    def migrate(self):
        self.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}`", use_database=False)
        for migration in sorted((ROOT / "sql").glob("*.sql")):
            for statement in migration.read_text().split(";"):
                if statement.strip():
                    self.execute(statement)


@contextmanager
def writer_lock(client):
    key = digest({"url": client.url, "database": client.database})
    path = Path(tempfile.gettempdir()) / f"logparser-{os.getuid()}-{key}.lock"
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another local importer is writing to this ClickHouse database") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def load(events, report_path, state_dir, client, batch_size=5000):
    if batch_size < 1:
        raise ValueError("batch size must be positive")
    report = read_report(events, report_path)
    _, manifest, catalog = load_state(state_dir)
    if report.get("pipeline_version") != VERSION or report.get("template_version") != manifest["template_version"]:
        raise ValueError("transformed report and vocabulary version differ")
    expected_version = digest({k: report[k] for k in
        ("schema_version", "parser_version", "timezone_assumption", "template_version", "pipeline_version")})
    if expected_version != report.get("processing_version"):
        raise ValueError("invalid processing version")
    catalog_ids = {t["template_id"] for t in catalog}
    with writer_lock(client):
        client.migrate()
        runs = {}
        result = {"dataset_id": report["dataset_id"], "processing_version": expected_version, "files": []}
        for source in report["files"]:
            params = {"dataset": report["dataset_id"], "source": source["source_sha256"]}
            current = client.rows("SELECT ingestion_run_id, processing_version FROM current_ingestions "
                                  "WHERE dataset_id={dataset:String} AND source_sha256={source:String}", params)
            if current and current[0]["processing_version"] == expected_version:
                runs[source["source_sha256"]] = None
                result["files"].append({**source, "status": "skipped", "ingestion_run_id": current[0]["ingestion_run_id"]})
                continue
            run = {"ingestion_run_id": str(uuid.uuid4()), "dataset_id": report["dataset_id"],
                   "source_sha256": source["source_sha256"], "source_file": source["source_file"],
                   "processing_version": expected_version, "template_version": manifest["template_version"],
                   "expected_rows": source["physical_lines"], "status": "started"}
            runs[source["source_sha256"]] = run
            client.insert("ingestion_runs", [run])
            for offset in range(0, len(catalog), batch_size):
                client.insert("event_templates_raw", [{**t, "ingestion_run_id": run["ingestion_run_id"]}
                                                     for t in catalog[offset:offset + batch_size]])
            result["files"].append({**source, "status": "completed", "ingestion_run_id": run["ingestion_run_id"]})
        batch = []
        for event in read_events(events, report):
            if event["ingestion_run_id"] is not None or event["template_status"] == "pending":
                raise ValueError("load requires transformed, not previously loaded events")
            if event["template_version"] != manifest["template_version"]:
                raise ValueError("event and catalog template versions differ")
            if event["template_id"] is not None and event["template_id"] not in catalog_ids:
                raise ValueError("event references a missing template")
            run = runs[event["source_sha256"]]
            if run is None:
                continue
            event["ingestion_run_id"] = run["ingestion_run_id"]
            batch.append(event)
            if len(batch) >= batch_size:
                client.insert("log_events_raw", batch)
                batch = []
        client.insert("log_events_raw", batch)
        # read_events has now checked every source hash and the whole artifact.
        for run in runs.values():
            if run is None:
                continue
            params = {"run": run["ingestion_run_id"]}
            counts = client.rows("SELECT count() AS rows, uniqExact(event_id) AS ids "
                                 "FROM log_events_raw WHERE ingestion_run_id={run:UUID}", params)[0]
            if int(counts["rows"]) != run["expected_rows"] or int(counts["ids"]) != run["expected_rows"]:
                raise ValueError("staged event count/uniqueness check failed; attempt remains unpublished")
            templates = client.rows("SELECT uniqExact(template_id) AS ids FROM event_templates_raw "
                                    "WHERE ingestion_run_id={run:UUID}", params)[0]
            if int(templates["ids"]) != len(catalog):
                raise ValueError("staged template catalog is incomplete")
        for run in runs.values():
            if run is not None:
                client.insert("ingestion_runs", [{**run, "status": "completed"}])
        return result
