provider "aws" {
  region  = var.region
  profile = var.profile

  # Tags on every resource this project creates.
  default_tags {
    tags = {
      project      = "aws-multi-account-pipeline"
      account-role = "platform"
      managed-by   = "terraform"
    }
  }
}

# Read-only lookups: which account and region this run is in.
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
