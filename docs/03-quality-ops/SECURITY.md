# Security

## Principles
- Least privilege everywhere, with resource-level ARNs instead of `*` where possible.
- Roles and temporary credentials, not access keys, between accounts and services.
- Private by default: no public buckets, no public RDS, no public IPs on workers.
- Everything encrypted at rest and in transit.

## Account hygiene (both accounts)
- MFA on the root user, root not used for daily work.
- Admin IAM user or IAM Identity Center for the labs; access keys for the CLI rotated or removed after the project.
- Budget alert at the chosen limit.
- CloudTrail management events enabled.

## Cross-account trust model
| Trust | Who trusts whom | Controls |
|---|---|---|
| Raw bucket (A) readable by Glue role (B) | A's bucket policy names B's role ARN | actions limited to `s3:GetObject` and `s3:ListBucket` on specific prefixes |
| Queue (B) accepts events from bucket (A) | B's queue policy | condition on `aws:SourceArn` and `aws:SourceAccount` |
| Workflow (B) writes state to DynamoDB (A) | role in A with trust policy naming B's workflow role | actions limited to `GetItem` and `UpdateItem` on one table; trust policy names the exact calling role ARN (an external ID is mainly for third-party access, so it is optional between your own accounts) |
| Peering (optional) | route tables and security groups | only the required ports from the required CIDR |

Always grant the narrowest principal: a specific role ARN, not the whole account root, when possible.

### As built (2026-10-20)
| Trust | Exact grant | File |
|---|---|---|
| Raw bucket (A) -> Glue role (B) | `role/platform-glue-etl-role` may `s3:ListBucket` with `s3:prefix` `raw` or `raw/*`, and `s3:GetObject` on `raw/*`. B's role policy grants the same on its side. | `terraform/account-a/s3.tf`, `terraform/account-b/glue.tf` |
| Queue (B) <- bucket (A) | `s3.amazonaws.com` may `sqs:SendMessage`, with conditions `aws:SourceArn` = raw bucket and `aws:SourceAccount` = A (protects against the confused deputy problem) | `terraform/account-b/sqs.tf` |
| B -> DynamoDB (A) | Role `producer-state-writer` in A. Principal is account B **with** an `aws:PrincipalArn` condition listing `role/platform-workflow-role` and, temporarily, `user/<ADMIN_USER_B>`. A role named directly as a principal must already exist; a condition does not need to. Permissions: `dynamodb:GetItem` and `dynamodb:UpdateItem` on `scrape_state` only. Verified: `Scan`, `DeleteItem` and `s3:ListBucket` are denied. | `terraform/account-a/iam.tf` |

Service roles in B: the Lambda role reads only `platform-ingest-queue` and writes only its own log group; the Glue role reads `raw/` in A and `samples/` in B and writes only `curated/` in B, plus the `curated_$folder$` marker object (see `OBSERVABILITY.md`).

Update (end of Chunk 6): the trust policy of `producer-state-writer` now names only `role/platform-workflow-role` (the test user gets AccessDenied), and that role is trusted only by Step Functions with `aws:SourceAccount` = B. The `samples/` read permission is removed.

Known gaps to close: console-added `AWSLambdaBasicExecutionRole`, long-lived access keys for both admin users, no TLS-only (`aws:SecureTransport`) statement on either bucket yet.

## Data protection
- S3: Block Public Access on, SSE-S3 or SSE-KMS, versioning on the raw bucket, TLS-only bucket policy.
- RDS: encrypted, private subnet group, security group allows only the Glue connection and approved sources, credentials in Secrets Manager.
- DynamoDB: encryption at rest (default).
- No employer or client data is ever stored in this project.

## Secrets
- No credentials in code, Terraform variables files, or Git history.
- `.gitignore` excludes `*.tfstate`, `*.tfvars`, `.env`, and any credentials files.
- Terraform state in an encrypted S3 backend (a small bootstrap step) or local state kept out of Git during early work.

## Checks before publishing the repo (done 2026-10-23, Chunk 7c)
- [x] Secret scan: trivy `fs --scanners secret` on the repo, canary-tested with a fake key (the AWS documentation example key is allow-listed by trivy, so the canary used a random one). 0 findings; no AWS key pattern anywhere in Git history.
- [x] IaC scan: checkov on all Terraform: 263 passed; 6 fixed (DynamoDB PITR, Glue security configuration, locked default security group, Step Functions error logging, state-bucket upload cleanup, RDS tag copy); 29 accepted with `#checkov:skip` reasons in the resource (customer-managed KMS, cross-region replication, access logging, curated versioning, log retention, SNS encryption, and false positives on the Glue self-referencing rule and the SQS-triggered Lambda).
- [x] IAM Access Analyzer (ACCOUNT type) in both accounts. A: raw bucket (B's Glue role) and producer-state-writer (account B) are intended and archived by Terraform archive rules matching exact resource and principal; a GitHub Actions OIDC role from another personal project is left to that project. B: no findings (S3 service access to the queue is not external access).
- [x] No resource allows `0.0.0.0/0` ingress; the VPC has no internet gateway or NAT, and its default security group has no rules.
- [x] Account IDs replaced by placeholders in all committed files and history; commit author uses the GitHub no-reply address.

Follow-ups: X-Ray tracing, VPC flow logs, CI running these scans on every push.
