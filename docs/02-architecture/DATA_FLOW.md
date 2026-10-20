# Data flow

## Happy path
| Step | Where | What happens |
|---|---|---|
| 1 | A | Generator or scraper writes `raw/.../<run_id>.json` to the raw bucket and creates a `RECEIVED` row in DynamoDB |
| 2 | A → B | S3 `ObjectCreated` event is sent to the SQS queue in B |
| 3 | B | Lambda polls the queue and starts a Step Functions execution (execution name = `run_id`) |
| 4 | B | Glue Data Quality evaluates the file against the ruleset |
| 5 | B | Glue ETL job cleans, flattens and writes partitioned Parquet to the curated bucket |
| 6 | B | Glue load job writes the same rows to RDS (idempotent upsert) |
| 7 | B | Glue Crawler updates the Data Catalog |
| 8 | B → A | Workflow assumes the role in A and sets DynamoDB status to `PROCESSED` |
| 9 | B | Athena queries curated Parquet; RDS serves SQL queries |

Status (2026-10-20, end of Chunk 6): steps 1-5, 7 and 8 run automatically. Step 4 is inside the ETL job (Glue Data Quality), step 7 uses Athena `MSCK REPAIR TABLE` instead of the crawler, and step 6 (RDS load) runs by hand with `platform-load-rds` when an RDS session is active. The execution name is `<file name>-<hash of bucket, key, version id>`. Failures go MarkFailed (DynamoDB in A) -> NotifyFailure (SNS email). The DLQ only receives messages the Lambda itself cannot handle, watched by the `platform-dlq-not-empty` alarm.

## Failure path
| Situation | Behaviour |
|---|---|
| Transient error in a Glue job (throttling, brief network issue) | Step Functions retries with backoff, up to 3 attempts |
| Data quality failure for some records | Bad records go to `quarantine/`, good records continue, counts are logged |
| File cannot be parsed at all | Execution fails fast, file is quarantined, status set to `FAILED` |
| Retries exhausted | Catch block sets `FAILED`, SNS email is sent, the SQS message moves to the DLQ after its max receives |
| Poison message in the queue | DLQ keeps it for inspection and replay |

## Idempotency
- Execution name is derived from the S3 object key and version, so a duplicate event does not start a second run for the same object.
- RDS load uses a primary key and `ON CONFLICT`.
- Curated Parquet for a run is written to a run-specific path then swapped, or overwritten by partition, so reruns replace rather than append.

## Sequence diagram (text)
```
Producer(A) -> S3 raw(A): put file
S3 raw(A) -> SQS(B): ObjectCreated event
SQS(B) -> Lambda(B): message
Lambda(B) -> StepFunctions(B): start execution
StepFunctions(B) -> Glue DQ(B): run
StepFunctions(B) -> Glue ETL(B): run (reads S3 raw in A)
StepFunctions(B) -> Glue load(B): run (writes RDS in B)
StepFunctions(B) -> Glue crawler(B): run
StepFunctions(B) -> IAM role(A): AssumeRole
StepFunctions(B) -> DynamoDB(A): status = PROCESSED
```

The rendered HLD and flowchart diagrams from the planning chat should be exported and saved in `docs/02-architecture/diagrams/`.
