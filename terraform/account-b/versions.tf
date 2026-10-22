# Terraform and provider versions, and where this project's state is stored.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    # Zips the Lambda source code (lambda.tf).
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  # State lives in the bucket created by terraform/bootstrap.
  # The bucket name and profile are not written here, because a backend block cannot
  # use variables and the bucket name contains the account ID. They come from
  # backend.hcl (ignored by Git):  terraform init -backend-config=backend.hcl
  backend "s3" {
    key          = "account-b/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true # lock file next to the state, so two applies cannot run at once
  }
}
