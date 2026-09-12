"""Produce UI contract fixtures using the real Analytics runner, without a database."""
import json
import sys
from pathlib import Path

analytics = Path(__file__).resolve().parents[2] / "Analytics"
sys.path[:0] = [str(analytics), str(analytics / "tests")]
from log_analytics.baseline import RunConfig
from log_analytics.runner import run
from log_analytics.storage import Store
from support import MemoryClient

client = MemoryClient()
report = run(client, RunConfig("test", 30))
card = report["incidents"][0]
store = Store(client)
print(json.dumps({"report": report, "card": card,
                  "timeline": store.incident(card["incident_id"])[1],
                  "event": store.event(card["evidence_ids"][0])}))
