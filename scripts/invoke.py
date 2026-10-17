"""Chat with the deployed agent on AgentCore Runtime.

    python scripts/invoke.py C1001 "¿por qué subió mi factura?" ["Sí, aplícalo" ...]
"""

import json
import subprocess
import sys
import uuid

import boto3
from botocore.config import Config


def runtime_arn() -> str:
    return subprocess.check_output(["terraform", "-chdir=infra", "output", "-raw", "agent_runtime_arn"], text=True)


def ask(client, arn, session_id, customer_id, prompt) -> dict:
    r = client.invoke_agent_runtime(agentRuntimeArn=arn, runtimeSessionId=session_id, qualifier="DEFAULT",
                                    payload=json.dumps({"customer_id": customer_id, "prompt": prompt}))
    return json.loads(r["response"].read())


def main(customer_id: str, prompts: list[str]):
    client = boto3.client("bedrock-agentcore", region_name="us-east-1",
                          config=Config(read_timeout=180, retries={"max_attempts": 2}))
    arn = runtime_arn()
    session_id = f"demo-{customer_id}-{uuid.uuid4()}"  # >= 33 chars required
    for p in prompts:
        out = ask(client, arn, session_id, customer_id, p)
        print(f"cliente> {p}\nconi>    {out.get('answer', out)}")
        meta = {k: out[k] for k in ("verified", "verifier_retries", "guard_blocks") if k in out}
        print(f"         {meta}\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
