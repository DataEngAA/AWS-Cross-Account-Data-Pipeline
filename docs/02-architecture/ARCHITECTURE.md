# Architecture

## Overview
Two AWS accounts split by responsibility.

| | Account A: producer (free tier) | Account B: platform (paid) |
|---|---|---|
| Purpose | Collect and land raw data | Validate, transform, store, serve |
| Network | VPC A `10.1.0.0/16`, private subnets | VPC B `10.2.0.0/16`, private subnets |
| Compute | EC2 scraper (later) | Lambda, Step Functions, Glue |
| Storage | S3 raw bucket, DynamoDB | S3 curated bucket, RDS PostgreSQL |
| Messaging | none | SQS queue + DLQ, SNS topic |
| Query | none | Glue Data Catalog + Athena |

CIDR blocks do not overlap so the VPCs can be peered.

## Components
1. **S3 raw bucket (A):** landing zone. Versioning on, public access blocked, encrypted. Event notification sends `ObjectCreated` events to the SQS queue in B.
2. **DynamoDB (A):** scrape and processing state. Key: `file_key`. Attributes: `status`, `received_at`, `record_count`, `run_id`.
3. **EC2 scraper (A):** private subnet, reaches S3 through a gateway endpoint, reached for administration through SSM Session Manager (no SSH, no public IP).
4. **SQS queue + DLQ (B):** buffers events. After N failed receives a message moves to the DLQ.
5. **Lambda (B):** thin trigger. Reads a queue message and starts a Step Functions execution. No heavy logic.
6. **Step Functions (B):** orchestrates Glue jobs with retries, catch blocks, and the failure path.
7. **Glue (B):** four stages: Data Quality, ETL to Parquet, load to RDS, Crawler.
8. **S3 curated bucket (B):** partitioned Parquet, plus a quarantine prefix for rejected records.
9. **Athena (B):** SQL over the curated data through the Data Catalog.
10. **RDS PostgreSQL (B):** private subnet, no public access, used for relational serving.
11. **SNS + CloudWatch (B):** alerts and dashboards.

## Cross-account access (the core of the project)
| Need | Mechanism | Where configured |
|---|---|---|
| S3 (A) notifies SQS (B) | SQS queue policy allowing the bucket's ARN and source account | B |
| Glue (B) reads raw files in A (ADR-002: direct read, no staging copy) | S3 bucket policy allowing the Glue job role from B, read-only on `raw/` | A (bucket policy), B (role policy) |
| Workflow (B) updates DynamoDB (A) and reads metadata | IAM role in A with a trust policy naming B's workflow role; B calls `sts:AssumeRole` | A (role), B (permission to assume) |
| Private path from A to RDS in B (optional) | VPC peering with routes and security group rules on both sides | A and B |

Rule of thumb: for resource policies and roles, permission must be granted on **both** sides (the caller's identity policy and the target's resource or trust policy).

Status (2026-10-20): the first three rows are built and tested. The policies are defined in Terraform (`terraform/account-a/s3.tf`, `iam.tf`; `terraform/account-b/sqs.tf`, `glue.tf`, `stepfunctions.tf`); resource names and settings are in [RESOURCE_INVENTORY.md](RESOURCE_INVENTORY.md). The DynamoDB role is `producer-state-writer`; its trust policy trusts account B limited by `aws:PrincipalArn`, because the caller (`platform-workflow-role`) is only created in Chunk 6.

## Network design

As built (2026-10-20, Account B): `platform-vpc` 10.20.0.0/16 with two private subnets (ap-south-1a, ap-south-1b), no internet gateway and no NAT. AWS services are reached through endpoints only: an S3 gateway endpoint (free, permanent) and interface endpoints for Secrets Manager, CloudWatch Logs and Glue (created per session in subnet 1a). Security groups reference each other instead of IP ranges: RDS accepts 5432 only from the Glue group, endpoints accept 443 only from the Glue group. Account A has no VPC yet; it is planned as 10.10.0.0/16 so the ranges never overlap if peering is added (ADR-003).

- VPC A: 2 private subnets across 2 AZs, S3 gateway endpoint, SSM interface endpoints if the scraper needs them. No NAT Gateway by default.
- VPC B: 2 private subnets across 2 AZs for RDS and Glue connections, S3 gateway endpoint. Glue jobs reach RDS through a Glue connection in the private subnet.
- Peering: requested from one side, accepted in the other, with route table entries and security group rules. Treated as an optional lab.

## Diagrams
- High-level design: see `diagrams/hld.md` (add the exported image to the repo).
- Process flow: see `DATA_FLOW.md`.

## Quality attributes
- Reliability: SQS buffering, retries, DLQ.
- Security: see `SECURITY.md`.
- Cost: serverless where possible, lab-only expensive resources.
- Operability: see `OBSERVABILITY.md` and `SLO.md`.

## Open questions
- Is the peering path useful enough to keep, or does it add complexity for little value?
