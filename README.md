# AWS multi-account data pipeline

A cross-account, event-driven data pipeline on AWS. A **producer account** lands raw data in S3. A **platform account** validates, transforms, stores and serves it using SQS, Lambda, Step Functions, Glue, Athena and RDS.

> Personal learning project using synthetic or public practice data only.

## Status
Chunks 0-6 done and Chunk 7b done (2026-10-22): the whole pipeline is defined in Terraform (`terraform/bootstrap`, `terraform/account-b`, `terraform/account-a`), was destroyed and rebuilt from code, and passes `tests/e2e/run_e2e.py`. Before that, an upload in Account A is processed end to end with no manual step (Step Functions: ETL with data quality, partition refresh, status written back to A, email on failure). both accounts built and connected, data quality with quarantine, catalog and Athena, and a private RDS PostgreSQL loaded idempotently from Glue inside a VPC with no internet access. An upload in Account A triggers the Lambda in Account B, Glue in B reads A's raw bucket directly and writes partitioned Parquet, and B updates A's DynamoDB through AssumeRole. Next: Chunk 7c (security scans, README with diagrams, make the repo public). Progress is in `docs/04-delivery/TASKS.md`; everything that exists in AWS is listed in the [resource inventory](docs/02-architecture/RESOURCE_INVENTORY.md).

## Documentation map
New here or unsure which doc to open? Start with [How to use these docs](docs/HOW_TO_USE_THESE_DOCS.md).

### 01 Product and requirements
- [Project brief](docs/01-product/PROJECT_BRIEF.md)
- [Requirements](docs/01-product/REQUIREMENTS.md)
- [User stories](docs/01-product/USER_STORIES.md)
- [Acceptance criteria](docs/01-product/ACCEPTANCE_CRITERIA.md)

### 02 Architecture and design
- [Architecture](docs/02-architecture/ARCHITECTURE.md)
- [Data model](docs/02-architecture/DATA_MODEL.md)
- [Data flow](docs/02-architecture/DATA_FLOW.md)
- [Tech stack](docs/02-architecture/TECH_STACK.md)
- [Resource inventory](docs/02-architecture/RESOURCE_INVENTORY.md) (what is deployed, with settings)
- [ADR-001: producer/platform split](docs/adr/ADR-001-two-account-producer-platform-split.md)
- [ADR-002: Glue reads Account A's bucket directly](docs/adr/ADR-002-glue-reads-producer-bucket-directly.md)

### 03 Quality and operations
- [Test strategy](docs/03-quality-ops/TEST_STRATEGY.md)
- [Data quality](docs/03-quality-ops/DATA_QUALITY.md)
- [Observability](docs/03-quality-ops/OBSERVABILITY.md)
- [Security](docs/03-quality-ops/SECURITY.md)
- [SLO](docs/03-quality-ops/SLO.md)

### 04 Execution and delivery
- [Implementation plan](docs/04-delivery/IMPLEMENTATION_PLAN.md)
- [Tasks](docs/04-delivery/TASKS.md)
- [Definition of done](docs/04-delivery/DEFINITION_OF_DONE.md)
- [Risks](docs/04-delivery/RISKS.md)

### 05 Learning and interviews
- [Learning plan](docs/05-learning/LEARNING_PLAN.md)
- [Interview notes](docs/05-learning/INTERVIEW_NOTES.md)
- [Decisions and trade-offs](docs/05-learning/DECISIONS_AND_TRADEOFFS.md)

## Architecture at a glance
```
Account A (producer)                 Account B (platform)
EC2 scraper -> S3 raw  --event-->    SQS(+DLQ) -> Lambda -> Step Functions
DynamoDB state  <--AssumeRole--      Glue: DQ -> ETL -> load RDS -> Crawler
                                     S3 curated (Parquet) -> Athena
                                     RDS PostgreSQL (private)   SNS alerts
```
Add the exported HLD and flowchart images to `docs/02-architecture/diagrams/` and link them here.

## Repo layout
```
src/generator/               generate.py (synthetic data), upload.py (S3 + DynamoDB)
src/lambda/ingest_trigger/   handler.py, iam-policy.json, test_event.json
src/glue/                    etl_products.py (ETL + data quality), load_rds.py (RDS load), iam-policy.json
src/stepfunctions/           ingest_workflow.asl.json, workflow role trust and permissions
policies/account-a/          raw bucket policy, producer-state-writer trust and permissions
policies/account-b/          SQS queue policy
tests/manual/                inputs for manual cross-account tests
scripts/render.py            fills placeholders from local/accounts.env into build/
local/accounts.env.example   template for the real IDs (local/accounts.env is not committed)
docs/                        this documentation
terraform/                   (Chunk 7) account-a/ account-b/ modules/
```

## Account IDs and placeholders
Files in this repo use placeholders such as `<ACCOUNT_A_ID>`, `<ACCOUNT_B_ID>`, `<ADMIN_USER_A>` instead of real values, so no account details are published. To use them:

1. Copy `local/accounts.env.example` to `local/accounts.env` and fill in your values (this file is ignored by Git).
2. Run `python scripts/render.py`; ready-to-paste copies of every policy and the workflow definition are written to `build/` (also ignored).
3. `src/generator/upload.py` reads the raw bucket name from `local/accounts.env` (or `--bucket` / `$RAW_BUCKET`).

## Deploy with Terraform
Prerequisites: Terraform 1.10+, AWS CLI profiles `default` (Account A) and `acct-b` (Account B).

1. `terraform/bootstrap`: `terraform init` then `terraform apply` (state bucket, once).
2. In `terraform/account-b` and `terraform/account-a`: copy `backend.hcl.example` to `backend.hcl` and `terraform.tfvars.example` to `terraform.tfvars`, fill them in, then `terraform init "-backend-config=backend.hcl"`.
3. Apply **account-b first**, confirm the SNS email, then apply **account-a** (A's bucket policy names B's Glue role, which must exist).
4. Check: `python tests/e2e/run_e2e.py` (all three checks PASS).
5. Optional RDS session: `terraform apply -var "enable_rds=true"` in account-b, run the `platform-load-rds` Glue job, then apply again without the variable.
6. Tear down: `terraform destroy` in account-a (set `allow_destroy_raw = true` and apply first), then account-b.

## First steps
1. Read [How to use these docs](docs/HOW_TO_USE_THESE_DOCS.md), then `IMPLEMENTATION_PLAN.md`.
2. Complete Chunk 0 in `TASKS.md` (MFA, budgets, two CLI profiles).
3. Start Chunk 1 (Account A alone).
