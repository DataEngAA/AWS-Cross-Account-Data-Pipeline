# IAM Access Analyzer: reports every resource in this account that can be reached from
# outside it (bucket policies, role trust policies, ...). Free for this analyzer type.

resource "aws_accessanalyzer_analyzer" "account" {
  analyzer_name = "producer-account-analyzer"
  type          = "ACCOUNT" # zone of trust = this account; anything outside it is reported
}

# Archive rules: the cross-account access this project grants on purpose. Each rule
# matches one resource AND one outside principal, so if either resource is ever opened
# to anyone else, that finding does not match and stays ACTIVE.
# (Other projects' findings in this account, such as a GitHub Actions OIDC role, are
# left to those projects.)

# B's Glue role reads raw files (ADR-002).
resource "aws_accessanalyzer_archive_rule" "raw_bucket_read_by_platform_glue" {
  analyzer_name = aws_accessanalyzer_analyzer.account.analyzer_name
  rule_name     = "raw-bucket-read-by-platform-glue"

  filter {
    criteria = "resource"
    eq       = [aws_s3_bucket.raw.arn]
  }
  filter {
    criteria = "principal.AWS"
    eq       = [local.platform_glue_role]
  }
  filter {
    criteria = "isPublic"
    eq       = ["false"]
  }
}

# Account B's workflow assumes producer-state-writer to update scrape_state. The trust
# policy names account B (narrowed by an aws:PrincipalArn condition), so the finding's
# principal is the account ID.
resource "aws_accessanalyzer_archive_rule" "state_writer_assumed_by_platform" {
  analyzer_name = aws_accessanalyzer_analyzer.account.analyzer_name
  rule_name     = "state-writer-assumed-by-platform"

  filter {
    criteria = "resource"
    eq       = [aws_iam_role.state_writer.arn]
  }
  filter {
    criteria = "principal.AWS"
    eq       = [var.account_b_id]
  }
  filter {
    criteria = "isPublic"
    eq       = ["false"]
  }
}
