# Ingest queue (B's mailbox for "new file" events from A) and its dead-letter queue.

resource "aws_sqs_queue" "dlq" {
  name                      = "platform-ingest-dlq"
  message_retention_seconds = 1209600 # 14 days, the maximum: time to inspect failures
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "ingest" {
  name                       = "platform-ingest-queue"
  visibility_timeout_seconds = 180    # 6 x the Lambda's 30 s timeout (decision 15)
  message_retention_seconds  = 345600 # 4 days
  receive_wait_time_seconds  = 20     # long polling
  sqs_managed_sse_enabled    = true   # S3 notifications work with SSE-SQS (not with the AWS-managed KMS key)

  # After 3 failed receives a message moves to the DLQ.
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# Only the S3 service, acting for Account A's raw bucket, may send messages.
# (Account B's own identities already have access through IAM.)
data "aws_iam_policy_document" "ingest_queue" {
  statement {
    sid       = "AllowRawBucketInAccountA"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingest.arn]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    # Both conditions guard against the confused deputy problem: another bucket
    # using the S3 service to write into this queue.
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [local.raw_bucket_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_a_id]
    }
  }
}

resource "aws_sqs_queue_policy" "ingest" {
  queue_url = aws_sqs_queue.ingest.id
  policy    = data.aws_iam_policy_document.ingest_queue.json
}
