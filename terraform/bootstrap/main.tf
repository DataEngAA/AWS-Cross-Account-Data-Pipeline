# Bootstrap: the S3 bucket that stores Terraform state for account-a and account-b.
#
# Applied once, with local state (terraform.tfstate in this folder, ignored by Git),
# because a bucket cannot hold the state of the code that creates it.
# Lives in Account B, the platform account, which also runs the pipeline.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.profile

  default_tags {
    tags = {
      project      = "aws-multi-account-pipeline"
      account-role = "platform"
      component    = "terraform-state"
      managed-by   = "terraform"
    }
  }
}

variable "region" {
  description = "AWS region for the state bucket"
  type        = string
  default     = "ap-south-1"
}

variable "profile" {
  description = "AWS CLI profile for Account B"
  type        = string
  default     = "acct-b"
}

# Read the account ID instead of typing it, so no ID is written in code.
data "aws_caller_identity" "current" {}

locals {
  state_bucket = "tfstate-${data.aws_caller_identity.current.account_id}-${var.region}"
}

resource "aws_s3_bucket" "state" {
  #checkov:skip=CKV_AWS_145:Encrypted with SSE-S3; a customer-managed KMS key adds cost and key policies with no extra benefit here (decision 12)
  #checkov:skip=CKV_AWS_144:Single region by design (decision 7); no disaster-recovery requirement
  #checkov:skip=CKV_AWS_18:No separate access-log bucket for this lab; API activity is in CloudTrail
  #checkov:skip=CKV2_AWS_62:Nothing needs to react to objects in this bucket
  bucket = local.state_bucket

  # Refuse to delete this bucket, even with `terraform destroy`: losing it means
  # Terraform forgets every resource in both accounts.
  lifecycle {
    prevent_destroy = true
  }
}

# Every apply writes a new state version; old versions allow rolling back a bad state.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Keep old state versions for 90 days, then delete them, so they do not pile up forever.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
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

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Refuse any request that is not encrypted in transit (plain HTTP).
data "aws_iam_policy_document" "state_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]
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

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_tls_only.json

  # Apply the public access block first, so this policy is never briefly evaluated without it.
  depends_on = [aws_s3_bucket_public_access_block.state]
}

output "state_bucket" {
  description = "Put this name in backend.hcl of account-a and account-b"
  value       = aws_s3_bucket.state.bucket
}
