import os

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")

# Local defaults; on AWS these point to the billing MCP runtime and the AgentCore Gateway.
BILLING_MCP_URL = os.environ.get("BILLING_MCP_URL", "http://localhost:8000/mcp")
CARE_MCP_URL = os.environ.get("CARE_MCP_URL", "http://localhost:8001/mcp")

# Max verifier retries before falling back to a safe answer + human handoff.
VERIFIER_RETRIES = int(os.environ.get("VERIFIER_RETRIES", "1"))
