"""AgentCore Runtime entrypoint.

Payload: {"prompt": "...", "customer_id": "C1001"}. In production the customer id would come from the
caller's verified identity (a JWT claim), not from the payload.
"""

import logging

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from conecta_agent import config
from conecta_agent.agent import CareSession, mcp_clients

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("conecta")

app = BedrockAgentCoreApp()
_clients = None
_tools = None
_sessions: dict[str, CareSession] = {}


def tools():
    global _clients, _tools
    if _tools is None:
        _clients = mcp_clients()
        for c in _clients:
            c.start()
        _tools = [t for c in _clients for t in c.list_tools_sync()]
        log.info("loaded %d tools: %s", len(_tools), [t.tool_name for t in _tools])
    return _tools


def memory(session_id: str, customer_id: str):
    if not config.MEMORY_ID:
        return None
    from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
    from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

    return AgentCoreMemorySessionManager(
        AgentCoreMemoryConfig(memory_id=config.MEMORY_ID, session_id=session_id, actor_id=customer_id),
        region_name=config.REGION)


@app.entrypoint
def invoke(payload: dict, context=None):
    customer_id = payload.get("customer_id", "")
    prompt = payload.get("prompt", "").strip()
    if not customer_id or not prompt:
        return {"error": "customer_id and prompt are required"}
    session_id = getattr(context, "session_id", None) or f"local-{customer_id}"

    session = _sessions.get(session_id)
    if session and session.customer_id != customer_id:
        return {"error": "session belongs to another customer"}
    if not session:
        session = _sessions[session_id] = CareSession(customer_id, tools(), session_manager=memory(session_id, customer_id))

    r = session.ask(prompt)
    return {"answer": r.text, "verified": r.verified, "verifier_retries": r.retries,
            "unsupported": r.unsupported, "guard_blocks": r.blocked, "tool_calls": r.tool_calls,
            "session_id": session_id}


if __name__ == "__main__":
    app.run()
