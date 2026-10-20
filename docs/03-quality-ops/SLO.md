# Service level objectives

This is a learning project, so these are practice SLOs: small, measurable and useful for interview discussion.

| SLI | Target | How measured |
|---|---|---|
| Ingest latency: upload to Step Functions start | 95% within 1 minute | timestamps in DynamoDB and execution start time |
| End-to-end latency: upload to curated data queryable | 95% within 15 minutes for small files | `received_at` vs. completion time |
| Success rate | 95% of valid files processed without manual action | `PROCESSED` / total over 7 days |
| No data loss | 100% of failed messages end in DLQ or quarantine, never silently dropped | DLQ and quarantine reconciliation |
| Alert delivery | failure email within 5 minutes of final failure | test scenario F-02 |
| Cost | monthly spend within budget | AWS Budgets |

## Error budget
With a 95% success target over, say, 20 files, one failure is within budget; more than one means stop adding features and fix reliability.

## Review cadence
Check the dashboard after each build chunk and at the end of the project; record findings in `DECISIONS_AND_TRADEOFFS.md`.
