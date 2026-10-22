# Resource inventory

Everything that exists in AWS right now, with the settings chosen in the console. This is the
checklist for rewriting the stack in Terraform (Chunk 7): every row here must become code.

> **Since 2026-10-22 (Chunk 7b) every resource below is created by Terraform** (`terraform/account-a`, `terraform/account-b`, state in `terraform/bootstrap`). The code is now the source of truth; this page records what the console build looked like and why each setting was chosen. Resource IDs (VPC, subnets, security groups, endpoints) changed when Terraform recreated them. Differences from the console build: tags on everything, 14-day Lambda log retention, TLS-only bucket policies, lifecycle rules, no `AWSLambdaBasicExecutionRole`, no crawler (the `products` table is declared), no RDS storage autoscaling, and RDS/interface endpoints controlled by `enable_rds`. The JSON policy files named in the tables were retired in Chunk 7c; the policies now live in the Terraform files. After recreating RDS no job parameters need editing: Terraform passes the new address and secret to the load job.

Region for everything: `ap-south-1` (Mumbai). Last updated: 2026-10-20 (end of Chunk 6).

## Accounts and CLI profiles
| Account | ID | Role | Admin identity | CLI profile |
|---|---|---|---|---|
| A | `<ACCOUNT_A_ID>` | producer (free tier) | IAM user `<ADMIN_USER_A>` | `default` |
| B | `<ACCOUNT_B_ID>` | platform (paid) | IAM user `<ADMIN_USER_B>` (group `admin`, `AdministratorAccess`) | `acct-b` |
| A, assumed from B | `<ACCOUNT_A_ID>` | role `producer-state-writer` | no longer usable by `<ADMIN_USER_B>` (only the workflow role) | `acct-a-state-writer` (now returns AccessDenied; can be deleted from `~/.aws/config`) |

Both admin identities use long-lived access keys. Before publishing: rotate or delete them, or move to IAM Identity Center.

## Account A (producer)
| Resource | Name | Settings | Policy file |
|---|---|---|---|
| S3 bucket | `producer-aws-<ACCOUNT_A_ID>-ap-south-1-an` | Block Public Access on (all 4), ACLs disabled, versioning **Enabled**, SSE-S3, no tags yet | bucket policy: `policies/account-a/raw-bucket-policy.json` |
| S3 event notification | `to-platform-ingest-queue` | `s3:ObjectCreated:*`, prefix `raw/`, suffix `.json`, destination SQS `arn:aws:sqs:ap-south-1:<ACCOUNT_B_ID>:platform-ingest-queue` | |
| DynamoDB table | `scrape_state` | partition key `file_key` (String), no sort key, on-demand, AWS-owned encryption key | |
| IAM role | `producer-state-writer` | trusted by account B, limited by `aws:PrincipalArn` to `role/platform-workflow-role` only (test user removed 2026-10-20); max session 1 h; inline policy `scrape-state-update` | `policies/account-a/state-writer-trust-policy.json`, `policies/account-a/state-writer-permissions-policy.json` |

Not part of this project, leave alone: DynamoDB tables `Users` and `UserPosts` in Account A.

