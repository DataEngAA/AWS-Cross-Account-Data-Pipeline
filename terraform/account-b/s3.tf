# Curated bucket: everything the platform produces (curated/, quarantine/, dq-results/,
# athena-results/) plus the Glue scripts under scripts/.

resource "aws_s3_bucket" "curated" {
  #checkov:skip=CKV_AWS_145:Encrypted with SSE-S3; a customer-managed KMS key adds cost and key policies with no extra benefit here (decision 12)
  #checkov:skip=CKV_AWS_144:Single region by design (decision 7); no disaster-recovery requirement
  #checkov:skip=CKV_AWS_18:No separate access-log bucket for this lab; API activity is in CloudTrail
  #checkov:skip=CKV2_AWS_62:Nothing needs to react to objects in this bucket
  #checkov:skip=CKV_AWS_21:Curated data is derived and rebuilt from raw, so versioning stays off (decision 13)
  bucket           = local.curated_bucket
  bucket_namespace = "account-regional" # same kind as the console-built bucket

  # Curated data can always be rebuilt from Account A's raw files, so `terraform destroy`
  # may delete the bucket together with its contents (needed for the destroy/apply test).
  force_destroy = true
}

# ACLs off: access is controlled only by policies.
resource "aws_s3_bucket_ownership_controls" "curated" {
  bucket = aws_s3_bucket.curated.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "curated" {
  bucket                  = aws_s3_bucket.curated.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "curated" {
  bucket = aws_s3_bucket.curated.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# No versioning resource: curated is derived data (decision 13), so versioning stays off.

resource "aws_s3_bucket_lifecycle_configuration" "curated" {
  bucket = aws_s3_bucket.curated.id

  # Every Athena query leaves a CSV; keep them a week.
  rule {
    id     = "expire-athena-results"
    status = "Enabled"
    filter {
      prefix = "athena-results/"
    }
    expiration {
      days = 7
    }
  }

  # Uploads that were started but never finished still cost storage; clean them up.
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Refuse any request that is not encrypted in transit.
data "aws_iam_policy_document" "curated_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.curated.arn, "${aws_s3_bucket.curated.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "curated" {
  bucket     = aws_s3_bucket.curated.id
  policy     = data.aws_iam_policy_document.curated_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.curated]
}
