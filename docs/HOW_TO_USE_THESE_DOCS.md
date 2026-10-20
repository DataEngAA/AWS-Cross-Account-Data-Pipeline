# How to use these docs

## What this project is about
A personal, hands-on build of a cross-account, event-driven data pipeline on AWS, designed to teach multi-account design and VPC networking while producing a portfolio piece for platform and data engineering roles.

Two AWS accounts split the work by responsibility: a **producer account** (A, free tier) collects raw data and lands it in S3, and a **platform account** (B, paid) picks it up through SQS, validates and transforms it with Glue under Step Functions, then serves it through Athena and a private RDS database. The accounts talk to each other through bucket and queue policies, `sts:AssumeRole`, and optionally VPC peering, so every cross-account mechanism has a real reason to exist.

It uses only synthetic or public practice data, never employer or client data, and the finished system should deploy and destroy with Terraform.

## Which document to open, and when
Think of the docs as three layers: **why → how → do**. When something changes, update the highest layer it touches, then everything below it.

| You want to... | Open first | Then update |
|---|---|---|
| Remember the goal or scope | [PROJECT_BRIEF](01-product/PROJECT_BRIEF.md) | [REQUIREMENTS](01-product/REQUIREMENTS.md) if scope changes |
| Know what the system must do | [REQUIREMENTS](01-product/REQUIREMENTS.md) | [ACCEPTANCE_CRITERIA](01-product/ACCEPTANCE_CRITERIA.md) and [TASKS](04-delivery/TASKS.md) |
| See what is deployed right now, with exact settings | [RESOURCE_INVENTORY](02-architecture/RESOURCE_INVENTORY.md) | update it the same day you change anything in AWS |
| Understand how it fits together | [ARCHITECTURE](02-architecture/ARCHITECTURE.md), then [DATA_FLOW](02-architecture/DATA_FLOW.md) | [DATA_MODEL](02-architecture/DATA_MODEL.md) if schemas change |
| Know what to build next | [IMPLEMENTATION_PLAN](04-delivery/IMPLEMENTATION_PLAN.md), then [TASKS](04-delivery/TASKS.md) | tick boxes as you finish |
| Check if a chunk is really finished | [DEFINITION_OF_DONE](04-delivery/DEFINITION_OF_DONE.md) | [TASKS](04-delivery/TASKS.md) |
| Decide whether something is too risky or costly | [RISKS](04-delivery/RISKS.md) | add new risks as they appear |
| Check security or permissions | [SECURITY](03-quality-ops/SECURITY.md) | the cross-account access table in [ARCHITECTURE](02-architecture/ARCHITECTURE.md) |
| Know how to test or debug | [TEST_STRATEGY](03-quality-ops/TEST_STRATEGY.md), [OBSERVABILITY](03-quality-ops/OBSERVABILITY.md) | add runbook notes |
| Prepare for interviews | [INTERVIEW_NOTES](05-learning/INTERVIEW_NOTES.md) | fill in "my notes" and the chunk log after each chunk |

## How to follow the docs while building
1. Start each session at [TASKS](04-delivery/TASKS.md). Pick the next unchecked item in the current chunk.
2. If you need context, read the matching section of [ARCHITECTURE](02-architecture/ARCHITECTURE.md) or [DATA_FLOW](02-architecture/DATA_FLOW.md).
3. Before calling a chunk done, walk through [DEFINITION_OF_DONE](04-delivery/DEFINITION_OF_DONE.md).
4. After each chunk, add three lines to the chunk log in [INTERVIEW_NOTES](05-learning/INTERVIEW_NOTES.md): what you built, what broke, what you learned.

## How to change a decision
Not every change deserves the same effort:

- **Small change** (a name, a threshold, a rule): edit the relevant doc directly and add one row to [DECISIONS_AND_TRADEOFFS](05-learning/DECISIONS_AND_TRADEOFFS.md).
- **Big change** (account split, replacing Glue, dropping peering, a new service): write a new ADR in [`adr/`](adr/), copying the shape of [ADR-001](adr/ADR-001-two-account-producer-platform-split.md): context, options, decision, consequences. The open decisions already have numbers waiting:
  - ADR-002: decided, Glue reads A's bucket directly ([ADR-002](adr/ADR-002-glue-reads-producer-bucket-directly.md))
  - ADR-003: keep or drop VPC peering
  - ADR-004: add a third logging account (only if yes)
- **Never delete an old ADR.** If a decision is reversed, mark the old one `Superseded by ADR-00X` and write the new one. Interviewers like seeing that history.

After deciding, walk down the chain so the docs don't contradict each other:

1. [REQUIREMENTS](01-product/REQUIREMENTS.md): does a requirement change?
2. [ARCHITECTURE](02-architecture/ARCHITECTURE.md) and [DATA_FLOW](02-architecture/DATA_FLOW.md): does the design change?
3. [ACCEPTANCE_CRITERIA](01-product/ACCEPTANCE_CRITERIA.md) and [TEST_STRATEGY](03-quality-ops/TEST_STRATEGY.md): does a test change?
4. [TASKS](04-delivery/TASKS.md) and [IMPLEMENTATION_PLAN](04-delivery/IMPLEMENTATION_PLAN.md): does the work change?
5. [RISKS](04-delivery/RISKS.md) and [SECURITY](03-quality-ops/SECURITY.md): does the risk or trust model change?

When the architecture and the real build disagree, fix the doc the same day. Stale docs are worse than no docs, because you'll end up trusting them in an interview.