## Account B (platform)
| Resource | Name | Settings | Policy file |
|---|---|---|---|
| S3 bucket | `platform-aws-<ACCOUNT_B_ID>-ap-south-1-an` | Block Public Access on (all 4), ACLs disabled, versioning **Suspended** (behaves as off), SSE-S3 | |
| SQS queue | `platform-ingest-queue` | Standard, visibility timeout 180 s, retention 4 days, receive wait 20 s, SSE-SQS, redrive to DLQ after 3 receives | `policies/account-b/sqs-ingest-queue-policy.json` |
| SQS DLQ | `platform-ingest-dlq` | Standard, retention 14 days, SSE-SQS | default (owner only) |
| Lambda | `platform-ingest-trigger` | Python 3.12, arm64, 128 MB, timeout 30 s, handler `lambda_function.lambda_handler`, code `src/lambda/ingest_trigger/handler.py` | |
| Lambda trigger | SQS → `platform-ingest-trigger` | batch size 10, batch window 0, report batch item failures on, maximum concurrency 2 | |
| Lambda environment | `platform-ingest-trigger` | `STATE_MACHINE_ARN=arn:aws:states:ap-south-1:<ACCOUNT_B_ID>:stateMachine:platform-ingest-workflow`; the function now starts one execution per file | |
| Step Functions | `platform-ingest-workflow` | Standard, logging off, X-Ray off; RunEtl (Glue .sync) -> RefreshPartitions (Athena `MSCK REPAIR TABLE products`) -> MarkProcessed (DynamoDB in A via `Credentials`); failures -> MarkFailed -> NotifyFailure -> Failed | `src/stepfunctions/ingest_workflow.asl.json` |
| IAM role | `platform-workflow-role` | trusted by `states.amazonaws.com` with `aws:SourceAccount` = B; inline `workflow-permissions` | `src/stepfunctions/trust-policy.json`, `src/stepfunctions/iam-policy.json` |
| SNS topic | `platform-alerts` | Standard; one confirmed email subscription | |
| CloudWatch alarm | `platform-dlq-not-empty` | `AWS/SQS ApproximateNumberOfMessagesVisible` on `platform-ingest-dlq`, Maximum > 0 over 5 min, missing data not breaching, action `platform-alerts` | |
| IAM role | `platform-ingest-trigger-role` | trusted by `lambda.amazonaws.com`; customer policy `platform-ingest-trigger-rolePolicy`; the console also attached `AWSLambdaBasicExecutionRole` (broader than needed, drop it in Terraform); statement `StartIngestWorkflow` allows `states:StartExecution` on `platform-ingest-workflow` only | `src/lambda/ingest_trigger/iam-policy.json` |
| Glue job | `platform-etl-products` | Spark, Glue 5.0, Python 3, G.1X x 2 workers, Flex execution, bookmarks off, retries 0, timeout 10 min, maximum concurrency 3, script `src/glue/etl_products.py` | |
| Glue job parameters | | `--input_path s3://producer-aws-<ACCOUNT_A_ID>-ap-south-1-an/raw/source=synthetic/date=2026-10-20/`, `--output_path s3://platform-aws-<ACCOUNT_B_ID>-ap-south-1-an/curated/products/` | |
| IAM role | `platform-glue-etl-role` | trusted by `glue.amazonaws.com`; managed `AWSGlueServiceRole` + inline `curated-bucket-access` | `src/glue/iam-policy.json` |
| Glue job parameters (Chunk 4 additions) | | `--quarantine_path s3://platform-aws-<ACCOUNT_B_ID>-ap-south-1-an/quarantine/products/`, `--dq_results_path s3://platform-aws-<ACCOUNT_B_ID>-ap-south-1-an/dq-results/products/`; `--input_path` currently file `raw/source=synthetic/date=2026-10-14/20261014T060000-001.json` | |
| Glue database | `platform_curated` | Data Catalog database | |
| Glue table | `platform_curated.products` | created by the crawler: Parquet at `curated/products/`, partition keys `date`, `category` (16 partitions on 2026-10-20) | |
| Glue crawler | `platform-curated-products-crawler` | S3 path `curated/products/`, crawl all sub-folders, on demand, target database `platform_curated` | role `service-role/AWSGlueServiceRole-platform-crawler` (console-created: `AWSGlueServiceRole` + an S3 policy for that path) |
| Athena workgroup | `platform-analytics` | engine v3, results `s3://platform-aws-<ACCOUNT_B_ID>-ap-south-1-an/athena-results/`, SSE-S3, expected bucket owner `<ACCOUNT_B_ID>`, override client settings on, per-query limit 1 GB (1073741824 bytes), CloudWatch metrics on | |
| VPC | `platform-vpc` `vpc-0d29a985ee1ed0de0` | 10.20.0.0/16, DNS hostnames and resolution on, no internet gateway, no NAT gateway | |
| Subnets | `platform-subnet-private1-ap-south-1a` `subnet-03c609a994867a89a` (10.20.128.0/20), `platform-subnet-private2-ap-south-1b` `subnet-07fdf8890ab7c348a` (10.20.144.0/20) | private, no public IPs; one route table each | |
| S3 gateway endpoint | `platform-vpce-s3` `vpce-0f8770351dd50f559` | attached to both private route tables, full-access policy (free, kept) | |
| Security group | `platform-glue-sg` `sg-05bd963faae2ff89f` | inbound all TCP from itself (required by Glue) | |
| Security group | `platform-rds-sg` `sg-0f0822f881f06ce8c` | inbound TCP 5432 from `platform-glue-sg` only | |
| Security group | `platform-endpoints-sg` `sg-09866b85b5660b2df` | inbound TCP 443 from `platform-glue-sg` only | |
| Glue connection | `platform-vpc-network` | type NETWORK, subnet 1a, `platform-glue-sg`; makes a job run inside the VPC | |
| Glue job | `platform-load-rds` | Glue 5.0, 2 x G.1X, Flex, 10 min, retries 0, connection `platform-vpc-network`, script `src/glue/load_rds.py`; parameters `--curated_path`, `--secret_id`, `--db_host`, `--db_name platform` | role `platform-glue-etl-role` (statement `ReadRdsSecret`) |
| CloudWatch log groups | `/aws/lambda/platform-ingest-trigger`, `/aws-glue/jobs/output`, `/aws-glue/jobs/error` | default retention (never expire): set a retention period in Terraform | |

