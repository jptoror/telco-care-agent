"""httpx auth that signs MCP requests with SigV4 for AgentCore Gateway and AgentCore Runtime."""

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


class AgentCoreSigV4(httpx.Auth):
    requires_request_body = True

    def __init__(self, region: str, service: str = "bedrock-agentcore"):
        self.region = region
        self.service = service
        self.session = boto3.Session()

    def auth_flow(self, request: httpx.Request):
        creds = self.session.get_credentials().get_frozen_credentials()
        aws = AWSRequest(method=request.method, url=str(request.url), data=request.content,
                         headers={k: v for k, v in request.headers.items()
                                  if k.lower() in ("content-type", "accept", "mcp-session-id",
                                                   "mcp-protocol-version")})
        SigV4Auth(creds, self.service, self.region).add_auth(aws)
        for k, v in aws.headers.items():
            request.headers[k] = v
        yield request
