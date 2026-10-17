"""One care session = one Strands agent bound to one authenticated customer."""

import logging
from dataclasses import dataclass, field

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

from . import config
from .guards import CareGuards, base_name
from .prompts import SYSTEM_PROMPT
from .verifier import Evidence

log = logging.getLogger(__name__)

FALLBACK = {
    "es": "Quiero darte un dato exacto y no pude confirmarlo. Ya dejé tu caso a un asesor humano con todo el "
          "detalle; te contactará pronto.",
    "en": "I want to give you an exact figure and could not confirm it. I've passed your case to a human "
          "agent with all the details; they'll contact you shortly.",
}


def mcp_clients() -> list[MCPClient]:
    """Billing MCP (Java) and care tools (Gateway on AWS, local MCP server in development)."""
    auth = None
    if config.MCP_AUTH == "sigv4":
        from .sigv4 import AgentCoreSigV4

        auth = AgentCoreSigV4(config.REGION)
    return [MCPClient(lambda url=url: streamablehttp_client(url, auth=auth, timeout=60))
            for url in (config.BILLING_MCP_URL, config.CARE_MCP_URL)]


@dataclass
class TurnResult:
    text: str
    verified: bool
    retries: int
    unsupported: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)


class CareSession:
    def __init__(self, customer_id: str, tools: list, language: str = "es", session_manager=None):
        self.customer_id = customer_id
        self.language = language
        self.evidence = Evidence()
        self.guards = CareGuards(customer_id, self.evidence)
        self.agent = Agent(
            model=BedrockModel(model_id=config.MODEL_ID, region_name=config.REGION, temperature=0.2),
            system_prompt=SYSTEM_PROMPT.format(customer_id=customer_id),
            tools=tools,
            hooks=[self.guards],
            callback_handler=None,
            session_manager=session_manager,
            trace_attributes={"customer.id": customer_id},
        )

    def ask(self, message: str) -> TurnResult:
        self.guards.blocked.clear()
        start = len(self.agent.messages)
        text = str(self.agent(message)).strip()
        retries = 0
        bad = self.evidence.unsupported(text)
        while bad and retries < config.VERIFIER_RETRIES:
            retries += 1
            log.warning("verifier rejected amounts %s", bad)
            text = str(self.agent(
                "[VERIFIER — internal, the customer cannot see this message] Your previous answer mentions "
                f"amounts that do not appear in any tool result or use the wrong currency: {', '.join(bad)}. "
                "Write the answer again from scratch, in US dollars and only with amounts returned by tools. "
                "If you need to refer to an amount the customer asked for, do it without the number. Output "
                "only the new customer-facing answer; do not apologize for or mention any correction.")).strip()
            bad = self.evidence.unsupported(text)
        calls = executed_tool_calls(self.agent.messages[start:])
        if bad:
            return TurnResult(FALLBACK.get(self.language, FALLBACK["es"]), False, retries, bad,
                              list(self.guards.blocked), calls)
        return TurnResult(text, True, retries, [], list(self.guards.blocked), calls)


def executed_tool_calls(messages: list) -> list[dict]:
    """Tool calls that actually ran (guard-cancelled calls come back as error results)."""
    ok = {c["toolResult"]["toolUseId"] for m in messages for c in m["content"]
          if "toolResult" in c and c["toolResult"].get("status") != "error"}
    return [{"name": base_name(c["toolUse"]["name"]), "input": c["toolUse"].get("input") or {}}
            for m in messages for c in m["content"] if "toolUse" in c and c["toolUse"]["toolUseId"] in ok]
