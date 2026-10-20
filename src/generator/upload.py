"""Upload generated files to the raw bucket in Account A and record each one in DynamoDB.

For every file under <data>/raw/ the S3 key is the file's path relative to
<data>, e.g. raw/source=synthetic/date=2026-10-14/20261014T060000-001.json.

Per file:
  1. Skip it if the table already has a row for that key (unless --force),
     so running the script twice does not upload or trigger anything twice.
  2. Put the object in S3.
  3. Write a RECEIVED row to DynamoDB with the S3 version id.

S3 is written before DynamoDB. If the DynamoDB write fails the script stops and
names the file that is in S3 without a row.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

def default_bucket():
    """Raw bucket name: $RAW_BUCKET, else built from ACCOUNT_A_ID in local/accounts.env."""
    if os.environ.get("RAW_BUCKET"):
        return os.environ["RAW_BUCKET"]
    env_file = Path(__file__).resolve().parents[2] / "local" / "accounts.env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("ACCOUNT_A_ID="):
                return f"producer-aws-{line.split('=', 1)[1].strip()}-ap-south-1-an"
    return None


DEFAULT_TABLE = "scrape_state"
DEFAULT_REGION = "ap-south-1"


def load_manifest(data_dir):
    path = data_dir / "manifest.json"
    if not path.exists():
        return {}
    detail = json.loads(path.read_text(encoding="utf-8"))["files_detail"]
    return {entry["key"]: entry for entry in detail}


def preflight(s3, table, bucket):
    """Fail early with a clear message if the bucket or table cannot be reached."""
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        sys.exit(f"cannot reach bucket {bucket!r} ({code}): check the name, region and profile")
    try:
        table.load()
    except ClientError as e:
        code = e.response["Error"]["Code"]
        sys.exit(f"cannot reach table {table.name!r} ({code}): check the name, region and profile")
    versioning = s3.get_bucket_versioning(Bucket=bucket).get("Status")
    if versioning != "Enabled":
        print(f"warning: versioning is not enabled on {bucket}; rows will have no s3_version_id")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", help="AWS CLI profile (default: your default profile)")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--bucket", default=default_bucket(),
                        help="raw bucket (default: $RAW_BUCKET or built from local/accounts.env)")
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--data", default="data", help="folder made by generate.py (default data/)")
    parser.add_argument("--limit", type=int, help="upload at most this many files")
    parser.add_argument("--force", action="store_true",
                        help="upload even if the table already has a row for the file")
    parser.add_argument("--dry-run", action="store_true",
                        help="check access and show what would be uploaded, write nothing")
    args = parser.parse_args()

    if not args.bucket:
        sys.exit("no bucket: pass --bucket, set RAW_BUCKET, or create local/accounts.env")
    data_dir = Path(args.data)
    files = sorted((data_dir / "raw").rglob("*.json"))
    if not files:
        sys.exit(f"no files under {data_dir / 'raw'}; run generate.py first")
    if args.limit:
        files = files[:args.limit]
    manifest = load_manifest(data_dir)

    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        s3 = session.client("s3")
        table = session.resource("dynamodb").Table(args.table)
        account = session.client("sts").get_caller_identity()["Account"]
    except ProfileNotFound:
        sys.exit(f"profile {args.profile!r} not found; see `aws configure list-profiles`")
    except NoCredentialsError:
        sys.exit("no AWS credentials found; configure a profile first")

    print(f"account {account}, bucket {args.bucket}, table {args.table}, {len(files)} file(s)"
          + (" [dry run]" if args.dry_run else ""))
    preflight(s3, table, args.bucket)

    uploaded = skipped = 0
    for path in files:
        key = path.relative_to(data_dir).as_posix()
        entry = manifest.get(key, {})

        if not args.force and "Item" in table.get_item(Key={"file_key": key}):
            print(f"skip    {key} (already in {args.table})")
            skipped += 1
            continue
        if args.dry_run:
            print(f"would   {key}")
            continue

        with path.open("rb") as body:
            response = s3.put_object(Bucket=args.bucket, Key=key, Body=body,
                                     ContentType="application/json")

        item = {
            "file_key": key,
            "status": "RECEIVED",
            "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_id": entry.get("run_id", path.stem),
            "source": key.split("/")[1].removeprefix("source="),
        }
        if response.get("VersionId"):
            item["s3_version_id"] = response["VersionId"]
        if entry.get("records") is not None:
            item["record_count"] = entry["records"]

        try:
            table.put_item(Item=item)
        except ClientError as e:
            sys.exit(f"uploaded {key} to S3 but writing its row failed "
                     f"({e.response['Error']['Code']}); fix the cause, then rerun with --force")

        print(f"upload  {key}")
        uploaded += 1

    if not args.dry_run:
        print(f"done: {uploaded} uploaded, {skipped} skipped")


if __name__ == "__main__":
    main()
