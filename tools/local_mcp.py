"""Serves the network + care tools as one MCP server for local development (stand-in for the Gateway).

    python tools/local_mcp.py   # http://localhost:8001/mcp
"""

from mcp.server.fastmcp import FastMCP

from conecta_tools import care, network

mcp = FastMCP("conecta-care-tools", host="127.0.0.1", port=8001, stateless_http=True)
for fn in network.TOOLS + care.TOOLS:
    mcp.add_tool(fn)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
