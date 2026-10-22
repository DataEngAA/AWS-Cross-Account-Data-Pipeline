# Terraform and provider versions, and where this project's state is stored.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State lives in the bootstrap bucket in Account B, under its own key.
  # backend.hcl (ignored by Git) gives the bucket name and the profile used to reach it:
  # the backend logs in to Account B, while the provider below works in Account A.
  backend "s3" {
    key          = "account-a/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
