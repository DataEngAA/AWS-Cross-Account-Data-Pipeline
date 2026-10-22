# Values account-a needs, and values handy for checks.

output "curated_bucket" {
  value = aws_s3_bucket.curated.bucket
}

output "ingest_queue_arn" {
  description = "Destination of Account A's S3 event notification"
  value       = aws_sqs_queue.ingest.arn
}

output "glue_role_arn" {
  description = "Named in Account A's raw bucket policy"
  value       = aws_iam_role.glue.arn
}

output "workflow_role_arn" {
  description = "Trusted by Account A's producer-state-writer role"
  value       = aws_iam_role.workflow.arn
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.ingest.arn
}

output "rds_endpoint" {
  description = "Database address while enable_rds = true"
  value       = var.enable_rds ? aws_db_instance.platform[0].address : null
}
