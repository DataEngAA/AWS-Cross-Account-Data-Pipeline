# Names used in more than one file. Every name is built from the account IDs, so
# nothing account-specific is typed into the code.

locals {
  account_b_id = data.aws_caller_identity.current.account_id
  region       = data.aws_region.current.region

  # Account-regional bucket names must end in -<account id>-<region>-an.
  curated_bucket = "platform-aws-${local.account_b_id}-${local.region}-an"

  # Account A's resources, referenced by name only (AWS does not check that they exist
  # in the places these are used, so account-b can be applied before account-a).
  raw_bucket            = "producer-aws-${var.account_a_id}-${local.region}-an"
  raw_bucket_arn        = "arn:aws:s3:::${local.raw_bucket}"
  state_table_arn       = "arn:aws:dynamodb:${local.region}:${var.account_a_id}:table/scrape_state"
  producer_state_writer = "arn:aws:iam::${var.account_a_id}:role/producer-state-writer"
}
