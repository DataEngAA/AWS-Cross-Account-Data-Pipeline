# Glue: job scripts, the ETL + data quality job, its role, and the Data Catalog table.
# The RDS load job and its secret permission are in rds.tf (only when enable_rds = true).

locals {
  curated_s3 = "s3://${aws_s3_bucket.curated.bucket}"
}

# --- Scripts -----------------------------------------------------------------------------
# Uploaded to scripts/ in the curated bucket. etag = file hash, so an edited script is
# re-uploaded on the next apply and an unchanged one is left alone.
resource "aws_s3_object" "etl_script" {
  bucket = aws_s3_bucket.curated.id
  key    = "scripts/etl_products.py"
  source = "${path.module}/../../src/glue/etl_products.py"
  etag   = filemd5("${path.module}/../../src/glue/etl_products.py")
}

resource "aws_s3_object" "load_script" {
  bucket = aws_s3_bucket.curated.id
  key    = "scripts/load_rds.py"
  source = "${path.module}/../../src/glue/load_rds.py"
  etag   = filemd5("${path.module}/../../src/glue/load_rds.py")
}

# --- Role ---------------------------------------------------------------------------------
data "aws_iam_policy_document" "glue_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "platform-glue-etl-role"
  assume_role_policy = data.aws_iam_policy_document.glue_trust.json
}

# AWS-managed policy Glue needs for itself: its logs, metrics, data quality results and
# the network interfaces it creates when a job runs inside the VPC.
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue" {
  statement {
    sid       = "ListCuratedBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.curated.arn]
  }
  statement {
    sid       = "ReadScripts"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.curated.arn}/scripts/*"]
  }
  statement {
    sid     = "WriteOutputs"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    # Each prefix plus the <prefix>_$folder$ marker object Glue writes next to it
    # (the AccessDenied found in Chunk 2). A lone $ is literal in Terraform; only ${ starts
    # a reference.
    resources = flatten([
      for prefix in ["curated", "quarantine", "dq-results"] : [
        "${aws_s3_bucket.curated.arn}/${prefix}/*",
        "${aws_s3_bucket.curated.arn}/${prefix}_$folder$",
      ]
    ])
  }
  # Cross-account read of Account A's raw files (ADR-002). A's bucket policy grants the
  # other half; both are needed.
  statement {
    sid       = "ListProducerRaw"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw", "raw/*"]
    }
  }
  statement {
    sid       = "ReadProducerRaw"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_bucket_arn}/raw/*"]
  }
}

resource "aws_iam_role_policy" "glue" {
  name   = "glue-data-access"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue.json
}

# --- Security configuration ---------------------------------------------------------------
# Makes Glue itself request SSE-S3 for everything it writes, independent of bucket defaults.
resource "aws_glue_security_configuration" "platform" {
  #checkov:skip=CKV_AWS_99:S3 output uses SSE-S3; CloudWatch and bookmark encryption would need a customer-managed KMS key (decision 12), and bookmarks are off
  name = "platform-glue-security"

  encryption_configuration {
    s3_encryption {
      s3_encryption_mode = "SSE-S3"
    }
    cloudwatch_encryption {
      cloudwatch_encryption_mode = "DISABLED"
    }
    job_bookmarks_encryption {
      job_bookmarks_encryption_mode = "DISABLED"
    }
  }
}

# --- ETL + data quality job ----------------------------------------------------------------
resource "aws_glue_job" "etl_products" {
  name                   = "platform-etl-products"
  role_arn               = aws_iam_role.glue.arn
  glue_version           = "5.0"
  worker_type            = "G.1X"
  number_of_workers      = 2
  execution_class        = "FLEX"
  timeout                = 10 # minutes
  security_configuration = aws_glue_security_configuration.platform.name
  max_retries            = 0

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "${local.curated_s3}/${aws_s3_object.etl_script.key}"
  }

  execution_property {
    max_concurrent_runs = 3
  }

  default_arguments = {
    "--job-language"    = "python"
    "--enable-metrics"  = "true"
    "--output_path"     = "${local.curated_s3}/curated/products/"
    "--quarantine_path" = "${local.curated_s3}/quarantine/products/"
    "--dq_results_path" = "${local.curated_s3}/dq-results/products/"
    # The workflow passes the real file for each run; this default only satisfies the
    # script's required argument when the job is started by hand.
    "--input_path" = "s3://${local.raw_bucket}/raw/"
  }
}

# --- Data Catalog: database and table (declared, replaces the crawler) ---------------------
resource "aws_glue_catalog_database" "curated" {
  name = "platform_curated"
}

resource "aws_glue_catalog_table" "products" {
  name          = "products"
  database_name = aws_glue_catalog_database.curated.name
  table_type    = "EXTERNAL_TABLE" # Athena reads the files in S3; dropping the table keeps them

  parameters = {
    classification        = "parquet"
    EXTERNAL              = "TRUE"
    "parquet.compression" = "SNAPPY"
  }

  storage_descriptor {
    location      = "${local.curated_s3}/curated/products/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    # Same columns and types as the Parquet files written by etl_products.py.
    columns {
      name = "product_id"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "price"
      type = "decimal(10,2)"
    }
    columns {
      name = "currency"
      type = "string"
    }
    columns {
      name = "in_stock"
      type = "boolean"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "scraped_at"
      type = "timestamp"
    }
  }

  # Folders date=.../category=... ; registered by the workflow's MSCK REPAIR step.
  partition_keys {
    name = "date"
    type = "string"
  }
  partition_keys {
    name = "category"
    type = "string"
  }
}
