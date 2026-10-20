# Requirements

IDs are referenced from `USER_STORIES.md`, `ACCEPTANCE_CRITERIA.md` and `TASKS.md`.

## Functional requirements
| ID | Requirement | Priority |
|---|---|---|
| FR-01 | A script generates sample product JSON files, including a configurable share of bad records | Must |
| FR-02 | Raw files are stored in an S3 bucket in Account A, and a metadata row per file is written to DynamoDB | Must |
| FR-03 | A new object in the raw bucket sends an event to an SQS queue in Account B | Must |
| FR-04 | A Lambda in Account B consumes queue messages and starts a Step Functions execution | Must |
| FR-05 | Account B can read raw files from Account A without long-term credentials (bucket policy and/or AssumeRole) | Must |
| FR-06 | Glue Data Quality evaluates each file against defined rules and separates passing from failing records | Must |
| FR-07 | A Glue ETL job cleans and flattens valid records and writes partitioned Parquet to the curated bucket | Must |
| FR-08 | A Glue job loads curated rows into RDS PostgreSQL over a private connection | Should |
| FR-09 | A Glue Crawler keeps the Data Catalog current so Athena can query curated data | Must |
| FR-10 | Step Functions orchestrates the Glue stages with retries and error handling | Must |
| FR-11 | Failing files are quarantined, the message ends in a DLQ, and an SNS email is sent | Must |
| FR-12 | The pipeline updates scrape/processing status in DynamoDB in Account A via an assumed role | Should |
| FR-13 | An EC2 scraper in a private subnet in Account A replaces the manual generator | Could |
| FR-14 | VPC peering lets private resources in A reach RDS in B (optional path) | Could |

## Non-functional requirements
| ID | Requirement | Target |
|---|---|---|
| NFR-01 | Cost | Stay within the monthly budget in `RISKS.md`; expensive resources are created only for lab sessions |
| NFR-02 | Security | No public S3 buckets, no public RDS, no static credentials in code, least-privilege IAM (see `SECURITY.md`) |
| NFR-03 | Reproducibility | Everything deployable and destroyable through Terraform |
| NFR-04 | Observability | Every stage emits logs and metrics, and failures alert by email (see `OBSERVABILITY.md`) |
| NFR-05 | Idempotency | Re-processing the same file must not create duplicate rows |
| NFR-06 | Documentation | Architecture, data flow and decisions documented in the repo |
| NFR-07 | Region | Single region (`ap-south-1`) to keep latency, cost and complexity simple |

## Constraints
- Account A is on a free plan; services that cost money (RDS, Glue, NAT) live in Account B.
- Only synthetic or public data is used.
- One person builds and operates the system.

## Assumptions
- Both accounts have MFA on root, budget alerts and an admin IAM user (or Identity Center) for lab work.
- The free-tier account's plan and credit rules are checked in the Billing console before creating paid services.
