# Manual test: Account B updates Account A's DynamoDB through AssumeRole

Inputs for the `aws dynamodb update-item` test in Chunk 3 (step 3.4). Kept as files so the
same commands work in CMD and PowerShell without JSON quoting problems.

- `key.json`: which row to update (the 2026-10-20 file)
- `names.json`: `#s` stands for `status`, which is a DynamoDB reserved word
- `values.json`: the new status, valid count and processed time
