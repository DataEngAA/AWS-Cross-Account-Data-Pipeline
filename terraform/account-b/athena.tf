# Athena workgroup: where queries run, where results go, and a cost limit per query.

resource "aws_athena_workgroup" "analytics" {
  name          = "platform-analytics"
  force_destroy = true # allow destroy even though the workgroup has query history

  configuration {
    enforce_workgroup_configuration    = true # users cannot override these settings
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 1073741824 # 1 GB: stop runaway queries

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }

    result_configuration {
      output_location       = "s3://${aws_s3_bucket.curated.bucket}/athena-results/"
      expected_bucket_owner = local.account_b_id

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
