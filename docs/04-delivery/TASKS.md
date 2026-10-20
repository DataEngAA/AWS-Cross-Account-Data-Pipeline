# Tasks

Legend: `[ ]` to do, `[x]` done. Update as you go.

## Chunk 0: prep
- [x] Enable MFA on root in both accounts
- [x] Create a budget alert in both accounts
- [x] Create an admin IAM user (or Identity Center) in both accounts: A `<ADMIN_USER_A>`, B `<ADMIN_USER_B>`
- [ ] Configure CLI profiles `acct-a` and `acct-b`
- [x] Verify with `aws sts get-caller-identity` for both
- [ ] Check the free account's plan and credit rules in Billing
- [x] Create the Git repo with this docs folder and a `.gitignore` (local repo `aws-multi-account-pipeline`, branch `main`, 2026-10-20; not pushed to GitHub yet)

## Chunk 1: Account A alone
- [x] Create the raw S3 bucket (block public access, versioning, encryption): `producer-aws-<ACCOUNT_A_ID>-ap-south-1-an`
- [x] Create the `scrape_state` DynamoDB table
- [x] Write the data generator (good and bad records): `src/generator/generate.py`
- [x] Upload script that writes the file and a DynamoDB row: `src/generator/upload.py`
- [x] Verify both appear (31 objects, 31 rows, 2026-10-20)

## Chunk 2: Account B alone
- [x] Create the curated S3 bucket: `platform-aws-<ACCOUNT_B_ID>-ap-south-1-an`
- [x] Create SQS queue and DLQ with a redrive policy: `platform-ingest-queue` -> `platform-ingest-dlq` after 3 receives
- [x] Create a logging-only Lambda and test with a sample event: `platform-ingest-trigger` (Python 3.12, arm64, 30 s), SQS trigger batch 10 with partial batch responses
- [x] Create and run a Glue ETL job on a sample file by hand: `platform-etl-products` (Glue 5.0, 2x G.1X, Flex), 5,000 in -> 4,758 rows in curated Parquet

## Chunk 3: connect A and B
- [x] S3 event notification to the SQS queue in B (queue policy first): `policies/account-b/sqs-ingest-queue-policy.json`, notification `to-platform-ingest-queue` (raw/, .json)
- [x] Bucket policy in A for the Glue role in B (ADR-002, direct read): `policies/account-a/raw-bucket-policy.json`; Glue read 100 records from A, wrote 98 to curated
- [x] Role in A with a trust policy for B, and AssumeRole from B: `producer-state-writer` (GetItem/UpdateItem on `scrape_state` only); tested via CLI profile `acct-a-state-writer`, Scan/DeleteItem/S3 denied
- [x] Test: upload in A triggers the Lambda in B (2026-10-20, version id matches S3 and DynamoDB)

## Chunk 4: Glue stack
- [x] Data Quality ruleset and quarantine output: DQDL in `src/glue/etl_products.py`; file 001 gave 4,758 valid, 242 quarantined with reasons (manifest planted 244; 2 planted duplicates were kept because their twin was already rejected for another rule)
- [x] ETL to partitioned Parquet (`date`, `category`, one file per folder)
- [x] Crawler and Data Catalog: crawler `platform-curated-products-crawler` (role `AWSGlueServiceRole-platform-crawler`), database `platform_curated`, table `products`, 16 partitions
- [x] Athena workgroup and test queries: `platform-analytics` (results to `athena-results/`, SSE-S3, 1 GB per-query limit); AC-04 passed: 4,758 + 98 = 4,856 rows match the Glue valid counts
- [ ] Later (Chunk 6): workgroup data usage alert once the SNS topic exists; lifecycle rule to expire `athena-results/`

## Chunk 5: VPC
- [x] VPC and private subnets in B, S3 gateway endpoint: `platform-vpc` 10.20.0.0/16, private subnets in 1a and 1b, no IGW, no NAT; security groups `platform-glue-sg`, `platform-rds-sg`, `platform-endpoints-sg`; interface endpoints for Secrets Manager, Logs and Glue (1a only, created for the session)
- [x] RDS PostgreSQL in a private subnet, credentials in Secrets Manager: `platform-db` db.t4g.micro, PostgreSQL 18.3, no public access, RDS-managed secret (deleted after the session, see RESOURCE_INVENTORY to recreate)
- [x] Glue connection and load job: Network connection `platform-vpc-network`, job `platform-load-rds` (`src/glue/load_rds.py`); 4,856 rows loaded, a second run inserted 0 (AC-05 passed)
- [ ] (Optional) VPC peering between A and B (ADR-003, not decided yet)

## Chunk 6: orchestration
- [x] Step Functions state machine for all stages: `platform-ingest-workflow` (RunEtl -> RefreshPartitions (MSCK REPAIR) -> MarkProcessed via AssumeRole into A), role `platform-workflow-role`; e2e upload of a 500-record file ran with no manual step (471 valid, PROCESSED in A, new date queryable in Athena)
- [x] Retries, catch blocks, quarantine and DLQ handling: Glue retries on concurrency/throttling, Catch -> MarkFailed -> NotifyFailure; tested with a 42.5%-bad file (DQ-08) and a corrupt file (F-02): both FAILED in A, emails received, nothing written to curated
- [ ] Improvement: put the Glue error message (not just `States.TaskFailed`) into `error_message` in A
- [x] Create `platform-workflow-role` with `sts:AssumeRole` on `producer-state-writer`, then remove the temporary `user/<ADMIN_USER_B>` entry from that role's trust policy in A (verified: the test profile now gets AccessDenied)
- [x] Lambda starts the workflow (`STATE_MACHINE_ARN`, deterministic execution name, duplicate events ignored); SQS trigger maximum concurrency 2; Glue ETL maximum concurrency 3
- [x] Remove the `samples/` copy and the Glue role's `ReadSamples` permission (ADR-002 follow-up)
- [ ] Optional: RDS load as a workflow step for sessions when RDS exists
- [x] SNS topic `platform-alerts` with a confirmed email subscription; failure emails tested
- [x] CloudWatch alarm: DLQ not empty -> `platform-alerts` (`platform-dlq-not-empty`, fired on a leftover test message, back to OK after it was deleted)
- [ ] Run failure scenarios F-01 to F-05: F-02 done (corrupt file -> FAILED + email), DQ-08 done (42.5% bad -> FAILED + email, nothing in curated), F-05 effectively done (removed principal gets AccessDenied); F-01 and F-04 still to run, F-03 needs an RDS session

## Chunk 7: finish
- [ ] EC2 scraper in a private subnet reaching a public practice site
- [ ] Terraform for both accounts
- [ ] Secret scan and Access Analyzer check
- [ ] README with diagrams and cost note
- [ ] Final destroy and apply test

## Later: scale test
- [ ] Add a `--preset large` to the generator: ~22M records, JSON Lines, ~100 files of ~45 MB, 30 days, optional `--gzip` (~4.5-5 GB plain)
- [ ] Upload to a `backfill/` prefix that is not wired to the event trigger, and process it with one manual Glue run
- [ ] Record what broke (Glue workers, memory, file sizes, Athena scan cost) in `INTERVIEW_NOTES.md`
