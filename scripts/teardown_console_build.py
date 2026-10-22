"""One-off cut-over helper (ADR-005): delete the resources built by hand in Chunks 1-6
so Terraform can recreate them with the same names.

Dry run by default: lists what exists and would be deleted, changes nothing.
    python scripts/teardown_console_build.py             # dry run
    python scripts/teardown_console_build.py --execute   # really delete

Kept on purpose: scrape_state (imported by Terraform), the Terraform state bucket,
admin users, budgets, the unrelated Users/UserPosts tables, Glue job log groups.
Account IDs are read from local/accounts.env.
"""

import argparse
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
REGION = "ap-south-1"


def load_ids():
    values = {}
    for line in (ROOT / "local" / "accounts.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values["ACCOUNT_A_ID"], values["ACCOUNT_B_ID"]


class Teardown:
    def __init__(self, execute):
        self.execute = execute
        self.found = 0

    def step(self, label, exists, delete):
        """exists() -> bool; delete() performs the deletion."""
        try:
            if not exists():
                print(f"  -        {label} (not found)")
                return
        except ClientError as e:
            print(f"  ?        {label} (check failed: {e.response['Error']['Code']})")
            return
        self.found += 1
        if not self.execute:
            print(f"  delete   {label}")
            return
        try:
            delete()
            print(f"  deleted  {label}")
        except ClientError as e:
            print(f"  FAILED   {label}: {e.response['Error']['Code']}: {e.response['Error']['Message']}")


def missing(fn, *codes):
    """Run fn(); True if it worked, False if it raised one of the 'not found' codes."""
    try:
        fn()
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in codes:
            return False
        raise


def empty_bucket(s3, bucket):
    paginator = s3.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket):
        objs = [{"Key": v["Key"], "VersionId": v["VersionId"]}
                for v in page.get("Versions", []) + page.get("DeleteMarkers", [])]
        for i in range(0, len(objs), 1000):
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objs[i:i + 1000], "Quiet": True})


def delete_role(iam, name):
    for p in iam.list_attached_role_policies(RoleName=name)["AttachedPolicies"]:
        iam.detach_role_policy(RoleName=name, PolicyArn=p["PolicyArn"])
    for p in iam.list_role_policies(RoleName=name)["PolicyNames"]:
        iam.delete_role_policy(RoleName=name, PolicyName=p)
    iam.delete_role(RoleName=name)


def delete_managed_policy(iam, arn):
    for v in iam.list_policy_versions(PolicyArn=arn)["Versions"]:
        if not v["IsDefaultVersion"]:
            iam.delete_policy_version(PolicyArn=arn, VersionId=v["VersionId"])
    iam.delete_policy(PolicyArn=arn)


def role_exists(iam, name):
    return missing(lambda: iam.get_role(RoleName=name), "NoSuchEntity")


def account_a(t, a_id):
    print(f"\nAccount A ({a_id}), profile default")
    session = boto3.Session(profile_name="default", region_name=REGION)
    s3, iam = session.client("s3"), session.client("iam")
    raw = f"producer-aws-{a_id}-{REGION}-an"

    t.step(f"S3 bucket {raw} (all versions, policy, event notification)",
           lambda: missing(lambda: s3.head_bucket(Bucket=raw), "404", "NoSuchBucket"),
           lambda: (empty_bucket(s3, raw), s3.delete_bucket(Bucket=raw)))
    t.step("IAM role producer-state-writer",
           lambda: role_exists(iam, "producer-state-writer"),
           lambda: delete_role(iam, "producer-state-writer"))
    print("  keep     DynamoDB table scrape_state (imported by Terraform)")


