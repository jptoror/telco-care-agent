# ---------------------------------------------------------------- ECR
resource "aws_ecr_repository" "repo" {
  for_each             = toset(["billing-mcp", "care-agent"])
  name                 = "${local.name}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "repo" {
  for_each   = aws_ecr_repository.repo
  repository = each.value.name
  policy = jsonencode({ rules = [{
    rulePriority = 1, description = "keep last 5"
    selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }
    action       = { type = "expire" }
  }] })
}

# ---------------------------------------------------------------- shared runtime permissions
data "aws_iam_policy_document" "runtime_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

data "aws_iam_policy_document" "runtime_base" {
  statement {
    sid       = "EcrPull"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [for r in aws_ecr_repository.repo : r.arn]
  }
  statement {
    sid       = "EcrToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams", "logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/bedrock-agentcore/*", "arn:aws:logs:${var.region}:${local.account_id}:log-group:*"]
  }
  statement {
    sid       = "Traces"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
    resources = ["*"]
  }
  statement {
    sid       = "Metrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }
  statement {
    sid       = "WorkloadIdentity"
    actions   = ["bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetWorkloadAccessTokenForJWT", "bedrock-agentcore:GetWorkloadAccessTokenForUserId"]
    resources = ["arn:aws:bedrock-agentcore:${var.region}:${local.account_id}:workload-identity-directory/default*"]
  }
}

# ---------------------------------------------------------------- billing MCP runtime (Java)
resource "aws_iam_role" "billing_runtime" {
  name               = "${local.name}-billing-runtime"
  assume_role_policy = data.aws_iam_policy_document.runtime_trust.json
}

resource "aws_iam_role_policy" "billing_base" {
  role   = aws_iam_role.billing_runtime.id
  policy = data.aws_iam_policy_document.runtime_base.json
}

resource "aws_iam_role_policy" "billing_data" {
  role = aws_iam_role.billing_runtime.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"], Resource = aws_athena_workgroup.conecta.arn },
      { Effect = "Allow", Action = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartitions"], Resource = [
        "arn:aws:glue:${var.region}:${local.account_id}:catalog",
        aws_glue_catalog_database.conecta.arn,
      "arn:aws:glue:${var.region}:${local.account_id}:table/${aws_glue_catalog_database.conecta.name}/*"] },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"], Resource = [aws_s3_bucket.data.arn, "${aws_s3_bucket.data.arn}/raw/*"] },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation", "s3:AbortMultipartUpload"], Resource = [aws_s3_bucket.athena_results.arn, "${aws_s3_bucket.athena_results.arn}/*"] },
      { Effect = "Allow", Action = ["dynamodb:Query", "dynamodb:PutItem"], Resource = aws_dynamodb_table.credits.arn },
    ]
  })
}

resource "aws_bedrockagentcore_agent_runtime" "billing" {
  count              = var.billing_image_tag == "" ? 0 : 1
  agent_runtime_name = "${local.name}_billing_mcp"
  description        = "Billing MCP server (Java/Spring AI) over Athena + DynamoDB"
  role_arn           = aws_iam_role.billing_runtime.arn
  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.repo["billing-mcp"].repository_url}:${var.billing_image_tag}"
    }
  }
  network_configuration { network_mode = "PUBLIC" }
  protocol_configuration { server_protocol = "MCP" }
  environment_variables = {
    SPRING_PROFILES_ACTIVE = "aws"
    ATHENA_DATABASE        = aws_glue_catalog_database.conecta.name
    ATHENA_WORKGROUP       = aws_athena_workgroup.conecta.name
    CREDITS_TABLE          = aws_dynamodb_table.credits.name
    AWS_REGION             = var.region
  }
  depends_on = [aws_iam_role_policy.billing_base, aws_iam_role_policy.billing_data]
}

# ---------------------------------------------------------------- memory (short-term conversation history)
resource "aws_bedrockagentcore_memory" "care" {
  name                  = "${local.name}_care_memory"
  description           = "Conversation history per customer session"
  event_expiry_duration = 30
}

# ---------------------------------------------------------------- care agent runtime (Python/Strands)
resource "aws_iam_role" "agent_runtime" {
  name               = "${local.name}-agent-runtime"
  assume_role_policy = data.aws_iam_policy_document.runtime_trust.json
}

resource "aws_iam_role_policy" "agent_base" {
  role   = aws_iam_role.agent_runtime.id
  policy = data.aws_iam_policy_document.runtime_base.json
}

resource "aws_iam_role_policy" "agent_access" {
  role = aws_iam_role.agent_runtime.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      { Effect = "Allow", Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], Resource = [
        "arn:aws:bedrock:*::foundation-model/anthropic.*",
      "arn:aws:bedrock:${var.region}:${local.account_id}:inference-profile/*"] },
      { Effect = "Allow", Action = ["bedrock-agentcore:InvokeGateway"], Resource = aws_bedrockagentcore_gateway.care.gateway_arn },
      { Effect = "Allow", Action = ["bedrock-agentcore:CreateEvent", "bedrock-agentcore:ListEvents", "bedrock-agentcore:GetEvent", "bedrock-agentcore:ListSessions", "bedrock-agentcore:GetMemory"], Resource = aws_bedrockagentcore_memory.care.arn },
      ], var.billing_image_tag == "" ? [] : [
      { Effect = "Allow", Action = ["bedrock-agentcore:InvokeAgentRuntime"], Resource = ["${aws_bedrockagentcore_agent_runtime.billing[0].agent_runtime_arn}", "${aws_bedrockagentcore_agent_runtime.billing[0].agent_runtime_arn}/*"] },
    ])
  })
}

locals {
  billing_mcp_url = var.billing_image_tag == "" ? "" : "https://bedrock-agentcore.${var.region}.amazonaws.com/runtimes/${urlencode(aws_bedrockagentcore_agent_runtime.billing[0].agent_runtime_arn)}/invocations?qualifier=DEFAULT"
}

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  count              = var.agent_image_tag == "" || var.billing_image_tag == "" ? 0 : 1
  agent_runtime_name = "${local.name}_care_agent"
  description        = "Coni: Strands care agent with guards and grounding verifier"
  role_arn           = aws_iam_role.agent_runtime.arn
  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.repo["care-agent"].repository_url}:${var.agent_image_tag}"
    }
  }
  network_configuration { network_mode = "PUBLIC" }
  protocol_configuration { server_protocol = "HTTP" }
  environment_variables = {
    AWS_REGION      = var.region
    MODEL_ID        = var.model_id
    BILLING_MCP_URL = local.billing_mcp_url
    CARE_MCP_URL    = aws_bedrockagentcore_gateway.care.gateway_url
    MCP_AUTH        = "sigv4"
    MEMORY_ID       = aws_bedrockagentcore_memory.care.id
    # ADOT: AgentCore Observability (traces in CloudWatch GenAI Observability)
    AGENT_OBSERVABILITY_ENABLED = "true"
    OTEL_PYTHON_DISTRO          = "aws_distro"
    OTEL_PYTHON_CONFIGURATOR    = "aws_configurator"
  }
  depends_on = [aws_iam_role_policy.agent_base, aws_iam_role_policy.agent_access]
}
