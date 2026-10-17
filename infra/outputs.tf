output "data_bucket" { value = aws_s3_bucket.data.id }
output "athena_workgroup" { value = aws_athena_workgroup.conecta.name }
output "gateway_url" { value = aws_bedrockagentcore_gateway.care.gateway_url }
output "memory_id" { value = aws_bedrockagentcore_memory.care.id }
output "ecr" { value = { for k, r in aws_ecr_repository.repo : k => r.repository_url } }
output "billing_mcp_url" { value = local.billing_mcp_url }
output "agent_runtime_arn" { value = try(aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn, "") }
