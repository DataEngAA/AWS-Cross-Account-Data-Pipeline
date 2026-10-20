# ADR-002: Glue reads raw files directly from Account A's bucket

- **Status:** Accepted
- **Date:** 2026-10-20
- **Deciders:** Ali

## Context
The Glue jobs run in Account B (platform), but the raw files live in Account A's bucket `producer-aws-<ACCOUNT_A_ID>-ap-south-1-an`. During Chunk 2 the ETL job read a hand-made copy under `samples/` in B's bucket, because B had no access to A. Chunk 3 has to decide how Glue gets at the raw data for real.

## Options considered
1. **Direct read (chosen).** A's bucket policy grants B's Glue role read access to `raw/`; B's role policy allows reading that bucket. Glue reads `s3://producer-.../raw/...` itself.
2. **Copy to staging in B.** The Lambda (or a step in the workflow) copies each new file into a `staging/` prefix in B, and Glue reads only from B.

## Decision
Use **direct read**. A's bucket policy names the exact role `arn:aws:iam::<ACCOUNT_B_ID>:role/platform-glue-etl-role` and allows only `s3:GetObject` on `raw/*` and `s3:ListBucket` limited to the `raw/` prefix.

## Consequences
**Positive**
- One copy of the raw data, owned by the producer. No duplicate storage or extra copy step to build, pay for and debug.
- The bucket policy is a real cross-account resource policy, with both sides required (A's bucket policy and B's role policy), which is the main thing this project is meant to teach.
- B never writes to A's bucket; access is read-only.

**Negative / risks**
- B depends on A's bucket being available and unchanged while a job runs. If A deletes or overwrites a file, a rerun reads the new state (versioning in A keeps old versions, but the job reads the latest unless told otherwise).
- The bucket policy contains B's account ID and role name; renaming the role breaks access until A's policy is updated.
- Any future encryption change in A (for example a customer-managed KMS key) also needs a key policy grant for the same role.

## Follow-ups
- Remove the temporary `samples/` read permission from the Glue role once the direct read is proven.
- If A ever needs to delete raw data on a schedule, revisit this ADR (staging or a replication rule would then make sense).
