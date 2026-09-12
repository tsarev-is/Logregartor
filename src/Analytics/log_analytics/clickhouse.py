"""Independent ClickHouse HTTP adapter; no LogParser package dependency."""

import base64
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from importlib.resources import files


class ClickHouseError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ClickHouseError("ClickHouse redirects are not supported")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ClickHouse:
    def __init__(self, url, database, user, password, timeout=60):
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError("CLICKHOUSE_URL must be HTTP(S) without credentials, query or fragment")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
            raise ValueError("invalid CLICKHOUSE_DB")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("CLICKHOUSE_TIMEOUT must be finite and positive")
        self.url, self.database, self.timeout = url.rstrip("/"), database, timeout
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.opener = urllib.request.build_opener(NoRedirect())

    @classmethod
    def from_env(cls):
        return cls(os.getenv("CLICKHOUSE_URL", "http://localhost:8123"),
                   os.getenv("CLICKHOUSE_DB", "logs"), os.getenv("CLICKHOUSE_USER", "logregartor"),
                   os.getenv("CLICKHOUSE_PASSWORD", "localdev"), float(os.getenv("CLICKHOUSE_TIMEOUT", "60")))

    def execute(self, sql, params=None, data=None, use_database=True):
        query = {"wait_end_of_query": "1", "async_insert": "0",
                 "date_time_input_format": "best_effort", "output_format_json_quote_64bit_integers": "0"}
        if use_database:
            query["database"] = self.database
        for name, value in (params or {}).items():
            query["param_" + name] = str(value)
        if data is not None:
            query["query"] = sql
        request = urllib.request.Request(self.url + "/?" + urllib.parse.urlencode(query),
                                         data=sql.encode() if data is None else data,
                                         headers={"Authorization": self.auth,
                                                  "Content-Type": "application/octet-stream"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                result = response.read().decode("utf-8")
                if response.headers.get("X-ClickHouse-Exception-Code"):
                    raise ClickHouseError("ClickHouse query failed")
                return result
        except urllib.error.HTTPError as exc:
            # Do not expose query fragments or source records from a database error.
            exc.close()
            raise ClickHouseError(f"ClickHouse HTTP {exc.code}; check database schema and access") from exc
        except (urllib.error.URLError, OSError, UnicodeError) as exc:
            # An INSERT may have succeeded despite a lost response. Never retry it here.
            raise ClickHouseError("ClickHouse request failed; rerun analysis to recover an interrupted attempt") from exc

    def rows(self, sql, params=None):
        try:
            result = [json.loads(line) for line in self.execute(sql + " FORMAT JSONEachRow", params).splitlines() if line]
            if any(not isinstance(row, dict) for row in result):
                raise ValueError("expected objects")
            return result
        except ValueError as exc:
            raise ClickHouseError("invalid ClickHouse JSONEachRow response") from exc

    def insert(self, table, rows):
        if table not in {"analysis_runs", "incidents_raw", "incident_evidence_raw"}:
            raise ValueError("unexpected Analytics insertion table")
        if rows:
            self.execute(f"INSERT INTO {table} FORMAT JSONEachRow",
                         data=("\n".join(canonical(row) for row in rows) + "\n").encode())

    def migrate(self):
        self.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}`", use_database=False)
        directory = files("log_analytics").joinpath("sql")
        for migration in sorted(directory.iterdir(), key=lambda path: path.name):
            if migration.name.endswith(".sql"):
                for statement in migration.read_text().split(";"):
                    if statement.strip():
                        self.execute(statement)
