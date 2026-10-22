# Implementation plan

Build each account alone, test it, then connect them.

| Chunk | Where | Build | How to test | Output |
|---|---|---|---|---|
| 0. Prep | both | MFA, budgets, admin user, CLI profiles `acct-a` and `acct-b`, region `ap-south-1`, repo skeleton | `aws sts get-caller-identity --profile acct-a` and `acct-b` | both profiles work |
| 1. Account A alone | A | S3 raw bucket, DynamoDB `scrape_state`, data generator script with an upload step | file in bucket, row in table | AC-07 partly |
| 2. Account B alone | B | S3 curated bucket, SQS + DLQ, Lambda that only logs, Glue ETL job run by hand on a sample file | Lambda logs a test message, Parquet appears | components work alone |
| 3. Connect A and B | A ↔ B | bucket policy, queue policy, S3 event notification, Glue role access to A's bucket, AssumeRole | upload to A triggers the Lambda in B, Glue reads A's file | AC-01, AC-02 |
| 4. Glue stack | B | Data Quality ruleset, ETL, Crawler, Athena | Athena query matches valid record count | AC-03, AC-04 |
| 5. VPC | B (and A) | private subnets, S3 gateway endpoint, RDS, Glue JDBC connection and load job, optional peering | rows in RDS, rerun gives no duplicates | AC-05 |
| 6. Orchestration | B | Step Functions chaining all stages, retries, catch, DLQ handling, SNS | failure scenarios F-01 to F-05 | AC-06 |
| 7. Finish | both | EC2 scraper on a public practice site, Terraform for everything, README with diagrams, cost note | destroy then apply, e2e passes | AC-08, AC-09 |

## Status (2026-10-20)
Chunks 0-3 complete. Account A uses the `default` CLI profile (not `acct-a` as first planned); Account B uses `acct-b`; `acct-a-state-writer` assumes the role in A from B.

## Rules for working
1. Finish and test one chunk before starting the next.
2. Create paid resources (RDS, NAT, Glue runs) only for the lab session and tear them down after.
3. Manual console work first for learning, then rewrite in Terraform in chunk 7 (or per chunk if comfortable).
4. After each chunk, update `TASKS.md`, update personal notes (kept locally), and log any design choice in `DECISIONS_AND_TRADEOFFS.md`.

## Suggested pacing
About 1 to 2 chunks per week of focused evenings; chunks 3 and 5 are the hardest and deserve extra time.
