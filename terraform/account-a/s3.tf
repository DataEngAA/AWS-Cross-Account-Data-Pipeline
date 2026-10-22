# Raw bucket: the producer's original files, read by Account B's Glue role, and the
# event notification that tells Account B about each new file.

resource "aws_s3_bucket" "raw" {
  #checkov:skip=CKV_AWS_145:Encrypted with SSE-S3; a customer-managed KMS key adds cost and key policies with no extra benefit here (decision 12)
  #checkov:skip=CKV_AWS_144:Single region by design (decision 7); no disaster-recovery requirement
  #checkov:skip=CKV_AWS_18:No separate access-log bucket for this lab; API activity is in CloudTrail
  bucket           = local.raw_bucket
  bucket_namespace = "account-regional"

  # Raw data is the original; only allow deleting it with its files on purpose.
  force_destroy = var.allow_destroy_raw
}

resource "aws_s3_bucket_ownership_controls" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3: no key policy needed for B's cross-account read
    }
  }
}

# Versioning keeps overwritten files and gives each upload a version id, which the
# workflow uses to build its idempotent execution name.
resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  # Old versions are kept 30 days, then deleted, so versioning does not pile up forever.
  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.raw]
}

# Bucket policy: HTTPS only, and read access for Account B's Glue role (ADR-002).
data "aws_iam_policy_document" "raw_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.raw.arn, "${aws_s3_bucket.raw.arn}/*"]
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

  statement {
    sid       = "PlatformGlueListRaw"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.raw.arn]
    principals {
      type        = "AWS"
      identifiers = [local.platform_glue_role]
    }
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw", "raw/*"]
    }
  }

  statement {
    sid       = "PlatformGlueReadRaw"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.raw.arn}/raw/*"]
    principals {
      type        = "AWS"
      identifiers = [local.platform_glue_role]
    }
  }
}

resource "aws_s3_bucket_policy" "raw" {
  bucket     = aws_s3_bucket.raw.id
  policy     = data.aws_iam_policy_document.raw_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.raw]
}

# Every new .json under raw/ -> message in Account B's ingest queue.
resource "aws_s3_bucket_notification" "raw_to_platform" {
  bucket = aws_s3_bucket.raw.id

  queue {
    id            = "to-platform-ingest-queue"
    queue_arn     = local.platform_ingest_queue
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "raw/"
    filter_suffix = ".json"
  }
}
