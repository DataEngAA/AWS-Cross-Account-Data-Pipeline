# Inputs. Real values go in terraform.tfvars (ignored by Git);
# terraform.tfvars.example shows the format.

variable "region" {
  description = "AWS region for every resource"
  type        = string
  default     = "ap-south-1"
}

variable "profile" {
  description = "AWS CLI profile for Account B (platform)"
  type        = string
  default     = "acct-b"
}

variable "account_a_id" {
  description = "Account ID of Account A (producer); used in cross-account names and policies"
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_a_id))
    error_message = "account_a_id must be a 12-digit AWS account ID."
  }
}

variable "alert_email" {
  description = "Email address subscribed to the platform-alerts SNS topic"
  type        = string
}

variable "enable_rds" {
  description = "Create RDS, the interface endpoints and the load job's database wiring (costs per hour)"
  type        = bool
  default     = false
}
