"""Local chat with the agent (needs both MCP servers running and AWS credentials for Bedrock).

    python agent/cli.py C1001
"""

import sys

from conecta_agent.agent import CareSession, mcp_clients


def main(customer_id: str):
    clients = mcp_clients()
    for c in clients:
        c.start()
    try:
        tools = [t for c in clients for t in c.list_tools_sync()]
        session = CareSession(customer_id, tools)
        print(f"Coni para {customer_id} ({len(tools)} herramientas). Ctrl+C para salir.\n")
        while True:
            msg = input("cliente> ").strip()
            if not msg:
                continue
            r = session.ask(msg)
            flags = [] if r.verified else [f"NO VERIFICADO {r.unsupported}"]
            flags += [f"reintentos={r.retries}"] if r.retries else []
            flags += [f"bloqueado:{b['tool']}/{b['kind']}" for b in r.blocked]
            print(f"\nconi> {r.text}" + (f"\n      [{'; '.join(flags)}]" if flags else "") + "\n")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        for c in clients:
            c.stop(None, None, None)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "C1001")
