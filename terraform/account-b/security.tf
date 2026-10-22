# IAM Access Analyzer: reports every resource in this account that can be reached from
# outside it (queue policies, bucket policies, role trust policies, ...). Free for this
# analyzer type. Expected finding for Account B: platform-ingest-queue (S3 events on
# behalf of Account A). Anything else is unintended and must be investigated.

resource "aws_accessanalyzer_analyzer" "account" {
  analyzer_name = "platform-account-analyzer"
  type          = "ACCOUNT" # zone of trust = this account; anything outside it is reported
}
