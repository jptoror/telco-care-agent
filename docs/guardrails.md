# Guardrails

Four layers. Each one is plain code, so it behaves the same no matter what the model writes.

| # | Layer | Where | What it stops |
|---|---|---|---|
| 1 | **Scope guard** | Agent, `BeforeToolCallEvent` hook | Any tool call whose `customer_id` / `customerId` is not the authenticated customer. The call is cancelled before it leaves the agent. |
| 2 | **Consent guard** | Agent, `BeforeToolCallEvent` hook | `apply_credit`, `request_plan_change` (when confirmed) and `reboot_modem` unless the customer's last message is an explicit yes and contains no "no". |
| 3 | **Credit policy + server re-check** | Billing MCP, `CreditPolicy` and `apply_credit` | Credits on ineligible lines or with any amount other than lines + 10% tax. Rejected with `expected_amount`. |
| 4 | **Answer verifier** | Agent, after each turn | Amounts that do not appear in tool results, and non-USD currencies. One internal retry, then safe fallback + handoff. |

In production, the customer id would come from a verified JWT claim instead of the request payload.

## Credit policy rules

| Concept | Decision |
|---|---|
| TAX | Never credited directly; added on top of eligible lines. |
| PLAN_FEE | First occurrence is valid; any duplicate in the same invoice is eligible (`DUPLICATE_CHARGE`). |
| PREMIUM_SMS | Eligible on the first dispute (`UNRECOGNIZED_PREMIUM_SMS`); not again if the customer was credited before (`PREMIUM_SMS_REPEAT`). |
| LATE_FEE | Eligible only if the previous invoice was paid on time; otherwise `VALID_LATE_FEE`. |
| ROAMING, PRORATION, DATA_PACK | Not eligible: they are real usage or plan changes. |
| Already credited line | Not eligible again. |

Maximum credit = eligible subtotal + 10% tax, rounded HALF_UP.

## Tool catalog

| Tool | Server | Side effect | Consent |
|---|---|---|---|
| get_customer_profile | Billing (Java) | – | – |
| list_invoices | Billing | – | – |
| get_invoice | Billing | – | – |
| compare_with_previous_invoice | Billing | – | – |
| check_credit_eligibility | Billing | – | – |
| apply_credit | Billing | Writes a credit in DynamoDB | Required |
| get_line_status | Gateway → Lambda network | – | – |
| check_zone_outage | Gateway → Lambda network | – | – |
| run_remote_diagnostic | Gateway → Lambda network | – | – |
| reboot_modem | Gateway → Lambda network | Simulated reboot (5 min state); SKIPPED during an outage | Required |
| list_plans | Gateway → Lambda care | – | – |
| recommend_plan | Gateway → Lambda care | – | – |
| request_plan_change | Gateway → Lambda care | Schedules the change (NEEDS_CONFIRMATION first) | Required |
| create_handoff_ticket | Gateway → Lambda care | Creates a ticket for a human | – |

Gateway tools arrive at the agent as `target___tool` (for example `network___reboot_modem`); the guards and the
Lambda handler strip the prefix.

## What the evals check

Every scenario checks expected tools, forbidden tools, tool arguments, required text and amounts, plus two global
checks: no tool call on another customer, and no leak of the internal verifier instruction ("let me correct my
answer"). Results: 12/12 local and 12/12 on AgentCore.
