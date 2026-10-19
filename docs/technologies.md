# Technologies

What each piece does in this project, and what it is good for in general.

## Agent layer

| Technology | Role here | Good for |
|---|---|---|
| **Claude Haiku 4.5 on Amazon Bedrock** | The model: understands the customer, picks tools, writes the answer. | Fast, cheap tool use with managed access, IAM and no data leaving AWS. |
| **Strands Agents** (Python) | The agent loop: model ↔ tools, hooks, metrics. | Building tool-using agents with little code; hooks let you put deterministic checks around every tool call. |
| **MCP** (Model Context Protocol) | How the agent discovers and calls tools (streamable HTTP). | One standard interface so tools written in any language plug into any agent. |
| **Spring AI** (`@McpTool`) | Turns Java methods into MCP tools in the billing server. | Exposing existing Spring services to agents without rewriting them. |

## AgentCore

| Service | Role here | Good for |
|---|---|---|
| **AgentCore Runtime** | Hosts the agent (HTTP) and the Java billing server (MCP) as arm64 containers. One microVM per session. | Running agents and tool servers serverless, with session isolation and IAM. |
| **AgentCore Gateway** | Publishes two Lambdas as one MCP server; IAM inbound auth. | Turning existing APIs and Lambdas into MCP tools with central auth and schemas. |
| **AgentCore Memory** | Short-term conversation memory per customer session. | Keeping context across turns and restarts without running your own store. |
| **AgentCore Observability** | Traces of model calls and tool calls (via ADOT). | Seeing what the agent did, step by step, in CloudWatch GenAI Observability. |

## Data and compute

| Technology | Role here | Good for |
|---|---|---|
| **S3** | Stores the CSV tables. | Cheap durable storage; the base of a data lake. |
| **Glue Data Catalog** | Table definitions over the CSVs (OpenCSVSerde). | Giving files a schema so SQL engines can query them. |
| **Athena** | SQL over S3 for the billing server, with execution parameters and a 100 MB scan cap. | Serverless SQL on files; pay per scanned byte. |
| **DynamoDB** | Stores applied credits (customer_id + credit_id). | Low-latency key-value writes with no servers. |
| **Lambda** | Network and care tools behind the Gateway. | Small stateless functions that scale to zero. |
| **ECR** | Immutable image repositories for both containers. | Private container registry with lifecycle rules. |

## Languages and frameworks

| Technology | Role here | Good for |
|---|---|---|
| **Java 21 + Spring Boot 3.5** | Billing MCP server, CreditPolicy, Athena and DynamoDB adapters. | Typed, testable business rules; where most telco billing backends already live. |
| **Python 3.12** | Agent, guards, verifier, Lambdas, evals, data generator. | Fastest ecosystem for agent frameworks and scripting. |
| **AWS SDK v2 (Java) / boto3** | Calls to Athena, DynamoDB, S3, AgentCore. | Native AWS access with IAM credentials. |

## Infrastructure and quality

| Technology | Role here | Good for |
|---|---|---|
| **Terraform** (AWS provider 6.x) | All resources in `infra/`, in us-east-1. | Reproducible infra; one `destroy` removes everything. |
| **Docker buildx** | Builds arm64 images (AgentCore needs ARM64). | Cross-platform builds from a laptop. |
| **OpenTelemetry (ADOT)** | Auto-instruments the agent; exports OTLP to X-Ray. | Vendor-neutral traces, metrics and logs. |
| **X-Ray + Transaction Search** | Stores spans in CloudWatch Logs (`aws/spans`) for search and the GenAI dashboard. | Searching every trace, not only a sample. |
| **pytest / JUnit** | 11 Python tests (guards, verifier), 5 Java tests (credit policy). | Fast checks of the deterministic parts. |
| **Eval suite** (`evals/`) | 12 multi-turn scenarios with deterministic checks, local and remote. | Catching behaviour regressions that unit tests cannot see. |
