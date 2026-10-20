# Test strategy

## Principles
- Test each account on its own first, then test the connections.
- Use small, deterministic synthetic data so a failure points at the pipeline, not the data.
- Every acceptance criterion in `ACCEPTANCE_CRITERIA.md` has at least one test.

## Test levels
| Level | What | Tooling | When |
|---|---|---|---|
| Unit | Data generator, Lambda handler logic, PySpark transform functions | pytest, local Spark or plain Python | every change |
| Infrastructure validation | Terraform formatting, validation and plan review | `terraform fmt`, `validate`, `plan` | before every apply |
| Component | One service alone: Lambda with a test event, Glue job on a sample file, Athena query on sample Parquet | AWS CLI, console | each build chunk |
| Integration | A ↔ B connections: bucket policy, queue policy, AssumeRole, Glue reading A's bucket | AWS CLI with both profiles | chunk 3 |
| End to end | Upload a file in A, verify Parquet, RDS row, DynamoDB status | script in `tests/e2e/` | after each chunk |
| Failure | Corrupt file, missing permission, stopped RDS | manual scenarios below | chunk 6 |
| Security | Public access checks, IAM Access Analyzer, no static keys | AWS tools | before README is published |

## Test data sets
| Set | Contents | Purpose |
|---|---|---|
| `good_small.json` | 10 valid records | happy path |
| `mixed_quality.json` | valid records plus missing price, negative price, bad date, duplicate id, empty name | data quality |
| `corrupt.json` | invalid JSON | fail-fast path |
| `large.json` | a few thousand records | Glue behaviour and cost check |

## Failure scenarios
| ID | Scenario | Expected result |
|---|---|---|
| F-01 | Remove S3 read permission for the Glue role | Execution fails, clear AccessDenied in logs, alert sent |
| F-02 | Upload `corrupt.json` | Quarantine, `FAILED` status, DLQ message, email |
| F-03 | Stop RDS | Load step retries then fails, curated Parquet remains valid |
| F-04 | Upload the same file twice | No duplicate rows in RDS |
| F-05 | Wrong trust policy on the role in A | AssumeRole denied, logged and alerted |

## Tests run so far
| Date | Level | Test | Result |
|---|---|---|---|
| 2026-10-20 | Component | `generate.py` twice with the same seed | identical output |
| 2026-10-20 | Component | `upload.py --dry-run`, then 31 files | 31 objects in S3, 31 rows in DynamoDB; a rerun skips existing files |
| 2026-10-20 | Component | Lambda console test with `test_event.json` (one good, one broken message) | good message logged; `batchItemFailures` lists only the broken one |
| 2026-10-20 | Component | `sqs send-message` of a good and a broken message | Lambda invoked automatically; broken message retried, then moved to the DLQ |
| 2026-10-20 | Component | Glue ETL locally (PySpark 3.5.4) and in Glue on file 001 | 5,000 read, 4,758 valid, 216 invalid, 26 duplicates; one Parquet file per date/category folder |
| 2026-10-20 | Integration | Save the S3 event notification in A | S3 test event reached the Lambda in B |
| 2026-10-20 | Integration | Upload a new 100-record file in A | Lambda in B logged it within 1 s; version id identical in S3, DynamoDB and the log |
| 2026-10-20 | Integration | Glue in B with `--input_path` in A's bucket | 100 read, 98 valid written to B (direct cross-account read) |
| 2026-10-20 | Integration | AssumeRole `producer-state-writer` from B, `update-item` to `PROCESSED` | allowed; `Scan`, `DeleteItem` and `s3 ls` denied |
| 2026-10-20 | Component | Glue Data Quality run on file 001 | 4,758 valid, 242 quarantined (216 rule failures, 26 duplicates); per-reason counts match the generator manifest, 2 planted duplicates kept because their twin failed another rule |
| 2026-10-20 | Component | Crawler on `curated/products/` | table `products`, 9 columns with correct types, 16 partitions |
| 2026-10-20 | Acceptance (AC-04) | Athena `COUNT(*)` by date | 4,758 and 98, total 4,856, equal to Glue valid counts |
| 2026-10-20 | Integration | `platform-load-rds` inside the VPC (secret via endpoint, S3 via gateway, RDS on 5432) | 4,856 read, 4,856 inserted |
| 2026-10-20 | Acceptance (AC-05) | Run `platform-load-rds` a second time on the same data | 0 inserted, 4,856 skipped, table still 4,856 rows |
| 2026-10-20 | Infrastructure | Dry-run `create-vpc-endpoint` when the console form showed no subnets | request valid; created from the CLI instead |
| 2026-10-20 | Component | Manual Step Functions execution `manual-test-1` on the 2026-10-20 file | SUCCEEDED in about 4 min; A's row PROCESSED with `run_id` and `glue_run_id` |
| 2026-10-20 | End to end (AC-01, AC-07) | Upload a new 500-record file in A, no other action | Lambda started the workflow 1 s later; 471 valid, 29 quarantined (predicted beforehand); new date queryable in Athena; A's row PROCESSED |
| 2026-10-20 | Failure (DQ-08) | Upload a file with 42.5% bad rows | Glue failed on purpose, nothing in curated, 85 rows quarantined, A's row FAILED, email received |
| 2026-10-20 | Failure (F-02, AC-06) | Upload a file that is not valid JSON | 0 records read, Glue failed, A's row FAILED, email received |
| 2026-10-20 | Alarm | Leave one message in the DLQ | `platform-dlq-not-empty` went to ALARM |
| 2026-10-20 | Security (F-05 style) | AssumeRole with the removed test user | AccessDenied |

AC-06 note: in this design a corrupt file does not reach the DLQ, because the Lambda successfully starts the workflow; the workflow itself marks the file FAILED and sends the email. The DLQ (and its alarm) is for messages the Lambda cannot handle.

Windows note: local Spark reads JSON and runs transforms, but writing or listing Parquet needs Hadoop's `winutils.exe`. Local checks stop before the write, and Parquet output is checked with `pyarrow`.

## Exit criteria
All acceptance criteria pass, all failure scenarios behave as listed, and the e2e script runs clean from a fresh `terraform apply`.
