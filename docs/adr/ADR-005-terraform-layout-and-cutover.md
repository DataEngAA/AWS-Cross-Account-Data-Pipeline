# ADR-005: Terraform layout, state and cut-over from the console build

- **Status:** Accepted
- **Date:** 2026-10-21
- **Deciders:** Ali

## Context
Chunks 0-6 were built by hand in the console and CLI, with every setting recorded in `RESOURCE_INVENTORY.md`. Chunk 7 must make the whole stack reproducible from code (AC-08: destroy, then apply, gives a working pipeline). The stack spans two accounts with cross-account references in both directions, and some resources (RDS, interface endpoints) should exist only during lab sessions.

## Options considered
1. **One Terraform root for both accounts** (two provider aliases, one state). One apply; any mistake can reach both accounts.
2. **One root per account plus a bootstrap root (chosen).** Separate state and blast radius per account, matching the producer/platform ownership of ADR-001.
3. **Import every console resource** instead of recreating. Keeps the data, but about 40 imports and noisy diffs.

## Decision
- Layout: `terraform/bootstrap` (state bucket), `terraform/account-b` (platform, applied first), `terraform/account-a` (producer, applied second). Destroy in reverse order.
- Cross-account values are passed as input variables (the other account's ID); names are deterministic, so no project reads another project's state.
- State: S3 bucket in Account B with versioning and S3-native lock files (Terraform 1.10+). The bootstrap root keeps local state.
- IAM policies are written as `aws_iam_policy_document` that reference resources directly; the hand-maintained JSON in `policies/` and `scripts/render.py` are retired once Terraform works.
- Terraform deploys code too: Lambda zip (hash-based redeploy), Glue scripts to `scripts/` in B's bucket, Step Functions definition from a template.
- `enable_rds` switch creates or removes RDS, the three interface endpoints and the load job's database wiring.
- The `products` table is declared in Terraform; the crawler is retired (partitions are still refreshed by the workflow's MSCK REPAIR step).
- Not managed: admin users, MFA, budgets, data, and unrelated tables in Account A.
- Cut-over: delete the console-built resources and recreate them with Terraform; import one resource (the DynamoDB table) as a practice exercise.
- The EC2 scraper is dropped from Chunk 7 (synthetic data now, real APIs later).

## Consequences
**Positive**
- The whole pipeline can be rebuilt from Git; RDS sessions become one variable change.
- No console drift: only what is in code exists (no extra managed policies, no storage autoscaling).
- Default tags on every resource; log retention, TLS-only bucket policies and lifecycle rules are added as part of the rewrite.

**Negative / risks**
- Two applies in a fixed order (B, then A); applying A first fails because A's bucket policy names B's role.
- The SNS email subscription must be confirmed by hand after every fresh create.
- Recreating deletes the synthetic data, which is regenerated with `generate.py` and `upload.py`.
