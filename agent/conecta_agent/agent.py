"""One care session = one Strands agent bound to one authenticated customer."""

import logging
from dataclasses import dataclass, field

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

from . import config
from .guards import CareGuards
from .prompts import SYSTEM_PROMPT
from .verifier import Evidence

log = logging.getLogger(__name__)

FALLBACK = {
    "es": "Quiero darte un dato exacto y no pude confirmarlo. Ya dejé tu caso a un asesor humano con todo el "
          "detalle; te contactará pronto.",
    "en": "I want to give you an exact figure and could not confirm it. I've passed your case to a human "
          "agent with all the details; they'll contact you shortly.",
}


def mcp_clients(headers: dict | None = None) -> list[MCPClient]:
    return [MCPClient(lambda url=url: streamablehttp_client(url, headers=headers or {}))
            for url in (config.BILLING_MCP_URL, config.CARE_MCP_URL)]


@dataclass
class TurnResult:
    text: str
    verified: bool
    retries: int
    unsupported: list = field(default_factory=list)
    blocked: list = field(default_factory=list)


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
        text = str(self.agent(message)).strip()
        retries = 0
        bad = self.evidence.unsupported(text)
        while bad and retries < config.VERIFIER_RETRIES:
            retries += 1
            log.warning("verifier rejected amounts %s", bad)
            text = str(self.agent(
                "[VERIFIER — not from the customer] Your previous answer mentions amounts that do not appear "
                f"in any tool result or use the wrong currency: {', '.join(bad)}. Check the tools again and rewrite "
                "the answer for the customer using only traceable amounts in US dollars ($).")).strip()
            bad = self.evidence.unsupported(text)
        if bad:
            return TurnResult(FALLBACK.get(self.language, FALLBACK["es"]), False, retries, bad,
                              list(self.guards.blocked))
        return TurnResult(text, True, retries, [], list(self.guards.blocked))
