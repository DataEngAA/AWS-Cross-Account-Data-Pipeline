# The register: one row per raw file with its status (RECEIVED / PROCESSED / FAILED).

resource "aws_dynamodb_table" "scrape_state" {
  #checkov:skip=CKV_AWS_119:Encrypted with the AWS-owned key; a customer-managed KMS key adds cost with no extra benefit here (decision 12)
  name         = "scrape_state"
  billing_mode = "PAY_PER_REQUEST" # on-demand (decision 14)
  hash_key     = "file_key"

  # Only key attributes are declared; DynamoDB does not need the other columns up front.
  attribute {
    name = "file_key"
    type = "S"
  }

  # Continuous backups: the table can be restored to any second of the last 35 days.
  point_in_time_recovery {
    enabled = true
  }
}

# Taken over from the console build with an `import` block on 2026-10-22 (ADR-005); the
# block was removed after that apply, because from then on Terraform creates the table.
