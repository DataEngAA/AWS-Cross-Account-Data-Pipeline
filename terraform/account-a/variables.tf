# Inputs. Real values go in terraform.tfvars (ignored by Git).

variable "region" {
  description = "AWS region for every resource"
  type        = string
  default     = "ap-south-1"
}

variable "profile" {
  description = "AWS CLI profile for Account A (producer)"
  type        = string
  default     = "default"
}

variable "account_b_id" {
  description = "Account ID of Account B (platform); its roles and queue are referenced by name"
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_b_id))
    error_message = "account_b_id must be a 12-digit AWS account ID."
  }
}

variable "allow_destroy_raw" {
  description = "Let `terraform destroy` delete the raw bucket and its files. Keep false except for the destroy/apply test."
  type        = bool
  default     = false
}
