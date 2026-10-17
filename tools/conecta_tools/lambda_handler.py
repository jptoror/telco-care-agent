"""AgentCore Gateway Lambda target. The gateway sends the tool arguments as the event and the tool name
in client_context.custom['bedrockAgentCoreToolName'] as '<target>___<tool>'."""

import json
import logging

from . import care, network

log = logging.getLogger()
log.setLevel(logging.INFO)

REGISTRY = {f.__name__: f for f in network.TOOLS + care.TOOLS}


def handler(event, context):
    full_name = context.client_context.custom["bedrockAgentCoreToolName"]
    tool = full_name.split("___", 1)[-1]
    log.info(json.dumps({"tool": tool, "args": event}))
    fn = REGISTRY.get(tool)
    if not fn:
        return {"error": f"Unknown tool {tool}"}
    try:
        return fn(**event)
    except (ValueError, TypeError) as e:
        return {"error": str(e)}
