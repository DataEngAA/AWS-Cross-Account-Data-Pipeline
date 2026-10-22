# Decisions and trade-offs

Short log. Promote big ones to an ADR in `docs/adr/`.

| # | Decision | Alternatives | Why | Trade-off accepted |
|---|---|---|---|---|
| 1 | Producer/platform account split (ADR-001) | Lambda-triggers-EC2 only; dev/prod; three accounts | Gives each account a real job and real cross-account mechanisms | More setup and double-sided permission debugging |
| 2 | Glue does the heavy processing (DQ, ETL, load, crawler) | Lambda-only processing | Managed Spark, matches the Spark learning plan, common in data engineering roles | Glue costs money and starts slowly, so it lives in the paid account |
| 3 | Step Functions orchestrates, Lambda only triggers | Chain Lambdas, Glue Workflows | Native Glue integration, retries and visual debugging | One more service to learn |
| 4 | Synthetic data first, public practice site later | Real scraped data from the start | Controlled bad records, no legal or employer-data concerns | Less "real" at first |
| 5 | No employer or client data or code | Reuse existing scrapers or documents | Avoids confidentiality problems in a public portfolio | Data is simpler than real EPD or product data |
| 6 | Plain IAM trust between accounts, Organizations optional | Always use Organizations | Fewer moving parts, and consolidated billing can change free-tier behaviour | Less realistic governance (no SCPs) |
| 7 | One region, `ap-south-1` | Multi-region | Simplicity and cost | No DR story |
| 8 | Build manually first, Terraform after | Terraform from day one | Understand each service before abstracting it | Rewrite effort in chunk 7 |
| 9 | Keep expensive resources lab-only | Leave running | Budget control | Must recreate for each session |
| 10 | Synthetic data at volume (150k records default, 1M on demand) with `scraped_at` on every record | 50-record files; real API data now | Enough volume for Glue partitions and Athena to matter; per-record timestamp lets DQ-05 quarantine a single record | Real API sources (Open Prices, eBay) deferred to a later ADR |
| 11 | Glue in B reads raw files directly from A's bucket (ADR-002) | Copy each file to a staging prefix in B | One copy of raw data, read-only cross-account access, a real bucket policy to explain | B depends on A's bucket being available during a run |
| 12 | SSE-S3 on both buckets, not a customer-managed KMS key | SSE-KMS | Free, no key policy; a cross-account read of KMS-encrypted objects would also need a key policy grant | No key-level audit or separate key permissions |
| 13 | Versioning on in A's raw bucket, suspended (off) in B's curated bucket | Versioning on both | Raw data is the original and must survive overwrites; curated can be rebuilt from raw, and reruns would pile up old versions | No undo for curated files |
| 14 | DynamoDB on-demand | Provisioned capacity | No capacity planning, bursts of uploads are not throttled, cost is fractions of a cent | Higher per-request price at large steady volume |
| 15 | SQS Standard, visibility 180 s (6 x the 30 s Lambda timeout), DLQ after 3 receives, DLQ retention 14 days | FIFO; shorter timeouts | S3 cannot notify FIFO queues; 6 x timeout stops a retried batch being handed out twice | At-least-once delivery, so duplicates must be handled downstream |
| 16 | Lambda reports partial batch failures | Fail the whole batch | Only the bad message is retried and later sent to the DLQ | Handler must track message ids |
| 17 | Lambda on arm64 with a hand-written least-privilege policy | x86, console policy templates | About 20% cheaper; policy limited to one queue and one log group | Console still attached `AWSLambdaBasicExecutionRole` |
| 18 | Glue 5.0, 2 x G.1X, Flex, 10-minute timeout, no retries while developing | Defaults (10 workers, 480-minute timeout) | Smallest and cheapest; a stuck job cannot run for hours | Flex can start slower |
| 19 | `repartition("date", "category")` before writing | Spark default of 200 shuffle partitions | One file per folder instead of many tiny files, which keeps Athena fast and cheap | One task per folder; revisit in the scale test |
| 20 | Trust policy in A uses account B as principal plus an `aws:PrincipalArn` condition | Name the role directly as principal | The workflow role does not exist yet; a condition keeps working if the role is recreated | Slightly harder to read |
| 21 | IAM users with access keys for the CLI | IAM Identity Center | Quickest to set up for a two-account lab | Long-lived keys must be rotated or removed before publishing |
| 22 | No NAT gateway; S3 gateway endpoint plus interface endpoints for Secrets Manager, Logs and Glue | NAT gateway for outbound internet | Cheaper (about $0.035/h for three endpoints in one subnet vs $0.056/h plus data for NAT) and no path to the internet at all | Every new AWS service the job calls needs another endpoint |
| 23 | Interface endpoints in one subnet (ap-south-1a) only, created per session | One per AZ, kept running | Halves the hourly cost; Glue and RDS run in 1a | No AZ redundancy for the endpoints |
| 24 | The Glue load job creates the tables and merges through a staging table with `ON CONFLICT DO NOTHING` | Bastion host or SSM instance to run DDL; Spark JDBC append straight into `products` | No extra server; reloads are idempotent because the primary key `(product_id, scraped_at)` absorbs repeats | DDL lives in job code, not a migration tool |
| 25 | RDS credentials managed by RDS in Secrets Manager; Glue reads them with boto3 | Password typed into a Glue JDBC connection | Nobody ever sees the password; access is one IAM statement on one secret ARN | The secret ARN changes whenever the database is recreated |
| 26 | Glue joins the VPC through a NETWORK connection; the job builds the JDBC URL itself (`sslmode=require`) | Glue JDBC connection with a connection test | Simpler and works with the RDS-managed secret | No console "test connection" button |
| 27 | RDS db.t4g.micro, Single-AZ, free tier, deleted after each session | Keep it running; Multi-AZ | Free tier covers the instance hours; deleting avoids burning the 750-hour allowance and any surprise | About 15 minutes to recreate each session |
| 28 | Workflow refreshes partitions with Athena `MSCK REPAIR TABLE` instead of running the crawler per file | Crawler after every file; partition projection | Crawler bills a 10-minute minimum (about $0.07 per run); MSCK costs fractions of a cent and needs no schema inference | MSCK lists all partitions, so it slows down as partitions grow; partition projection is the next step |
| 29 | Lambda names each execution from file name + hash(bucket, key, version id) | Random execution names | Step Functions rejects a duplicate name, so duplicate S3 events or SQS redeliveries cannot process a file version twice | Re-processing the same version needs a manual start with a new name |
| 30 | Concurrency limits: SQS trigger max 2 Lambdas, Glue ETL max 3 runs, workflow retries `ConcurrentRunsExceededException` | Unlimited | Protects cost and avoids Glue concurrency errors during bursts | Large bursts queue up and take longer |
| 31 | RDS load is not part of the automatic workflow yet | Always load RDS | RDS is deleted between sessions; the workflow must succeed without it | RDS is refreshed manually with `platform-load-rds` |
| 32 | Failure path marks the file FAILED in A and emails via SNS; a separate alarm watches the DLQ | Only CloudWatch alarms | The producer sees each file's outcome; the DLQ alarm covers failures before the workflow starts | `error_message` in A is only the generic Step Functions error name for now |
| 33 | Terraform: one root per account plus bootstrap, S3 state with native locking (ADR-005) | One root for both accounts | Separate blast radius and state per account, matching ADR-001 | Two applies in a fixed order (B, then A) |
| 34 | Cut over by recreating, importing only `scrape_state` | Import all 40 resources | A real test that code alone builds everything | Synthetic data deleted and regenerated |
| 35 | `allow_destroy_raw` guard on the raw bucket | `force_destroy = true` always | Deleting the producer's original data takes a deliberate tfvars change plus an apply | One extra step before a destroy test |
| 36 | Step Functions definition read from the tested JSON file with placeholders replaced | Rewrite it in HCL | One tested copy of the workflow | ARNs inside it are built from names, not references |
| 37 | Automated e2e test (`tests/e2e/run_e2e.py`) as the acceptance check | Manual console checks | Repeatable in about 5 minutes after any change or rebuild | Costs one Glue run per test |

## Open decisions
- Keep or drop VPC peering (ADR-003)
- Add a third logging account later? (ADR-004 if yes)