## Data currently stored
| Where | What |
|---|---|
| A `raw/source=synthetic/date=2026-10-14` .. `date=2026-10-19` | 31 files from `generate.py` defaults (150,000 records, about 30.8 MB), one of them deliberately broken |
| A `raw/source=synthetic/date=2026-10-20` | 1 file, 100 records (live test of Chunk 3) |
| A `scrape_state` | 32 rows: 31 `RECEIVED`, 1 `PROCESSED` (the 2026-10-20 file, set manually through AssumeRole) |
| B `samples/raw/...` | one copied sample file used in Chunk 2 (can be deleted; see ADR-002 follow-ups) |
| B `curated/products/date=2026-10-14`, `date=2026-10-20` | Parquet from the Glue runs: 4,758 and 98 rows, one file per category |
| B `curated_$folder$`, `curated/products_$folder$` | empty folder markers written by Glue |
| B `quarantine/products/processed_date=2026-10-20/run_id=jr_0a61.../` | 242 rejected rows of file 001 with `failed_rules` |
| B `dq-results/products/run_id=jr_0a61.../` | rule scorecard of that run |
| B `athena-results/` | one CSV per Athena query |
| B `platform-ingest-dlq` | 1 deliberately broken test message (safe to delete) |

## Created per session, deleted afterwards (cost per hour)
| Resource | Settings to recreate with | Command or note |
|---|---|---|
| RDS `platform-db` | Full configuration, PostgreSQL latest, Free tier template, Single-AZ, db.t4g.micro, master user `platform_admin`, credentials managed in Secrets Manager, gp3 20 GiB, storage autoscaling off, VPC `platform-vpc`, public access No, security group `platform-rds-sg` only, AZ ap-south-1a, initial database `platform`, backups 1 day, encryption on, deletion protection off | delete: `aws rds delete-db-instance --db-instance-identifier platform-db --skip-final-snapshot --delete-automated-backups --profile acct-b` |
| Interface endpoints `secretsmanager`, `logs`, `glue` | VPC `platform-vpc`, subnet 1a only, `platform-endpoints-sg`, private DNS on | create: `aws ec2 create-vpc-endpoint --vpc-id vpc-0d29a985ee1ed0de0 --vpc-endpoint-type Interface --service-name com.amazonaws.ap-south-1.<service> --subnet-ids subnet-03c609a994867a89a --security-group-ids sg-09866b85b5660b2df --private-dns-enabled --profile acct-b` |

After recreating RDS, update the load job parameters `--db_host` (new endpoint) and `--secret_id` (new secret ARN), and the `ReadRdsSecret` resource in `src/glue/iam-policy.json`. The job recreates the tables itself.

Last session (2026-10-20): RDS endpoint was `platform-db.<RDS_ID>.ap-south-1.rds.amazonaws.com`; deleted at the end of the session together with the three interface endpoints.

## Temporary items to clean up
- ~~`user/<ADMIN_USER_B>` in the trust policy of `producer-state-writer`~~ removed 2026-10-20.
- ~~`ReadSamples` statement and `samples/` prefix in B~~ removed 2026-10-20.
- `AWSLambdaBasicExecutionRole` on the Lambda role.
