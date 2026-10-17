data "archive_file" "tools" {
  type        = "zip"
  source_dir  = "${path.module}/../tools"
  excludes    = ["local_mcp.py", "conecta_tools/__pycache__"]
  output_path = "${path.module}/build/tools.zip"
}

resource "aws_iam_role" "tools_lambda" {
  name = "${local.name}-tools-lambda"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "tools_logs" {
  role       = aws_iam_role.tools_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "tools_data" {
  role = aws_iam_role.tools_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = "${aws_s3_bucket.data.arn}/raw/*"
    }]
  })
}

# One function per gateway target; both run the same package and dispatch on the tool name.
resource "aws_lambda_function" "tools" {
  for_each         = toset(["network", "care"])
  function_name    = "${local.name}-${each.key}-tools"
  role             = aws_iam_role.tools_lambda.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "conecta_tools.lambda_handler.handler"
  filename         = data.archive_file.tools.output_path
  source_code_hash = data.archive_file.tools.output_base64sha256
  timeout          = 15
  memory_size      = 256
  environment {
    variables = { DATA_BUCKET = aws_s3_bucket.data.id, DATA_PREFIX = "raw" }
  }
}

resource "aws_cloudwatch_log_group" "tools" {
  for_each          = aws_lambda_function.tools
  name              = "/aws/lambda/${each.value.function_name}"
  retention_in_days = 14
}
