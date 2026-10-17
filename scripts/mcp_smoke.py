"""Smoke test an MCP server over streamable HTTP: list tools and call a few.

    python scripts/mcp_smoke.py http://localhost:8000/mcp '["get_invoice", {"customerId": "C1001"}]'
    MCP_AUTH=sigv4 python scripts/mcp_smoke.py <gateway or runtime url> ...
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))


async def main(url: str, calls: list[tuple[str, dict]]):
    auth = None
    if os.environ.get("MCP_AUTH") == "sigv4":
        from conecta_agent.sigv4 import AgentCoreSigV4

        auth = AgentCoreSigV4(os.environ.get("AWS_REGION", "us-east-1"))
    async with streamablehttp_client(url, auth=auth, timeout=60) as (read, write, _):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("tools:", [t.name for t in tools.tools])
            for name, args in calls:
                r = await s.call_tool(name, args)
                text = r.content[0].text if r.content else ""
                print(f"\n>> {name} {args}\n{text[:900]}")


if __name__ == "__main__":
    url = sys.argv[1]
    calls = [tuple(json.loads(c)) for c in sys.argv[2:]]
    asyncio.run(main(url, calls))
