output "raw_bucket" {
  description = "Upload target for src/generator/upload.py"
  value       = aws_s3_bucket.raw.bucket
}

output "state_table" {
  value = aws_dynamodb_table.scrape_state.name
}

output "state_writer_role_arn" {
  description = "Assumed by Account B's workflow (MarkProcessed / MarkFailed)"
  value       = aws_iam_role.state_writer.arn
}
