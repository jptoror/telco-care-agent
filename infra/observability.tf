# CloudWatch Transaction Search: lets AgentCore Observability show agent traces (spans -> aws/spans log group).
# Regional setting: affects us-east-1 only.
resource "aws_cloudwatch_log_resource_policy" "xray_spans" {
  policy_name = "conecta-transaction-search"
  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "TransactionSearchXRayAccess"
      Effect    = "Allow"
      Principal = { Service = "xray.amazonaws.com" }
      Action    = "logs:PutLogEvents"
      Resource = [
        "arn:aws:logs:${var.region}:${local.account_id}:log-group:aws/spans:*",
        "arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/application-signals/data:*",
      ]
      Condition = {
        ArnLike      = { "aws:SourceArn" = "arn:aws:xray:${var.region}:${local.account_id}:*" }
        StringEquals = { "aws:SourceAccount" = local.account_id }
      }
    }]
  })
}

resource "aws_xray_trace_segment_destination" "cloudwatch" {
  destination = "CloudWatchLogs"
  depends_on  = [aws_cloudwatch_log_resource_policy.xray_spans]
}
