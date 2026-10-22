# Learning plan

Each chunk teaches specific skills. Use the "can I explain it?" check before moving on.

| Chunk | Skills practised | Can I explain it? |
|---|---|---|
| 0 Prep | IAM users vs roles, MFA, budgets, CLI profiles and named credentials | Why not use root? How does the CLI pick a profile? |
| 1 Account A | S3 security settings, bucket naming, DynamoDB keys and access patterns, boto3 | Why is Block Public Access on? Why `file_key` as the partition key? |
| 2 Account B | SQS visibility timeout and DLQs, Lambda event sources and permissions, first Glue job | What happens to a message when the Lambda fails? |
| 3 Connect | Resource policies vs identity policies, trust policies, `sts:AssumeRole`, `aws:SourceArn` and `aws:SourceAccount` conditions | Which side needs which permission, and why both? |
| 4 Glue stack | Glue Data Quality (DQDL), PySpark transforms, partitioned Parquet, Data Catalog, Athena cost model | Why Parquet and partitions? What does the crawler actually do? |
| 5 VPC | CIDR planning, public vs private subnets, route tables, gateway endpoints, security groups vs NACLs, RDS subnet groups, peering | Why can a private instance reach S3 without internet? Why must peered CIDRs not overlap? |
| 6 Orchestration | Step Functions states, retry and catch, error handling, SNS, CloudWatch alarms | How do retries differ from the DLQ? |
| 7 Finish | Terraform modules, provider aliases for two accounts, state, README writing | How do I deploy to two accounts from one codebase? |

## Study resources to line up
- AWS documentation pages for each service above (use the official docs for current limits and prices).
- Your PySpark course materials for the Glue ETL chunk.
- Terraform documentation for the AWS provider.

## Habits
- After each chunk, write three sentences in personal notes (kept locally): what I built, what broke, what I learned.
- Break something on purpose once per chunk and fix it.
- Prefer console first to understand, then code it in Terraform.
