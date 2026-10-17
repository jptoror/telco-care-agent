# AgentCore Gateway: one MCP endpoint in front of the network and care Lambdas (SigV4 inbound auth).

locals {
  cid = { name = "customer_id", type = "string", description = "Customer id, e.g. C1001", required = true }
  gateway_tools = {
    network = [
      { name = "get_line_status", description = "Current status of the customer's home modem (ONLINE, DEGRADED, OFFLINE), signal and last contact.", props = [local.cid] },
      { name = "check_zone_outage", description = "Active network outages in the customer's zone, with cause and estimated restoration time.", props = [local.cid] },
      { name = "run_remote_diagnostic", description = "Runs a remote line test and returns a diagnosis code plus the recommended next step.", props = [local.cid] },
      { name = "reboot_modem", description = "Reboots the customer's modem remotely. Refuses when a zone outage explains the problem.", props = [local.cid] },
    ]
    care = [
      { name = "list_plans", description = "Plan catalog. kind: 'mobile', 'home' or empty for all.", props = [
      { name = "kind", type = "string", description = "mobile, home or empty", required = false }] },
      { name = "recommend_plan", description = "Recommends the cheapest plan that fits the customer's real usage over the last 30 days.", props = [local.cid] },
      { name = "request_plan_change", description = "Changes the customer's plan. First call without confirmation to get the summary to read to the customer; call again with customer_confirmed=true only after the customer explicitly accepts.", props = [
        local.cid,
        { name = "plan_id", type = "string", description = "Target plan id, e.g. HOME-300", required = true },
      { name = "customer_confirmed", type = "boolean", description = "True only after an explicit yes", required = false }] },
      { name = "create_handoff_ticket", description = "Escalates to a human agent with a summary so the customer does not have to repeat anything.", props = [
        local.cid,
        { name = "reason", type = "string", description = "Short reason for the handoff", required = true },
      { name = "summary", type = "string", description = "What happened so far", required = true }] },
    ]
  }
}

resource "aws_iam_role" "gateway" {
  name = "${local.name}-gateway"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "gateway_invoke" {
  role = aws_iam_role.gateway.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "lambda:InvokeFunction", Resource = [for f in aws_lambda_function.tools : f.arn] }]
  })
}

resource "aws_bedrockagentcore_gateway" "care" {
  name            = "${local.name}-care-gateway"
  description     = "MCP front door for Conecta network and care tools"
  role_arn        = aws_iam_role.gateway.arn
  protocol_type   = "MCP"
  authorizer_type = "AWS_IAM"
  protocol_configuration {
    mcp {
      instructions = "Telecom customer care tools: network diagnostics and plans."
    }
  }
}

resource "aws_bedrockagentcore_gateway_target" "tools" {
  for_each           = local.gateway_tools
  name               = each.key
  gateway_identifier = aws_bedrockagentcore_gateway.care.gateway_id
  credential_provider_configuration {
    gateway_iam_role {}
  }
  target_configuration {
    mcp {
      lambda {
        lambda_arn = aws_lambda_function.tools[each.key].arn
        tool_schema {
          dynamic "inline_payload" {
            for_each = each.value
            content {
              name        = inline_payload.value.name
              description = inline_payload.value.description
              input_schema {
                type = "object"
                dynamic "property" {
                  for_each = inline_payload.value.props
                  content {
                    name        = property.value.name
                    type        = property.value.type
                    description = property.value.description
                    required    = property.value.required
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
