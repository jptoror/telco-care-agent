"""Smoke test an MCP server over streamable HTTP: list tools and call a few.

    python scripts/mcp_smoke.py http://localhost:8000/mcp
"""
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main(url: str, calls: list[tuple[str, dict]]):
    async with streamablehttp_client(url) as (read, write, _):
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
