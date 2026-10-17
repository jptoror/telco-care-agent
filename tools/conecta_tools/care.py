"""Customer care tools: plan catalog, plan recommendation, plan change and human handoff."""

import uuid
from datetime import date, timedelta

from . import data

TODAY = date(2026, 10, 17)  # the synthetic dataset is frozen on this day


def _plan(plan_id: str) -> dict:
    p = data.one("plans", plan_id=plan_id)
    if not p:
        raise ValueError(f"Unknown plan {plan_id}")
    return p


def list_plans(kind: str = "") -> list[dict]:
    """Plan catalog. kind: 'mobile', 'home' or empty for all."""
    return [p for p in data.table("plans") if not kind or p["kind"] == kind]


def recommend_plan(customer_id: str) -> dict:
    """Recommends the cheapest plan that fits the customer's real usage over the last 30 days."""
    c = data.customer(customer_id)
    current = _plan(c["plan_id"])
    usage = sorted(data.where("usage_daily", customer_id=customer_id), key=lambda r: r["date"])[-30:]
    if not usage:
        return {"current_plan": current, "recommendation": None, "reason": "No usage data for this customer."}
    avg_gb_day = sum(int(u["data_mb"]) for u in usage) / len(usage) / 1024
    roaming_days = sum(1 for u in usage if int(u["roaming_mb"]) > 0)
    candidates = sorted(list_plans(current["kind"]), key=lambda p: float(p["monthly_fee"]))
    if current["kind"] == "home":
        need_mbps = 100 if avg_gb_day < 2 else 300 if avg_gb_day < 8 else 1000
        fit = next(p for p in candidates if int(p["speed_mbps"]) >= need_mbps)
        basis = f"average {avg_gb_day:.1f} GB/day at home -> {need_mbps} Mbps is enough"
    else:
        need_gb = avg_gb_day * 30 * 1.2
        fit = next(p for p in candidates if int(p["data_gb"]) >= need_gb
                   and (roaming_days < 3 or p["roaming_included"] == "true"))
        basis = f"projected {avg_gb_day * 30:.0f} GB/month, {roaming_days} roaming days"
    saving = round(float(current["monthly_fee"]) - float(fit["monthly_fee"]), 2)
    return {"current_plan": current, "recommendation": fit if fit["plan_id"] != current["plan_id"] else None,
            "monthly_saving_before_tax": saving, "basis": basis}


def request_plan_change(customer_id: str, plan_id: str, customer_confirmed: bool = False) -> dict:
    """Changes the customer's plan. First call without confirmation to get the summary to read to the
    customer; call again with customer_confirmed=true only after the customer explicitly accepts."""
    c = data.customer(customer_id)
    new, old = _plan(plan_id), _plan(c["plan_id"])
    if new["kind"] != old["kind"]:
        return {"status": "REJECTED", "reason": f"Cannot change a {old['kind']} plan to a {new['kind']} plan."}
    effective = (TODAY.replace(day=1) + timedelta(days=32)).replace(day=1)
    summary = {"from_plan": old["name"], "to_plan": new["name"], "new_monthly_fee": new["monthly_fee"],
               "effective_date": effective.isoformat(), "no_penalty": True}
    if not customer_confirmed:
        return {"status": "NEEDS_CONFIRMATION", **summary}
    return {"status": "SCHEDULED", "order_id": f"ORD-{uuid.uuid4().hex[:8].upper()}", **summary}


def create_handoff_ticket(customer_id: str, reason: str, summary: str) -> dict:
    """Escalates to a human agent with a summary so the customer does not have to repeat anything."""
    data.customer(customer_id)
    return {"ticket_id": f"TCK-{uuid.uuid4().hex[:6].upper()}", "queue": "human-care",
            "expected_contact": "within 2 hours", "reason": reason, "summary": summary}


TOOLS = [list_plans, recommend_plan, request_plan_change, create_handoff_ticket]
