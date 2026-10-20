# Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | Unexpected AWS bill (RDS left running, NAT Gateway, Glue jobs, public IPv4) | Medium | High | Budget alerts in both accounts, tear down after each session, prefer VPC endpoints to NAT, check pricing before each lab |
| R-02 | Free-tier account rules differ from expectations (AWS changed its free plan structure; consolidated billing can affect benefits) | Medium | Medium | Read the Billing console for the account's actual plan; keep paid services in Account B; do not rely on old 12-month free-tier assumptions |
| R-03 | Cross-account permission errors that are slow to debug | High | Medium | Check both sides every time, use CloudTrail to see denied calls, build and test the connection in small steps |
| R-04 | Glue jobs are slow to start and costly if misconfigured | Medium | Medium | Smallest worker configuration, few workers, tiny test data, set job timeouts |
| R-05 | Scope creep (too many services before the core works) | High | Medium | Follow chunk order, finish and test each chunk, defer optional items (peering, third account) |
| R-06 | Accidentally exposing data or credentials publicly | Low | High | Block Public Access, secret scan, no real data, mask account IDs |
| R-07 | Using employer or client data or code in a public portfolio | Low | High | Only synthetic or public practice data, no employer code, keep the repo clearly personal |
| R-08 | Scraping a site that disallows it | Low | Medium | Use sites made for scraping practice or open APIs, respect robots.txt and terms |
| R-09 | Project stalls because it is large | Medium | Medium | Small chunks with visible results, weekly pacing, log progress in `TASKS.md` |
| R-10 | Terraform state loss or leak | Low | Medium | Encrypted remote state or local state outside Git, never commit state files |
| R-11 | Temporary test access left in place (`user/<ADMIN_USER_B>` in the `producer-state-writer` trust policy, `samples/` read) | Medium | Medium | Listed under "Temporary items" in `RESOURCE_INVENTORY.md`; removal is a Chunk 6 task |
| R-12 | One Glue run per file makes cost grow with file count, not data size (about $0.01-0.02 per small Flex run) | Medium | Medium | Batch backfills into one run, Flex and 2 workers, consider `MaximumConcurrency` on the SQS trigger |
| R-13 | The console adds broader permissions than intended (for example `AWSLambdaBasicExecutionRole`) | Medium | Low | Review every role after console work; Terraform defines exact policies |

## Budget
Set an initial monthly budget (suggested starting point: a few US dollars) in both accounts, review after chunk 2 and chunk 5, and adjust. Record the chosen number here: `____`.

## Review
Revisit this file at the end of every chunk and add new risks as they appear.
