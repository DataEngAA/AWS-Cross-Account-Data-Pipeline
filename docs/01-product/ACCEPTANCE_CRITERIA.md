# Acceptance criteria

Format: Given / When / Then. Each criterion maps to a user story and is checked off in `DEFINITION_OF_DONE.md`.

## AC-01 Upload triggers processing (US-01, US-02)
- **Given** the stack is deployed
- **When** a valid JSON file is uploaded to the raw bucket in Account A
- **Then** a message appears in the SQS queue in Account B within 1 minute and a Step Functions execution starts.

## AC-02 Cross-account read works without shared keys (US-03)
- **Given** no access keys for Account A exist in Account B
- **When** the Glue job reads the raw file
- **Then** the read succeeds through the bucket policy or assumed role, and CloudTrail shows the calling role.

## AC-03 Bad data is separated (US-04)
- **Given** a file containing records with a missing price and an invalid date
- **When** Glue Data Quality runs
- **Then** the invalid records are written to a quarantine prefix, valid records continue, and the counts are logged.

## AC-04 Curated output is queryable (US-05)
- **Given** a successful run
- **When** I run `SELECT category, COUNT(*) ... GROUP BY category` in Athena
- **Then** the result matches the number of valid records uploaded.

## AC-05 RDS load is correct and idempotent (US-06)
- **Given** a successful run
- **When** the same file is processed a second time
- **Then** RDS contains no duplicate rows for that file.

## AC-06 Failure path alerts (US-07)
- **Given** a deliberately corrupt file
- **When** the workflow fails after its configured retries
- **Then** the message lands in the DLQ, the file is quarantined, and an SNS email arrives.

## AC-07 State is tracked (US-08)
- **When** a file is processed
- **Then** DynamoDB in Account A has a row for it with a status of `RECEIVED`, `PROCESSED` or `FAILED`.

## AC-08 Reproducible deployment (US-09)
- **When** I run `terraform destroy` and then `terraform apply`
- **Then** the same working pipeline exists and AC-01 passes again.

## AC-09 Documentation (US-10)
- **Then** the README contains both architecture diagrams, a cost note and a "how to run" section that a stranger could follow.
