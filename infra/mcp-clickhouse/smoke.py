"""Check the running MCP endpoint, its tools, and database read-only access."""

import asyncio
import json
import os
import urllib.error
import urllib.request

from fastmcp import Client


def decode(result):
    for block in result.content:
        if block.type == "text":
            return json.loads(block.text)
    raise AssertionError("MCP returned no text result")


async def main():
    url = os.getenv("MCP_TEST_URL", "http://127.0.0.1:8000/mcp")
    token = os.environ["CLICKHOUSE_MCP_AUTH_TOKEN"]
    assert token, "CLICKHOUSE_MCP_AUTH_TOKEN is empty"

    # /health is public; the actual MCP endpoint must require authentication.
    request = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    try:
        urllib.request.urlopen(request, timeout=10).close()
    except urllib.error.HTTPError as error:
        assert error.code == 401, f"Expected HTTP 401, got {error.code}"
    else:
        raise AssertionError("MCP accepted a request without a token")
    print("Unauthenticated MCP request: rejected (401)")

    async with Client(url, auth=token) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert {"list_databases", "list_tables", "run_query"} <= names, names
        assert "run_chdb_select_query" not in names, names
        print("MCP tools:", ", ".join(sorted(names)))

        database = os.environ["CLICKHOUSE_DATABASE"]
        await client.call_tool("list_databases", {})
        tables = decode(await client.call_tool("list_tables", {"database": database}))
        print("Database:", database, "Tables:", tables["total_tables"])

        result = decode(await client.call_tool("run_query", {
            "query": "SELECT 1 AS ok, currentUser() AS user, getSetting('readonly') AS readonly"
        }))
        assert result["rows"][0] == [1, "logregartor_mcp", 1], result
        print("SELECT through MCP: passed; dedicated read-only user confirmed")

        # A read-only SELECT attempts to relax the server setting; no data mutation.
        denied = await client.call_tool("run_query", {
            "query": "SELECT 1 SETTINGS readonly = 0"
        }, raise_on_error=False)
        error_text = "\n".join(block.text for block in denied.content if block.type == "text")
        assert denied.is_error and "(READONLY)" in error_text, error_text
        print("Attempt to disable readonly: rejected")


if __name__ == "__main__":
    asyncio.run(main())
