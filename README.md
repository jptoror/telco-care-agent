# Conecta Care Agent

A customer-care AI agent for a (fictional) telecom operator, built on **Amazon Bedrock AgentCore** with
**MCP** tools. It answers billing questions, troubleshoots home internet, recommends plans and issues
credits — and it is designed around one rule:

> **The LLM proposes, deterministic code decides.** The model never decides an amount or takes an action on
> its own: a credit policy computes what can be credited, the server re-checks it, guards enforce scope and
> consent, and a verifier rejects any answer whose amounts cannot be traced to tool results.

## Architecture

```
customer ──► Agent (Strands, AgentCore Runtime, Claude on Bedrock)
               │  hooks: scope guard · consent guard · evidence recorder
               │  answer verifier (amounts must be traceable, USD only) ─► retry ─► safe fallback + handoff
               │
               ├── MCP: billing (Java 21 · Spring AI) ──► Athena ─► Glue catalog ─► S3 (invoices, lines)
               │      deterministic CreditPolicy · apply_credit re-validates · DynamoDB credits
               │
               └── MCP: AgentCore Gateway ──► Lambda network (line status, outages, diagnostic, reboot)
                                           └► Lambda care (plans, recommendation, plan change, handoff)
```

| Path | What |
|---|---|
| `data/generate.py` | Synthetic dataset: 198 customers, 3 months of invoices, usage, devices, outages. Customers C1001–C1008 carry seeded cases. |
| `mcp-billing-java/` | Billing MCP server (Spring Boot 3.5, Spring AI 1.1 `@McpTool`, stateless streamable HTTP). CSV locally, Athena + DynamoDB on AWS. |
| `tools/` | Network and care tools: AgentCore Gateway Lambda handler, and a local MCP server for development. |
| `agent/` | Strands agent, guards, grounding verifier, local CLI. |
| `evals/` | Scripted multi-turn scenarios with deterministic checks; writes `evals/report.md`. |

## Run locally

```bash
uv venv && uv pip install -e . pytest      # Python 3.12
python data/generate.py
(cd mcp-billing-java && mvn -q package -DskipTests && java -jar target/mcp-billing-0.1.0.jar)   # :8000/mcp
python tools/local_mcp.py                                                                        # :8001/mcp
python agent/cli.py C1001                  # chat as customer C1001 (needs AWS credentials for Bedrock)
python evals/run_evals.py                  # eval suite -> evals/report.md
pytest && (cd mcp-billing-java && mvn -q test)
```

## Seeded cases

| Customer | Situation | Expected behaviour |
|---|---|---|
| C1001 | Plan fee charged twice | Explain, offer exactly $49.50 (fee + tax), apply after a yes |
| C1002 | Roaming in the US (EN) | Explain the usage charges, no credit |
| C1003 | No internet | Zone outage: give cause and ETA, do not reboot |
| C1004 | Slow internet | Modem degraded: offer and run a remote reboot after consent |
| C1005 | Pays for 1 Gbps, uses little | Recommend 300 Mbps, change only after explicit confirmation |
| C1006 | Unknown premium SMS | First dispute: credit $16.47 |
| C1007 | Late fee (EN) | Legit (paid after due date), explain kindly |
| C1008 | Proration after upgrade | Explain, no credit |
