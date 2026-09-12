import io
import json
import unittest
import urllib.error
import urllib.parse
from unittest.mock import MagicMock

from log_analytics.clickhouse import ClickHouse, ClickHouseError, NoRedirect


class HttpAdapterTests(unittest.TestCase):
    def client(self, body=b'{"value": 1}\n', headers=None):
        client = ClickHouse("http://localhost:8123", "logs", "user", "password")
        response = MagicMock()
        response.read.return_value = body
        response.headers = headers or {}
        client.opener = MagicMock()
        client.opener.open.return_value.__enter__.return_value = response
        return client

    def test_query_values_are_parameters_and_credentials_are_headers(self):
        client = self.client()
        dataset = "dataset' OR 1=1 -- & ?"
        sql = "SELECT value FROM log_events WHERE dataset_id={dataset:String}"
        self.assertEqual(client.rows(sql, {"dataset": dataset}), [{"value": 1}])
        request = client.opener.open.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        self.assertEqual(query["param_dataset"], [dataset])
        self.assertEqual(query["wait_end_of_query"], ["1"])
        self.assertEqual(query["async_insert"], ["0"])
        self.assertEqual(request.data.decode(), sql + " FORMAT JSONEachRow")
        self.assertNotIn("password", request.full_url)
        self.assertIn("Authorization", request.headers)

    def test_insert_json_each_row_is_not_retried(self):
        client = self.client(b"")
        row = {"raw_text": "quotes '\" and newline\n", "value": 0}
        client.insert("incident_evidence_raw", [row])
        request = client.opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data), row)
        self.assertIn("INSERT INTO incident_evidence_raw FORMAT JSONEachRow", urllib.parse.unquote_plus(request.full_url))
        client.opener.open.reset_mock()
        client.opener.open.side_effect = OSError("lost response")
        with self.assertRaises(ClickHouseError):
            client.insert("incident_evidence_raw", [row])
        client.opener.open.assert_called_once()

    def test_late_error_or_malformed_json_never_returns_partial_rows(self):
        for body, headers in ((b'{"value": 1}\nDB::Exception', {}),
                              (b'{"value": 1}\n', {"X-ClickHouse-Exception-Code": "123"}),
                              (b'[]\n', {})):
            with self.subTest(body=body), self.assertRaises(ClickHouseError):
                self.client(body, headers).rows("SELECT value")

    def test_http_error_does_not_echo_records_and_redirects_are_rejected(self):
        client = self.client()
        client.opener.open.side_effect = urllib.error.HTTPError(
            client.url, 500, "error", {}, io.BytesIO(b"sensitive source content"))
        with self.assertRaises(ClickHouseError) as error:
            client.rows("SELECT value")
        self.assertNotIn("sensitive", str(error.exception))
        with self.assertRaises(ClickHouseError):
            NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://elsewhere")

    def test_invalid_configuration_and_table(self):
        for url, db, timeout in (("file:///tmp/file", "logs", 60),
                                 ("http://u:p@localhost", "logs", 60),
                                 ("http://localhost?query=x", "logs", 60),
                                 ("http://localhost", "logs; DROP DATABASE logs", 60),
                                 ("http://localhost", "logs", float("nan")),
                                 ("http://localhost", "logs", 0)):
            with self.subTest(url=url, db=db, timeout=timeout), self.assertRaises(ValueError):
                ClickHouse(url, db, "user", "password", timeout)
        with self.assertRaises(ValueError):
            self.client().insert("log_events_raw", [{"value": 1}])
