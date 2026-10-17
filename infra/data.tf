# ---------------------------------------------------------------- S3: raw CSVs + Athena results
resource "aws_s3_bucket" "data" {
  bucket        = "${local.name}-data-${local.account_id}-${var.region}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "csv" {
  for_each = fileset(local.data_dir, "*.csv")
  bucket   = aws_s3_bucket.data.id
  key      = "raw/${trimsuffix(each.value, ".csv")}/${each.value}"
  source   = "${local.data_dir}/${each.value}"
  etag     = filemd5("${local.data_dir}/${each.value}")
}

resource "aws_s3_bucket" "athena_results" {
  bucket        = "${local.name}-athena-${local.account_id}-${var.region}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket                  = aws_s3_bucket.athena_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    id     = "expire-results"
    status = "Enabled"
    filter {}
    expiration { days = 7 }
  }
}

# ---------------------------------------------------------------- Glue catalog + Athena
resource "aws_glue_catalog_database" "conecta" {
  name = local.name
}

resource "aws_glue_catalog_table" "tables" {
  for_each      = local.tables
  name          = each.key
  database_name = aws_glue_catalog_database.conecta.name
  table_type    = "EXTERNAL_TABLE"
  parameters = {
    classification           = "csv"
    "skip.header.line.count" = "1"
  }
  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data.id}/raw/${each.key}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.serde2.OpenCSVSerde"
      parameters            = { separatorChar = ",", quoteChar = "\"" }
    }
    dynamic "columns" {
      for_each = each.value
      content {
        name = columns.value
        type = "string" # OpenCSVSerde reads strings; the billing service parses decimals
      }
    }
  }
}

resource "aws_athena_workgroup" "conecta" {
  name          = local.name
  force_destroy = true
  configuration {
    enforce_workgroup_configuration = true
    bytes_scanned_cutoff_per_query  = 104857600 # 100 MB guardrail
    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.id}/results/"
    }
  }
}

# ---------------------------------------------------------------- DynamoDB: issued credits
resource "aws_dynamodb_table" "credits" {
  name         = "${local.name}-credits"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "customer_id"
  range_key    = "credit_id"
  attribute {
    name = "customer_id"
    type = "S"
  }
  attribute {
    name = "credit_id"
    type = "S"
  }
}
