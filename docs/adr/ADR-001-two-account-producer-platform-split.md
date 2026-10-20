# ADR-001: Split accounts into producer and platform

- **Status:** Accepted
- **Date:** 2026-10-20
- **Deciders:** Ali

## Context
The goal is to learn multi-account AWS and VPC networking and to have a believable portfolio project. A first idea was "Account B only runs a Lambda that triggers EC2 in Account A". That makes the second account look like an afterthought and gives it no reason to exist.

## Options considered
1. **Lambda in one account triggers EC2 in the other.** Simple, but one thin integration and no ownership story.
2. **Dev/prod split.** Realistic but both accounts would hold the same services, so less cross-account learning.
3. **Producer/platform split (chosen).** Each account owns a clear responsibility and the handoff between them needs real cross-account mechanisms.
4. **Three accounts, adding security/logging.** Very realistic but needs a third AWS account and email, and adds work before the core is built.

## Decision
Use two accounts: **A (free tier) = producer** and **B (paid) = platform**. Account A holds the raw bucket, DynamoDB state and the scraper. Account B holds messaging, orchestration, Glue, curated storage, Athena and RDS.

## Consequences
**Positive**
- Every cross-account mechanism has a real reason to exist: S3 to SQS event, bucket policy for reads, AssumeRole for state updates, and optional VPC peering.
- Costly services stay in the paid account; the free-tier account stays cheap.
- Easy to explain in an interview: "the producer has no access to analytics data, and I can show the policies that enforce it".

**Negative / risks**
- More setup (two CLI profiles, two Terraform providers).
- Debugging permission errors needs a check on both sides every time.
- A third logging account is deferred; may be added later as ADR-00X.

## Follow-ups
- ADR-002: Glue reads directly from Account A's bucket vs. copying to staging in B.
- ADR-003: Keep or drop VPC peering.
