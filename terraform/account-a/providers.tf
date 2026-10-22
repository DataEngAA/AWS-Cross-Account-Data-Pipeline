provider "aws" {
  region  = var.region
  profile = var.profile # Account A (producer)

  default_tags {
    tags = {
      project      = "aws-multi-account-pipeline"
      account-role = "producer"
      managed-by   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
