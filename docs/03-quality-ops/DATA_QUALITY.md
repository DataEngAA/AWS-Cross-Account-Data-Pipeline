# Data quality

## Approach
Glue Data Quality evaluates rules on every file. Records that fail are written to quarantine; records that pass continue. Counts are logged and stored.

## Rules (starter set)
| ID | Column | Rule | Action on failure |
|---|---|---|---|
| DQ-01 | `product_id` | not null, unique within the file | quarantine record |
| DQ-02 | `name` | not null, not empty | quarantine record |
| DQ-03 | `price` | not null, greater than 0 | quarantine record |
| DQ-04 | `currency` | one of the allowed ISO codes | quarantine record |
| DQ-05 | `scraped_at` | valid ISO 8601 timestamp, not in the future | quarantine record |
| DQ-06 | `category` | not null | quarantine record |
| DQ-07 | file | at least 1 record | fail the file |
| DQ-08 | file | share of failing records below a threshold (for example 30%) | fail the file and alert |

Rule definitions are DQDL, kept in the `RULESET` constant of `src/glue/etl_products.py` so they are versioned with the job. Rows are checked with Glue Data Quality `EvaluateDataQuality().process_rows`; rows whose `DataQualityEvaluationResult` is not `Passed` go to quarantine with `DataQualityRulesFail` as `failed_rules`. DQ-01 uniqueness is applied after the DQDL checks (first row per `product_id` + `scraped_at` is kept, later ones are quarantined as duplicates). DQ-08 is checked before the curated write, so a suspect file adds nothing to curated.

## Metrics to record per run
- records in, records valid, records quarantined
- failure count per rule
- run duration

## Quarantine handling
Quarantined records stay in `quarantine/products/processed_date=YYYY-MM-DD/run_id=<glue run id>/` as JSON lines, with the typed columns, the original `scraped_at_raw` text, the `input_file` they came from and the `failed_rules` list. The per-rule scorecard is in `dq-results/products/run_id=<glue run id>/` and in the Glue console's Data quality tab. A run that quarantines a large share raises an alert (DQ-08). Replay is manual: fix the data, re-upload.

## Later extensions
- Drift check on schema changes.
- Freshness check: alert when no file arrives within the expected window.
