# Ingest workflow: ETL -> refresh partitions -> mark PROCESSED in Account A, or
# MarkFailed -> email on any error.

# --- Role -------------------------------------------------------------------------------------
data "aws_iam_policy_document" "workflow_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    # Only Step Functions acting for this account (confused-deputy protection).
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_b_id]
    }
  }
}

# The name matters: Account A's producer-state-writer trusts exactly this role ARN.
resource "aws_iam_role" "workflow" {
  name               = "platform-workflow-role"
  assume_role_policy = data.aws_iam_policy_document.workflow_trust.json
}

data "aws_iam_policy_document" "workflow" {
  statement {
    sid       = "RunEtlJob"
    actions   = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"]
    resources = [aws_glue_job.etl_products.arn]
  }
  statement {
    sid = "RunAthenaQuery"
    actions = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults",
    "athena:StopQueryExecution", "athena:GetWorkGroup"]
    resources = [aws_athena_workgroup.analytics.arn]
  }
  statement {
    sid = "CatalogForPartitionRepair"
    actions = ["glue:GetDatabase", "glue:GetTable", "glue:GetPartition", "glue:GetPartitions",
    "glue:BatchGetPartition", "glue:CreatePartition", "glue:BatchCreatePartition"]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_b_id}:catalog",
      aws_glue_catalog_database.curated.arn,
      aws_glue_catalog_table.products.arn,
    ]
  }
  statement {
    sid       = "AthenaListsBucket"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = [aws_s3_bucket.curated.arn]
  }
  statement {
    sid     = "AthenaReadsCuratedWritesResults"
    actions = ["s3:GetObject", "s3:PutObject"]
    resources = [
      "${aws_s3_bucket.curated.arn}/curated/*",
      "${aws_s3_bucket.curated.arn}/athena-results/*",
    ]
  }
  statement {
    sid       = "UpdateStatusInAccountA"
    actions   = ["sts:AssumeRole"]
    resources = [local.producer_state_writer]
  }
  statement {
    sid       = "SendAlerts"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "workflow" {
  name   = "workflow-permissions"
  role   = aws_iam_role.workflow.id
  policy = data.aws_iam_policy_document.workflow.json
}

# --- State machine ------------------------------------------------------------------------------
# The definition is the file tested in Chunk 6; only the account ID placeholders are filled in.
resource "aws_sfn_state_machine" "ingest" {
  name     = local.state_machine_name
  type     = "STANDARD"
  role_arn = aws_iam_role.workflow.arn

  definition = replace(
    replace(
      file("${path.module}/../../src/stepfunctions/ingest_workflow.asl.json"),
      "<ACCOUNT_A_ID>", var.account_a_id
    ),
    "<ACCOUNT_B_ID>", local.account_b_id
  )

  # The role's permissions must exist before the first execution.
  depends_on = [aws_iam_role_policy.workflow]
}
