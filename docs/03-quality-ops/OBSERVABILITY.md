# Observability

## Logging
| Component | Where | Notes |
|---|---|---|
| Lambda | CloudWatch Logs | structured JSON logs with `run_id` and `file_key` |
| Step Functions | execution history and CloudWatch Logs | log level ERROR or ALL while learning |
| Glue | CloudWatch Logs (driver and executor) | enable job metrics |
| VPC | VPC Flow Logs to S3, queried in Athena | lab, short retention |
| API activity | CloudTrail | at least management events in both accounts |

Correlation id: `run_id` is carried through every stage so one file can be traced end to end.

### Where to look today (as built)
| What | Console | CLI |
|---|---|---|
| Lambda logs (`"msg": "file arrived"` with key, version id, size, SQS message id) | CloudWatch -> Log groups -> `/aws/lambda/platform-ingest-trigger` (search all streams), or Logs -> Live Tail | `aws logs tail /aws/lambda/platform-ingest-trigger --follow --profile acct-b` |
| Glue `print` output (record counts) | Glue -> job -> Runs -> Output logs (`/aws-glue/jobs/output`) | |
| Glue errors | Glue -> job -> Runs -> Error logs (`/aws-glue/jobs/error`) | |
| Messages that failed 3 times | SQS -> `platform-ingest-dlq` -> Send and receive messages -> Poll | |
| File status | Account A -> DynamoDB -> `scrape_state` -> Explore table items | |
| One file's run, step by step | Step Functions -> `platform-ingest-workflow` -> Executions (name starts with the file name) | `aws stepfunctions list-executions --state-machine-arn arn:aws:states:ap-south-1:<ACCOUNT_B_ID>:stateMachine:platform-ingest-workflow --profile acct-b` |
| Which run processed a file | Account A -> DynamoDB `scrape_state` row: `run_id` (execution name), `glue_run_id`, `processed_at`, `status`, `error_message` | |
| Alerts | email from SNS topic `platform-alerts` (workflow failures, DLQ alarm) | |
| Who assumed `producer-state-writer` | Account A -> CloudTrail -> Event history, event name `AssumeRole` (appears after 5-15 min) | |

Git Bash on Windows rewrites arguments that start with `/` (such as `/aws/lambda/...`) into Windows paths; set `MSYS_NO_PATHCONV=1`, or use CMD or PowerShell for `aws logs` commands.

## Metrics and alarms
| Alarm | Condition | Action |
|---|---|---|
| DLQ not empty | messages visible in DLQ > 0 | SNS email |
| Step Functions failures | `ExecutionsFailed` > 0 | SNS email |
| Glue job failure | job state FAILED | SNS email |
| Data quality threshold | quarantined share above limit | SNS email |
| Budget | actual or forecast above budget | AWS Budgets email |
| RDS | CPU or free storage out of range | email (only while RDS runs) |

## Dashboard (CloudWatch)
- Files received, files processed, files failed per day
- Step Functions success rate and duration
- Glue job duration and DPU usage
- DLQ depth
- Estimated cost (from Budgets or Cost Explorer, checked manually)

## Runbook stubs
- **DLQ has messages:** inspect message, find `run_id`, open Step Functions execution, read the failed state's error, fix, re-upload or redrive.
- **AccessDenied in a cross-account call:** check both sides, the caller's identity policy and the target's resource or trust policy, then check CloudTrail for the denied call.
- **Glue AccessDenied on `<prefix>_$folder$`:** Glue's S3 file system writes empty folder-marker objects next to the output prefix (for example `curated_$folder$`). A policy scoped to `curated/*` does not cover it; add that exact key to the role's write statement (seen 2026-10-20).
- **Console form shows "No subnet available" for a new VPC (endpoint wizard):** validate with `aws ec2 create-vpc-endpoint --dry-run ...`; if it says the request would succeed, create it from the CLI.
- **Glue load job cannot reach a service from inside the VPC:** each AWS API the job calls needs an endpoint (S3 gateway; Secrets Manager, Logs, Glue interface) and the endpoint security group must allow 443 from `platform-glue-sg`.
- **Test message in the DLQ:** a message that fails 3 receives moves to `platform-ingest-dlq` after roughly 3 x the 180 s visibility timeout. Inspect it, then delete or redrive.
