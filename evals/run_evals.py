"""Runs the scenario suite against the agent and writes evals/report.md + evals/results.json.

    python evals/run_evals.py            # all scenarios
    python evals/run_evals.py zone-outage
"""

import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from conecta_agent.agent import CareSession, mcp_clients  # noqa: E402
from conecta_agent.guards import base_name  # noqa: E402
from conecta_agent.verifier import amounts_in  # noqa: E402

HERE = Path(__file__).parent


def tool_calls(messages) -> list[dict]:
    calls = []
    for m in messages:
        for c in m["content"]:
            if "toolUse" in c:
                calls.append({"name": base_name(c["toolUse"]["name"]), "input": c["toolUse"].get("input") or {}})
    return calls


def executed(messages) -> set[str]:
    """toolUse ids whose result was not a guard cancellation."""
    ok = set()
    for m in messages:
        for c in m["content"]:
            if "toolResult" in c and c["toolResult"].get("status") != "error":
                ok.add(c["toolResult"]["toolUseId"])
    return ok


def matches(args: dict, expected: dict) -> bool:
    for k, v in expected.items():
        got = args.get(k)
        if isinstance(v, float) or isinstance(v, int) and not isinstance(v, bool):
            try:
                if abs(float(got) - float(v)) > 0.001:
                    return False
            except (TypeError, ValueError):
                return False
        elif got != v:
            return False
    return True


def check(sc, messages, final_text) -> list[str]:
    exp, fails = sc["expect"], []
    done = executed(messages)
    calls = []
    for m in messages:
        for c in m["content"]:
            if "toolUse" in c and c["toolUse"]["toolUseId"] in done:
                calls.append({"name": base_name(c["toolUse"]["name"]), "input": c["toolUse"].get("input") or {}})
    names = {c["name"] for c in calls}
    all_text = " ".join(final_text)
    for t in exp.get("tools", []):
        if t not in names:
            fails.append(f"missing tool {t}")
    for t in exp.get("not_tools", []):
        if t in names:
            fails.append(f"forbidden tool {t} ran")
    for t, a in exp.get("tool_args", {}).items():
        if not any(c["name"] == t and matches(c["input"], a) for c in calls):
            fails.append(f"{t} not called with {a}")
    for t, a in exp.get("not_tool_args", {}).items():
        if any(c["name"] == t and matches(c["input"], a) for c in calls):
            fails.append(f"{t} called with forbidden {a}")
    for s in exp.get("contains", []):
        if s not in all_text:
            fails.append(f"answer lacks '{s}'")
    if exp.get("contains_any") and not any(s in all_text for s in exp["contains_any"]):
        fails.append(f"answer lacks any of {exp['contains_any']}")
    said = amounts_in(all_text)
    for a in exp.get("amounts", []):
        if not any(abs(float(x) - a) < 0.001 for x in said):
            fails.append(f"answer lacks amount {a}")
    for s in exp.get("not_contains", []):
        if s.lower() in all_text.lower():
            fails.append(f"answer contains forbidden '{s}'")
    if exp.get("no_tool_args_for_other_customer"):
        cust = sc["customer"]
        if any((c["input"].get("customer_id") or c["input"].get("customerId") or cust) != cust for c in calls):
            fails.append("a tool ran for another customer")
    return fails


def reset_local_state():
    """Credits live in the billing server's memory locally; clear them so scenarios are independent."""
    import urllib.request

    try:
        urllib.request.urlopen(urllib.request.Request("http://localhost:8000/local/credits", method="DELETE"),
                               timeout=3)
    except OSError:
        pass  # remote run: each scenario uses its own customer state


def run(sc, tools) -> dict:
    reset_local_state()
    session = CareSession(sc["customer"], tools)
    answers, blocked, verifier_retries, unverified = [], [], 0, 0
    t0 = time.time()
    for turn in sc["turns"]:
        r = session.ask(turn)
        answers.append(r.text)
        blocked += r.blocked
        verifier_retries += r.retries
        unverified += 0 if r.verified else 1
    elapsed = time.time() - t0
    usage = session.agent.event_loop_metrics.accumulated_usage
    fails = check(sc, session.agent.messages, answers)
    return {"id": sc["id"], "customer": sc["customer"], "passed": not fails, "failures": fails,
            "turns": len(sc["turns"]), "seconds": round(elapsed, 1),
            "input_tokens": usage.get("inputTokens", 0), "output_tokens": usage.get("outputTokens", 0),
            "tools": [c["name"] for c in tool_calls(session.agent.messages)], "guard_blocks": blocked,
            "verifier_retries": verifier_retries, "unverified_answers": unverified,
            "transcript": [{"customer": q, "agent": a} for q, a in zip(sc["turns"], answers)]}


def report(results, model_id) -> str:
    passed = sum(r["passed"] for r in results)
    tin = sum(r["input_tokens"] for r in results)
    tout = sum(r["output_tokens"] for r in results)
    lines = [
        "# Eval report", "",
        f"Model: `{model_id}` · scenarios: {len(results)} · **passed: {passed}/{len(results)}**", "",
        f"Guard blocks: {sum(len(r['guard_blocks']) for r in results)} · verifier retries: "
        f"{sum(r['verifier_retries'] for r in results)} · unverified answers replaced: "
        f"{sum(r['unverified_answers'] for r in results)} · tokens in/out: {tin:,}/{tout:,} · "
        f"avg seconds per turn: {sum(r['seconds'] for r in results) / max(1, sum(r['turns'] for r in results)):.1f}",
        "", "| Scenario | Customer | Result | Tools used | Guards | Seconds |", "|---|---|---|---|---|---|",
    ]
    for r in results:
        guards = ", ".join(f"{b['tool']}/{b['kind']}" for b in r["guard_blocks"]) or "-"
        res = "PASS" if r["passed"] else "FAIL: " + "; ".join(r["failures"])
        lines.append(f"| {r['id']} | {r['customer']} | {res} | {', '.join(dict.fromkeys(r['tools']))} | "
                     f"{guards} | {r['seconds']} |")
    lines += ["", "## Transcripts", ""]
    for r in results:
        lines.append(f"### {r['id']} ({r['customer']})")
        for t in r["transcript"]:
            lines += [f"> **Customer:** {t['customer']}", ">", f"> **Coni:** {t['agent']}", ""]
    return "\n".join(lines)


def main(only: list[str]):
    from conecta_agent import config

    scenarios = yaml.safe_load((HERE / "scenarios.yaml").read_text())
    if only:
        scenarios = [s for s in scenarios if s["id"] in only]
    clients = mcp_clients()
    for c in clients:
        c.start()
    try:
        tools = [t for c in clients for t in c.list_tools_sync()]
        results = []
        for sc in scenarios:
            r = run(sc, tools)
            print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['id']:28s} {r['seconds']:5.1f}s  {r['failures']}")
            results.append(r)
    finally:
        for c in clients:
            c.stop(None, None, None)
    (HERE / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    (HERE / "report.md").write_text(report(results, config.MODEL_ID))
    print(f"\n{sum(r['passed'] for r in results)}/{len(results)} passed -> evals/report.md")


if __name__ == "__main__":
    main(sys.argv[1:])
