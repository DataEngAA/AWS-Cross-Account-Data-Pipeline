# User stories

Personas: **Data producer** (the scraper or uploader in Account A), **Platform engineer** (Ali, operating Account B), **Analyst** (queries curated data), **Interviewer** (reads the repo).

| ID | Story | Requirements |
|---|---|---|
| US-01 | As a data producer, I upload a raw JSON file so that it is processed without me contacting the platform team | FR-02, FR-03 |
| US-02 | As a platform engineer, I want new files to arrive as queue messages so that spikes and failures do not lose data | FR-03, FR-04, FR-11 |
| US-03 | As a platform engineer, I want Account B to read Account A's files using roles and policies so that no access keys are shared | FR-05 |
| US-04 | As a platform engineer, I want bad records separated from good ones so that analysts only see trusted data | FR-06 |
| US-05 | As an analyst, I want cleaned data as partitioned Parquet queryable in Athena so that queries are fast and cheap | FR-07, FR-09 |
| US-06 | As an analyst, I want the same data in PostgreSQL so that I can run relational queries | FR-08 |
| US-07 | As a platform engineer, I want a workflow with retries and failure paths so that transient errors fix themselves and real errors alert me | FR-10, FR-11 |
| US-08 | As a data producer, I want my scrape state tracked so that I do not fetch the same page twice | FR-02, FR-12 |
| US-09 | As a platform engineer, I want to deploy and destroy the whole stack with one command so that costs stay under control | NFR-01, NFR-03 |
| US-10 | As an interviewer, I want a README, diagrams and decision records so that I can judge the design quickly | NFR-06 |
