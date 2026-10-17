"""Runs the scenario suite and writes evals/report.md + evals/results.json.

    python evals/run_evals.py                    # local agent (MCP servers on :8000 / :8001)
    python evals/run_evals.py zone-outage
    python evals/run_evals.py --remote           # deployed agent on AgentCore Runtime
"""

import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from conecta_agent.agent import CareSession, mcp_clients  # noqa: E402
from conecta_agent.verifier import amounts_in  # noqa: E402

HERE = Path(__file__).parent


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


def check(sc, calls, final_text) -> list[str]:
    exp, fails = sc["expect"], []
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
    leaks = ("corregir mi respuesta", "correct my answer", "corrijo", "VERIFIER", "verificador")
    for s in [*exp.get("not_contains", []), *leaks]:
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


class LocalTarget:
    def __init__(self):
        self.clients = mcp_clients()
        for c in self.clients:
            c.start()
        self.tools = [t for c in self.clients for t in c.list_tools_sync()]

    def new_session(self, customer_id):
        reset_local_state()
        session = CareSession(customer_id, self.tools)

        def ask(prompt):
            r = session.ask(prompt)
            return {"answer": r.text, "verified": r.verified, "verifier_retries": r.retries,
                    "guard_blocks": r.blocked, "tool_calls": r.tool_calls}
        return ask, lambda: session.agent.event_loop_metrics.accumulated_usage

    def close(self):
        for c in self.clients:
            c.stop(None, None, None)


class RemoteTarget:
    """Each scenario gets a fresh AgentCore session (its own microVM)."""

    def __init__(self):
        import subprocess
        import boto3
        from botocore.config import Config

        self.arn = subprocess.check_output(["terraform", "-chdir=infra", "output", "-raw", "agent_runtime_arn"],
                                           text=True, cwd=HERE.parent)
        self.client = boto3.client("bedrock-agentcore", region_name="us-east-1",
                                   config=Config(read_timeout=180, retries={"max_attempts": 2}))
        self.credits = boto3.resource("dynamodb", region_name="us-east-1").Table("conecta-credits")

    def reset_customer(self, customer_id):
        """Demo environment: start each scenario without credits issued by earlier runs."""
        from boto3.dynamodb.conditions import Key

        items = self.credits.query(KeyConditionExpression=Key("customer_id").eq(customer_id))["Items"]
        for it in items:
            self.credits.delete_item(Key={"customer_id": customer_id, "credit_id": it["credit_id"]})

    def new_session(self, customer_id):
        import uuid

        self.reset_customer(customer_id)
        sid = f"eval-{customer_id}-{uuid.uuid4()}"

        def ask(prompt):
            r = self.client.invoke_agent_runtime(agentRuntimeArn=self.arn, runtimeSessionId=sid, qualifier="DEFAULT",
                                                 payload=json.dumps({"customer_id": customer_id, "prompt": prompt}))
            return json.loads(r["response"].read())
        return ask, lambda: {}

    def close(self):
        pass


def run(sc, target) -> dict:
    ask, usage_of = target.new_session(sc["customer"])
    answers, calls, blocked, verifier_retries, unverified = [], [], [], 0, 0
    t0 = time.time()
    for turn in sc["turns"]:
        r = ask(turn)
        answers.append(r.get("answer", json.dumps(r)))
        calls += r.get("tool_calls", [])
        blocked += r.get("guard_blocks", [])
        verifier_retries += r.get("verifier_retries", 0)
        unverified += 0 if r.get("verified", False) else 1
    elapsed = time.time() - t0
    usage = usage_of()
    fails = check(sc, calls, answers)
    return {"id": sc["id"], "customer": sc["customer"], "passed": not fails, "failures": fails,
            "turns": len(sc["turns"]), "seconds": round(elapsed, 1),
            "input_tokens": usage.get("inputTokens", 0), "output_tokens": usage.get("outputTokens", 0),
            "tools": [c["name"] for c in calls], "guard_blocks": blocked,
            "verifier_retries": verifier_retries, "unverified_answers": unverified,
            "transcript": [{"customer": q, "agent": a} for q, a in zip(sc["turns"], answers)]}


def report(results, model_id, where) -> str:
    passed = sum(r["passed"] for r in results)
    tin = sum(r["input_tokens"] for r in results)
    tout = sum(r["output_tokens"] for r in results)
    lines = [
        "# Eval report", "",
        f"Target: {where} · model: `{model_id}` · scenarios: {len(results)} · "
        f"**passed: {passed}/{len(results)}**", "",
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


def main(args: list[str]):
    from conecta_agent import config

    remote = "--remote" in args
    only = [a for a in args if not a.startswith("--")]
    scenarios = yaml.safe_load((HERE / "scenarios.yaml").read_text())
    if only:
        scenarios = [s for s in scenarios if s["id"] in only]
    target = RemoteTarget() if remote else LocalTarget()
    try:
        results = []
        for sc in scenarios:
            r = run(sc, target)
            print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['id']:28s} {r['seconds']:5.1f}s  {r['failures']}")
            results.append(r)
    finally:
        target.close()
    suffix = "-remote" if remote else ""
    where = "AgentCore Runtime (us-east-1)" if remote else "local"
    (HERE / f"results{suffix}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    (HERE / f"report{suffix}.md").write_text(report(results, config.MODEL_ID, where))
    print(f"\n{sum(r['passed'] for r in results)}/{len(results)} passed -> evals/report{suffix}.md")


if __name__ == "__main__":
    main(sys.argv[1:])
