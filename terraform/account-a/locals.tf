locals {
  account_a_id = data.aws_caller_identity.current.account_id
  region       = data.aws_region.current.region

  raw_bucket = "producer-aws-${local.account_a_id}-${local.region}-an"

  # Account B's resources. They must exist before this project is applied:
  # AWS rejects a bucket policy that names a missing role, and S3 tests the queue
  # when the event notification is saved. So: apply account-b first.
  platform_glue_role     = "arn:aws:iam::${var.account_b_id}:role/platform-glue-etl-role"
  platform_workflow_role = "arn:aws:iam::${var.account_b_id}:role/platform-workflow-role"
  platform_ingest_queue  = "arn:aws:sqs:${local.region}:${var.account_b_id}:platform-ingest-queue"
}
