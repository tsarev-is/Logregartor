"""Small read-only ASGI application; uvicorn is an optional CLI dependency."""

import asyncio
import json
import re
import uuid
from urllib.parse import parse_qs

from .clickhouse import ClickHouseError
from .storage import NotFound, Store


class Application:
    def __init__(self, client):
        self.store = Store(client)

    def dispatch(self, method, path, query):
        if method != "GET":
            return 405, {"detail": "method not allowed"}
        try:
            params = parse_qs(query, keep_blank_values=True)
            run = None
            if "analysis_run_id" in params:
                if len(params["analysis_run_id"]) != 1:
                    raise ValueError("provide one analysis_run_id")
                try:
                    run = str(uuid.UUID(params["analysis_run_id"][0]))
                except ValueError as exc:
                    raise ValueError("invalid analysis_run_id") from exc
            if path == "/v1/incidents":
                dataset = params.get("dataset_id", [])
                if len(dataset) != 1 or not dataset[0].strip():
                    raise ValueError("dataset_id is required exactly once")
                if run is not None:
                    raise ValueError("the incident list always returns the current dataset publication")
                return 200, self.store.current_report(dataset[0])
            match = re.fullmatch(r"/v1/(incidents|events)/([^/]+)(/timeline)?", path)
            if not match:
                return 404, {"detail": "endpoint not found"}
            kind, identifier, timeline = match.groups()
            if not re.fullmatch(r"[0-9a-f]{64}", identifier):
                raise ValueError("ID must be a lowercase SHA-256 hex string")
            if kind == "events":
                if timeline:
                    return 404, {"detail": "endpoint not found"}
                return 200, self.store.event(identifier, run)
            card, events = self.store.incident(identifier, run)
            return 200, events if timeline else card
        except NotFound as exc:
            return 404, {"detail": str(exc)}
        except ClickHouseError:
            return 503, {"detail": "Analytics database or schema unavailable"}
        except ValueError as exc:
            return 422, {"detail": str(exc)}

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        status, result = await asyncio.to_thread(
            self.dispatch, scope["method"], scope["path"], scope.get("query_string", b"").decode("latin-1"))
        body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
        headers = [(b"content-type", b"application/json; charset=utf-8"),
                   (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]
        if status == 405:
            headers.append((b"allow", b"GET"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def serve(client, host, port):
    try:
        import uvicorn
    except ImportError as exc:
        raise ValueError("serve requires the optional API dependency: pip install -e '.[api]'") from exc
    client.migrate()
    uvicorn.run(Application(client), host=host, port=port)
