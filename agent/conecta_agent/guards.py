"""Deterministic guards around tool calls (Strands hooks)."""

import json
import re

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry

from .verifier import Evidence

# Tools that change something for the customer. Gateway tools arrive as "<target>___<tool>".
SENSITIVE = {"apply_credit", "request_plan_change", "reboot_modem"}
_YES = re.compile(r"\b(s[ií]|yes|yeah|ok|okay|dale|claro|acepto|confirmo|de acuerdo|hazlo|proceed|go ahead|"
                  r"por favor|please)\b", re.IGNORECASE)
_NO = re.compile(r"\b(no|todav[ií]a no|not yet|espera|wait)\b", re.IGNORECASE)


def base_name(tool_name: str) -> str:
    return tool_name.split("___")[-1]


def last_user_text(messages: list) -> str:
    for m in reversed(messages):
        if m["role"] != "user":
            continue
        texts = [c["text"] for c in m["content"] if "text" in c]
        if texts:  # skip tool-result-only user turns
            return " ".join(texts)
    return ""


def tool_result_text(result: dict) -> str:
    parts = []
    for c in result.get("content", []):
        if "text" in c:
            parts.append(c["text"])
        elif "json" in c:
            parts.append(json.dumps(c["json"]))
    return " ".join(parts)


class CareGuards(HookProvider):
    """1) Scope: tools only for the authenticated customer.
    2) Consent: sensitive actions need an explicit yes in the customer's last message.
    3) Evidence: records tool results so the answer verifier can trace every amount."""

    def __init__(self, customer_id: str, evidence: Evidence):
        self.customer_id = customer_id
        self.evidence = evidence
        self.blocked: list[dict] = []

    def register_hooks(self, registry: HookRegistry, **_):
        registry.add_callback(BeforeToolCallEvent, self.before_tool)
        registry.add_callback(AfterToolCallEvent, self.after_tool)

    def before_tool(self, event: BeforeToolCallEvent):
        name = base_name(event.tool_use["name"])
        args = event.tool_use.get("input") or {}
        target = args.get("customer_id") or args.get("customerId")
        if target and target != self.customer_id:
            self._block(event, name, "SCOPE", f"Not allowed: the authenticated customer is {self.customer_id}.")
            return
        needs_consent = name in SENSITIVE and not (name == "request_plan_change"
                                                   and not args.get("customer_confirmed"))
        if needs_consent:
            said = last_user_text(event.agent.messages)
            if not _YES.search(said) or _NO.search(said):
                self._block(event, name, "CONSENT",
                            "Blocked: the customer has not explicitly agreed in their last message. "
                            "Explain what you will do and ask for confirmation first.")

    def after_tool(self, event: AfterToolCallEvent):
        if event.result:
            self.evidence.add_text(tool_result_text(event.result))

    def _block(self, event, name, kind, message):
        self.blocked.append({"tool": name, "kind": kind})
        event.cancel_tool = message
