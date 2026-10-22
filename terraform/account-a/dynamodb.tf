# The register: one row per raw file with its status (RECEIVED / PROCESSED / FAILED).

resource "aws_dynamodb_table" "scrape_state" {
  name         = "scrape_state"
  billing_mode = "PAY_PER_REQUEST" # on-demand (decision 14)
  hash_key     = "file_key"

  # Only key attributes are declared; DynamoDB does not need the other columns up front.
  attribute {
    name = "file_key"
    type = "S"
  }
}

# Taken over from the console build with an `import` block on 2026-10-22 (ADR-005); the
# block was removed after that apply, because from then on Terraform creates the table.
