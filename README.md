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
| `evals/` | Scripted multi-turn scenarios with deterministic checks; `report.md` (local) and `report-remote.md` (AgentCore). |
| `infra/` | Terraform (us-east-1): S3, Glue, Athena, DynamoDB, Lambdas, AgentCore Gateway, Runtimes, Memory, ECR, Transaction Search. |

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

## Deploy to AWS

```bash
./scripts/deploy.sh                               # ECR -> arm64 images -> terraform apply (idempotent)
python scripts/invoke.py C1004 "El internet va lento" "Sí, reinícialo"
python evals/run_evals.py --remote                # same suite against AgentCore Runtime
terraform -chdir=infra destroy                    # tear everything down
```

What gets deployed (all in `us-east-1`, tagged `Project=conecta-care-agent`):

- **Data:** CSVs in S3 → Glue tables (OpenCSVSerde) → Athena workgroup with a 100 MB per-query cutoff.
  Billing queries use Athena execution parameters, never string concatenation.
- **Billing MCP:** the Java server as an AgentCore Runtime (`server_protocol = MCP`), reading Athena and
  writing credits to DynamoDB, with a least-privilege role.
- **Care tools:** two Lambdas behind an **AgentCore Gateway** (MCP, IAM/SigV4 inbound auth), one target each.
- **Agent:** Strands in an AgentCore Runtime (HTTP), short-term **AgentCore Memory** per customer session,
  SigV4-signed MCP calls to the Gateway and the billing runtime, OpenTelemetry (ADOT) traces into CloudWatch
  GenAI Observability via Transaction Search.

## Results

| | Local | AgentCore Runtime |
|---|---|---|
| Scenarios passed | 12/12 | 12/12 |
| Avg seconds per turn | ~3 | ~8 (includes microVM cold starts and Athena) |
| Model | Claude Haiku 4.5 (Bedrock) | Claude Haiku 4.5 (Bedrock) |

Unit tests: 11 Python (guards, verifier) + 5 Java (credit policy).

### What the evals caught (and what changed)

1. **Wrong currency.** The first run answered "49,50 €" — the numbers were right, the currency was not, and the
   verifier missed it. Now the prompt pins USD and the verifier rejects any non-USD currency.
2. **A leaking self-correction.** When the verifier sent an answer back, the agent told the customer "let me
   correct my answer". The retry instruction now asks for a clean rewrite, and every eval checks for leaks.
3. **Conservative by design.** The verifier rejects amounts the customer mentioned ("give me $100") because they
   are not backed by a tool result. That costs one retry; the alternative is an agent repeating unvalidated numbers.

## Design decisions

- **Two layers of protection for money.** The agent-side verifier keeps the *answer* honest; the server-side
  `apply_credit` re-runs the policy so even a misbehaving agent cannot issue a wrong credit.
- **Consent is checked in code.** Credits, plan changes and reboots are cancelled by a hook unless the
  customer's last message is an explicit yes; withdrawing consent ("no, espera") also blocks.
- **Scope is checked in code.** Every tool call is pinned to the authenticated customer; prompt injection asking
  for another account gets nothing. In production the customer id would come from a verified JWT claim.
- **Java where the backend lives.** Telco billing systems are usually JVM; the billing MCP shows how an existing
  Spring service can be exposed to agents with `@McpTool` without rewriting it.

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
