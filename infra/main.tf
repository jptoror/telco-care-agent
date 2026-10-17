provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "conecta-care-agent"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "me" {}

locals {
  name       = "conecta"
  account_id = data.aws_caller_identity.me.account_id
  data_dir   = "${path.module}/../data/out"
  # Tables the billing MCP reads through Athena; the Lambdas read the CSVs from S3 directly.
  tables = {
    customers     = ["customer_id", "full_name", "zone_id", "plan_id", "language", "customer_since", "segment", "phone"]
    invoices      = ["invoice_id", "customer_id", "period", "issue_date", "due_date", "subtotal", "tax", "total", "status", "paid_on"]
    invoice_lines = ["line_id", "invoice_id", "concept_code", "description", "amount", "ref_date"]
  }
}