def account_b(t, b_id):
    print(f"\nAccount B ({b_id}), profile acct-b")
    session = boto3.Session(profile_name="acct-b", region_name=REGION)
    lam, logs, iam = session.client("lambda"), session.client("logs"), session.client("iam")
    sfn, sns, cw = session.client("stepfunctions"), session.client("sns"), session.client("cloudwatch")
    sqs, glue, athena = session.client("sqs"), session.client("glue"), session.client("athena")
    s3, ec2, rds = session.client("s3"), session.client("ec2"), session.client("rds")
    curated = f"platform-aws-{b_id}-{REGION}-an"

    # Lambda and its trigger first, so nothing keeps reading the queue.
    for m in lam.list_event_source_mappings(FunctionName="platform-ingest-trigger").get("EventSourceMappings", []) \
            if missing(lambda: lam.get_function(FunctionName="platform-ingest-trigger"), "ResourceNotFoundException") else []:
        t.step(f"Lambda trigger {m['UUID']}", lambda: True,
               lambda m=m: lam.delete_event_source_mapping(UUID=m["UUID"]))
    t.step("Lambda platform-ingest-trigger",
           lambda: missing(lambda: lam.get_function(FunctionName="platform-ingest-trigger"), "ResourceNotFoundException"),
           lambda: lam.delete_function(FunctionName="platform-ingest-trigger"))
    t.step("Log group /aws/lambda/platform-ingest-trigger",
           lambda: bool(logs.describe_log_groups(logGroupNamePrefix="/aws/lambda/platform-ingest-trigger")["logGroups"]),
           lambda: logs.delete_log_group(logGroupName="/aws/lambda/platform-ingest-trigger"))
    t.step("IAM role platform-ingest-trigger-role",
           lambda: role_exists(iam, "platform-ingest-trigger-role"),
           lambda: delete_role(iam, "platform-ingest-trigger-role"))
    lambda_policy = f"arn:aws:iam::{b_id}:policy/platform-ingest-trigger-rolePolicy"
    t.step("IAM policy platform-ingest-trigger-rolePolicy",
           lambda: missing(lambda: iam.get_policy(PolicyArn=lambda_policy), "NoSuchEntity"),
           lambda: delete_managed_policy(iam, lambda_policy))

    # Workflow, alerts.
    sm = f"arn:aws:states:{REGION}:{b_id}:stateMachine:platform-ingest-workflow"
    t.step("State machine platform-ingest-workflow",
           lambda: missing(lambda: sfn.describe_state_machine(stateMachineArn=sm), "StateMachineDoesNotExist"),
           lambda: sfn.delete_state_machine(stateMachineArn=sm))
    t.step("IAM role platform-workflow-role",
           lambda: role_exists(iam, "platform-workflow-role"),
           lambda: delete_role(iam, "platform-workflow-role"))
    topic = f"arn:aws:sns:{REGION}:{b_id}:platform-alerts"
    t.step("SNS topic platform-alerts (and its subscription)",
           lambda: missing(lambda: sns.get_topic_attributes(TopicArn=topic), "NotFound"),
           lambda: sns.delete_topic(TopicArn=topic))
    t.step("CloudWatch alarm platform-dlq-not-empty",
           lambda: bool(cw.describe_alarms(AlarmNames=["platform-dlq-not-empty"])["MetricAlarms"]),
           lambda: cw.delete_alarms(AlarmNames=["platform-dlq-not-empty"]))

    # Queues.
    for q in ("platform-ingest-queue", "platform-ingest-dlq"):
        t.step(f"SQS queue {q}",
               lambda q=q: missing(lambda: sqs.get_queue_url(QueueName=q), "AWS.SimpleQueueService.NonExistentQueue", "QueueDoesNotExist"),
               lambda q=q: sqs.delete_queue(QueueUrl=sqs.get_queue_url(QueueName=q)["QueueUrl"]))

    # Glue, catalog, crawler, Athena.
    for job in ("platform-etl-products", "platform-load-rds"):
        t.step(f"Glue job {job}",
               lambda job=job: missing(lambda: glue.get_job(JobName=job), "EntityNotFoundException"),
               lambda job=job: glue.delete_job(JobName=job))
    t.step("Glue crawler platform-curated-products-crawler",
           lambda: missing(lambda: glue.get_crawler(Name="platform-curated-products-crawler"), "EntityNotFoundException"),
           lambda: glue.delete_crawler(Name="platform-curated-products-crawler"))
    crawler_policies = [p["Arn"] for p in iam.list_policies(Scope="Local", PathPrefix="/service-role/")["Policies"]
                        if p["PolicyName"].startswith("AWSGlueServiceRole-platform-crawler")]
    t.step("IAM role AWSGlueServiceRole-platform-crawler",
           lambda: role_exists(iam, "AWSGlueServiceRole-platform-crawler"),
           lambda: delete_role(iam, "AWSGlueServiceRole-platform-crawler"))
    for arn in crawler_policies:
        t.step(f"IAM policy {arn.rsplit('/', 1)[-1]}", lambda: True,
               lambda arn=arn: delete_managed_policy(iam, arn))
    t.step("Glue connection platform-vpc-network",
           lambda: missing(lambda: glue.get_connection(Name="platform-vpc-network"), "EntityNotFoundException"),
           lambda: glue.delete_connection(ConnectionName="platform-vpc-network"))
    t.step("Glue database platform_curated (and table products)",
           lambda: missing(lambda: glue.get_database(Name="platform_curated"), "EntityNotFoundException"),
           lambda: glue.delete_database(Name="platform_curated"))
    t.step("IAM role platform-glue-etl-role",
           lambda: role_exists(iam, "platform-glue-etl-role"),
           lambda: delete_role(iam, "platform-glue-etl-role"))
    t.step("Athena workgroup platform-analytics",
           lambda: missing(lambda: athena.get_work_group(WorkGroup="platform-analytics"), "InvalidRequestException"),
           lambda: athena.delete_work_group(WorkGroup="platform-analytics", RecursiveDeleteOption=True))
    t.step(f"S3 bucket {curated} (all objects)",
           lambda: missing(lambda: s3.head_bucket(Bucket=curated), "404", "NoSuchBucket"),
           lambda: (empty_bucket(s3, curated), s3.delete_bucket(Bucket=curated)))

    # Network: endpoints, subnet group, security groups, subnets, route tables, VPC.
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": ["platform-vpc"]}])["Vpcs"]
    if not vpcs:
        print("  -        VPC platform-vpc (not found)")
        return
    vpc = vpcs[0]["VpcId"]
    f = [{"Name": "vpc-id", "Values": [vpc]}]
    for ep in ec2.describe_vpc_endpoints(Filters=f)["VpcEndpoints"]:
        if ep["State"] not in ("deleted", "deleting"):
            t.step(f"VPC endpoint {ep['VpcEndpointId']} ({ep['ServiceName'].rsplit('.', 1)[-1]})", lambda: True,
                   lambda ep=ep: ec2.delete_vpc_endpoints(VpcEndpointIds=[ep["VpcEndpointId"]]))
    for g in rds.describe_db_subnet_groups()["DBSubnetGroups"]:
        if g["VpcId"] == vpc:
            t.step(f"RDS subnet group {g['DBSubnetGroupName']}", lambda: True,
                   lambda g=g: rds.delete_db_subnet_group(DBSubnetGroupName=g["DBSubnetGroupName"]))
    groups = [g for g in ec2.describe_security_groups(Filters=f)["SecurityGroups"] if g["GroupName"] != "default"]
    # Remove rules first: groups that reference each other cannot be deleted otherwise.
    for g in groups:
        t.step(f"Rules of security group {g['GroupName']}", lambda g=g: bool(g["IpPermissions"]),
               lambda g=g: ec2.revoke_security_group_ingress(GroupId=g["GroupId"], IpPermissions=g["IpPermissions"]))
    if t.execute:
        time.sleep(5)  # endpoint network cards take a moment to disappear
    for g in groups:
        t.step(f"Security group {g['GroupName']}", lambda: True,
               lambda g=g: ec2.delete_security_group(GroupId=g["GroupId"]))
    for s in ec2.describe_subnets(Filters=f)["Subnets"]:
        name = next((x["Value"] for x in s.get("Tags", []) if x["Key"] == "Name"), s["SubnetId"])
        t.step(f"Subnet {name}", lambda: True, lambda s=s: ec2.delete_subnet(SubnetId=s["SubnetId"]))
    for rt in ec2.describe_route_tables(Filters=f)["RouteTables"]:
        if not any(a.get("Main") for a in rt.get("Associations", [])):
            t.step(f"Route table {rt['RouteTableId']}", lambda: True,
                   lambda rt=rt: ec2.delete_route_table(RouteTableId=rt["RouteTableId"]))
    t.step(f"VPC platform-vpc {vpc}", lambda: True, lambda: ec2.delete_vpc(VpcId=vpc))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="really delete (default: dry run)")
    args = parser.parse_args()
    a_id, b_id = load_ids()
    t = Teardown(args.execute)
    print("EXECUTE: deleting" if args.execute else "DRY RUN: nothing will be changed")
    account_a(t, a_id)  # A first: its policy and notification point at B
    account_b(t, b_id)
    print(f"\n{t.found} item(s) {'processed' if args.execute else 'would be deleted'}")
    if args.execute:
        print("SQS needs about 60 s before a deleted queue name can be reused; wait a minute before applying.")


if __name__ == "__main__":
    sys.exit(main())
