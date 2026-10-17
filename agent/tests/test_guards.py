from types import SimpleNamespace

from conecta_agent.guards import CareGuards
from conecta_agent.verifier import Evidence


def event(name, args, last_user):
    agent = SimpleNamespace(messages=[{"role": "user", "content": [{"text": last_user}]}])
    return SimpleNamespace(agent=agent, tool_use={"name": name, "input": args}, cancel_tool=False)


def guards():
    return CareGuards("C1001", Evidence())


def test_blocks_other_customer():
    e = event("get_invoice", {"customerId": "C1002"}, "muéstrame la factura")
    guards().before_tool(e)
    assert "C1001" in e.cancel_tool


def test_blocks_credit_without_consent():
    e = event("billing___apply_credit", {"customerId": "C1001", "amount": 49.5}, "¿por qué subió mi factura?")
    guards().before_tool(e)
    assert e.cancel_tool


def test_blocks_withdrawn_consent():
    e = event("reboot_modem", {"customer_id": "C1001"}, "no, espera, todavía no")
    guards().before_tool(e)
    assert e.cancel_tool


def test_allows_credit_after_yes():
    e = event("apply_credit", {"customerId": "C1001", "amount": 49.5}, "Sí, aplícalo por favor")
    guards().before_tool(e)
    assert e.cancel_tool is False


def test_plan_change_preview_needs_no_consent():
    e = event("request_plan_change", {"customer_id": "C1001", "plan_id": "MOB-M"}, "¿qué plan me sirve?")
    guards().before_tool(e)
    assert e.cancel_tool is False


def test_plan_change_confirmation_needs_consent():
    e = event("request_plan_change", {"customer_id": "C1001", "plan_id": "MOB-M", "customer_confirmed": True},
              "¿y eso cuánto cuesta?")
    guards().before_tool(e)
    assert e.cancel_tool
