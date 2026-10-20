# Project brief

## One-line summary
A cross-account, event-driven data pipeline on AWS: a **producer account** collects raw data, and a **platform account** validates, transforms, stores and serves it, with AWS Glue doing the heavy processing.

## Why this project exists
| Goal | How the project serves it |
|---|---|
| Learn multi-account AWS | Two real accounts with a clear split of responsibility, linked by resource policies, `sts:AssumeRole` and VPC peering |
| Get hands-on VPC experience | Private subnets, S3 gateway endpoint, security groups, RDS in a private subnet, cross-account peering |
| Practise data engineering on AWS | S3 → SQS → Lambda → Step Functions → Glue (ETL, Data Quality, Crawler) → Athena and RDS |
| Build a portfolio piece | Public GitHub repo with Terraform, diagrams, docs and a clear story |
| Prepare for platform-engineering interviews | Documented trade-offs, security model, observability and failure handling |

## The two accounts
| Account | Plan | Role | Owns |
|---|---|---|---|
| A | Free tier | Producer / ingestion | VPC A, EC2 scraper, S3 raw bucket, DynamoDB scrape state |
| B | Paid | Platform | VPC B, SQS + DLQ, Lambda, Step Functions, Glue, S3 curated bucket, Athena, RDS PostgreSQL, SNS, CloudWatch |

## Scope
**In scope**
- Synthetic product-style JSON data (with deliberate bad records), later a scraper over a public practice site.
- Event-driven handoff from A to B.
- Glue Data Quality, Glue ETL (PySpark), Glue load job to RDS, Glue Crawler, Athena queries.
- Failure handling: retries, quarantine, DLQ, SNS alert.
- Infrastructure as code (Terraform) and written documentation.

**Out of scope**
- Any employer or client data, scrapers or documents.
- Production-grade scale, multi-region, or high availability.
- A front-end or BI dashboard (Athena queries are the "serving" layer).
- Transit Gateway and other services that cost a lot for little learning value.

## Data source (decision)
1. **Phase 1:** a Python generator creates ~20 JSON files of product records (name, category, price, scraped_at), including intentionally bad rows.
2. **Later:** an EC2 scraper reads a public site built for scraping practice (for example books.toscrape.com) and writes the same JSON format.

## Success looks like
- One upload to the raw bucket in Account A produces cleaned Parquet, a loaded RDS table and queryable Athena results in Account B with no manual steps.
- A bad file triggers retries, lands in quarantine/DLQ and sends an email alert.
- `terraform destroy` removes everything and `terraform apply` rebuilds it.
- Monthly cost stays inside the budget (see `RISKS.md`).

## Stakeholders
Single owner and learner (Ali). The "audience" is future interviewers reading the repo.
