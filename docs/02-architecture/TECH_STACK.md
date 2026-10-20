# Tech stack

| Layer | Choice | Why | Alternatives considered |
|---|---|---|---|
| Cloud | AWS, region `ap-south-1` | Target skill set for the roles being applied for | Azure, GCP |
| Accounts | 2 (producer, platform), joined with plain IAM trust, Organizations optional | Realistic separation without a third account | 3 accounts with a security/logging account |
| IaC | Terraform | Common in platform roles, reusable across accounts via provider aliases | CloudFormation, CDK |
| Storage | S3 (raw, curated), Parquet | Cheap, durable, columnar | Delta/Iceberg tables (possible later extension) |
| State store | DynamoDB | Serverless, key-value access pattern, free allowance | RDS table |
| Messaging | SQS + DLQ | Decouples accounts, buffers spikes | SNS fan-out, EventBridge |
| Trigger | Lambda (Python) | Small glue code | Direct EventBridge to Step Functions |
| Orchestration | Step Functions | Native Glue integration, retries, visual debugging | Airflow (MWAA too costly), Glue Workflows |
| Processing | Glue ETL (PySpark), Glue Data Quality, Glue Crawler | Managed Spark, aligns with Spark learning plan | Lambda only, EMR |
| Query | Athena + Glue Data Catalog | Pay per data scanned | Redshift Serverless (more costly) |
| Relational | RDS PostgreSQL (smallest instance) | Real VPC and private-subnet practice | Aurora Serverless |
| Network | VPC, private subnets, gateway endpoints, SSM, VPC peering | Core hands-on goal | Transit Gateway (too costly) |
| Alerts | SNS email, CloudWatch alarms and dashboard | Simple and cheap | PagerDuty and others |
| Language | Python 3.12 | Lambda, Glue, scripts | |
| Local tooling | AWS CLI v2 with two named profiles, Terraform, pytest, Git | | |

## Versions to pin (fill in when scaffolding)
- Terraform: ____ (Chunk 7)
- AWS provider: ____ (Chunk 7)
- Glue version: 5.0 (Spark 3.5.4, Python 3); local tests use `pyspark==3.5.4` with Java 17
- Python (Lambda runtime): 3.12 on arm64
- Local Python: 3.12 with `boto3`; AWS CLI v2.32

## Cost notes
Check current AWS pricing for your region before each lab session. Glue ETL is billed per DPU-hour, RDS and NAT Gateway bill by the hour, and public IPv4 addresses are charged. Details and limits are in `RISKS.md`.
