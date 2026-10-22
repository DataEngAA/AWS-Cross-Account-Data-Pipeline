"""End-to-end test: one upload in Account A must come out PROCESSED, with the right row count.

Steps:
  1. Generate a test file dated yesterday and predict how many records are valid.
  2. Upload it to Account A (S3 + RECEIVED row), re-uploading if it already exists.
  3. Wait until scrape_state shows PROCESSED or FAILED for this upload.
  4. Check the Step Functions execution in Account B succeeded.
  5. Count the rows for that date in Athena and compare with the prediction.

    python tests/e2e/run_e2e.py              # 300 records
    python tests/e2e/run_e2e.py --records 1000

Exit code 0 = all checks passed. Uses CLI profiles `default` (Account A) and `acct-b` (Account B).
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[2]
REGION = "ap-south-1"
CURRENCIES = {"GBP", "USD", "EUR"}


def expected_valid(path):
    """Apply the same rules as the Glue Data Quality ruleset and DQ-01 de-duplication."""
    now = datetime.now(timezone.utc)
    seen, valid = set(), 0
    for r in json.loads(path.read_text(encoding="utf-8"))["records"]:
        try:
            ts = datetime.strptime(r.get("scraped_at") or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            ts = None
        ok = (r.get("product_id") and (r.get("name") or "").strip() and r.get("category")
              and r.get("price") is not None and r["price"] > 0
              and r.get("currency") in CURRENCIES and ts and ts <= now)
        if ok and (r["product_id"], ts) not in seen:
            seen.add((r["product_id"], ts))
            valid += 1
    return valid


def athena_count(athena, date):
    query = f"SELECT COUNT(*) FROM products WHERE \"date\" = '{date}'"
    qid = athena.start_query_execution(QueryString=query, WorkGroup="platform-analytics",
                                       QueryExecutionContext={"Database": "platform_curated"})["QueryExecutionId"]
    while True:
        state = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
    if state != "SUCCEEDED":
        return None
    rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    return int(rows[1]["Data"][0]["VarCharValue"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--records", type=int, default=300)
    parser.add_argument("--timeout", type=int, default=600, help="seconds to wait for the workflow")
    args = parser.parse_args()

    date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    out = ROOT / "data" / "e2e-run"
    checks = []

    # 1. Generate and predict.
    subprocess.run([sys.executable, str(ROOT / "src/generator/generate.py"), "--files", "1",
                    "--records", str(args.records), "--start", date, "--broken-files", "0",
                    "--seed", "2026", "--out", str(out)], check=True, stdout=subprocess.DEVNULL)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    key = manifest["files_detail"][0]["key"]
    predicted = expected_valid(out / key)
    print(f"1. generated {key}: {args.records} records, {predicted} predicted valid")

    # 2. Upload (and note the time, to recognise this run's result).
    started = datetime.now(timezone.utc)
    subprocess.run([sys.executable, str(ROOT / "src/generator/upload.py"), "--data", str(out), "--force"],
                   check=True, stdout=subprocess.DEVNULL)
    print(f"2. uploaded at {started:%H:%M:%S} UTC")

    # 3. Wait for the workflow to write back to Account A.
    table = boto3.Session(profile_name="default", region_name=REGION).resource("dynamodb").Table("scrape_state")
    deadline, item = time.time() + args.timeout, {}
    while time.time() < deadline:
        item = table.get_item(Key={"file_key": key}).get("Item", {})
        done_at = item.get("processed_at", "")
        if item.get("status") in ("PROCESSED", "FAILED") and done_at >= started.strftime("%Y-%m-%dT%H:%M:%S"):
            break
        time.sleep(10)
        print(f"   waiting... status={item.get('status')}")
    status = item.get("status")
    checks.append(("A: scrape_state is PROCESSED", status == "PROCESSED", f"status={status}"))
    print(f"3. scrape_state: {status} (run_id {item.get('run_id')})")

    # 4. The execution in Account B.
    session_b = boto3.Session(profile_name="acct-b", region_name=REGION)
    sfn = session_b.client("stepfunctions")
    account_b = session_b.client("sts").get_caller_identity()["Account"]
    exec_status = None
    if item.get("run_id"):
        arn = f"arn:aws:states:{REGION}:{account_b}:execution:platform-ingest-workflow:{item['run_id']}"
        exec_status = sfn.describe_execution(executionArn=arn)["status"]
    checks.append(("B: workflow execution SUCCEEDED", exec_status == "SUCCEEDED", f"status={exec_status}"))
    print(f"4. execution: {exec_status}")

    # 5. Athena count for that date (this file is the only one dated yesterday).
    count = athena_count(session_b.client("athena"), date)
    checks.append((f"B: Athena rows for {date} = predicted", count == predicted,
                   f"athena={count}, predicted={predicted}"))
    print(f"5. athena: {count} rows for {date}")

    print()
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  ({detail})")
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
