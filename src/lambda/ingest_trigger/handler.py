"""Ingest trigger (Account B): start one Step Functions execution per new raw file.

Triggered by SQS (platform-ingest-queue). Each SQS message body is an S3 event
notification sent by the raw bucket in Account A.

The execution name is built from the file name plus a hash of bucket, key and
version id. Step Functions refuses a second execution with the same name, so a
duplicate S3 event or SQS redelivery cannot process the same file version twice;
that case is logged and treated as success.

Uses partial batch responses: a message that fails is returned in
batchItemFailures, so only that message is retried (and moved to the DLQ after
3 receives), not the whole batch. Requires "Report batch item failures" to be
turned on in the SQS trigger.

Environment variables:
  STATE_MACHINE_ARN  ARN of platform-ingest-workflow
"""

import hashlib
import json
import logging
import os
import re
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sfn = boto3.client("stepfunctions")
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]


def parse_s3_records(body):
    """Return (bucket, key, version_id, size) for each S3 record in one SQS message body."""
    event = json.loads(body)
    # S3 sends a one-off test message when a notification is first configured.
    if event.get("Event") == "s3:TestEvent":
        logger.info("s3 test event from bucket %s, ignoring", event.get("Bucket"))
        return []
    files = []
    for record in event.get("Records", []):
        s3 = record["s3"]
        files.append((
            s3["bucket"]["name"],
            unquote_plus(s3["object"]["key"]),  # keys arrive URL-encoded ("=" becomes "%3D")
            s3["object"].get("versionId"),
            s3["object"].get("size"),
        ))
    return files


def execution_name(bucket, key, version_id):
    """Same file version -> same name (max 80 chars, letters, digits, - and _ only)."""
    digest = hashlib.sha256(f"{bucket}/{key}#{version_id}".encode()).hexdigest()[:16]
    stem = re.sub(r"[^A-Za-z0-9_-]", "-", key.rsplit("/", 1)[-1].rsplit(".", 1)[0])[:60]
    return f"{stem}-{digest}"


def start_workflow(bucket, key, version_id, size, message_id):
    name = execution_name(bucket, key, version_id)
    payload = {"bucket": bucket, "key": key, "version_id": version_id, "size": size}
    try:
        response = sfn.start_execution(stateMachineArn=STATE_MACHINE_ARN, name=name,
                                       input=json.dumps(payload))
        logger.info(json.dumps({"msg": "workflow started", "key": key, "version_id": version_id,
                                "execution": name, "execution_arn": response["executionArn"],
                                "sqs_message_id": message_id}))
    except sfn.exceptions.ExecutionAlreadyExists:
        # This file version was already started; a duplicate event is not an error.
        logger.info(json.dumps({"msg": "duplicate event, already started", "key": key,
                                "execution": name, "sqs_message_id": message_id}))


def lambda_handler(event, context):
    failures = []
    for message in event.get("Records", []):
        message_id = message["messageId"]
        try:
            for bucket, key, version_id, size in parse_s3_records(message["body"]):
                start_workflow(bucket, key, version_id, size, message_id)
        except Exception:
            logger.exception("could not process message %s", message_id)
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
