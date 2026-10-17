variable "region" {
  description = "Kept apart from the sa-east-1 workloads in the same account."
  type        = string
  default     = "us-east-1"
}

variable "model_id" {
  type    = string
  default = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "billing_image_tag" {
  description = "Tag pushed by scripts/deploy.sh; empty skips the runtimes (first apply creates ECR only)."
  type        = string
  default     = ""
}

variable "agent_image_tag" {
  type    = string
  default = ""
}
