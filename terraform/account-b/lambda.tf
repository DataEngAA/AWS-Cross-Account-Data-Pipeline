# Ingest trigger: reads S3 events from the queue and starts one workflow execution per file.

locals {
  lambda_name        = "platform-ingest-trigger"
  state_machine_name = "platform-ingest-workflow"
  # Built from the name (like Account A's ARNs), so this file does not depend on stepfunctions.tf.
  state_machine_arn = "arn:aws:states:${local.region}:${local.account_b_id}:stateMachine:${local.state_machine_name}"
}

# Zip the handler. When handler.py changes, the zip's hash changes and Terraform redeploys;
# when it does not, nothing happens.
data "archive_file" "ingest_trigger" {
  type        = "zip"
  source_file = "${path.module}/../../src/lambda/ingest_trigger/handler.py"
  output_path = "${path.module}/build/ingest_trigger.zip"
}

# Created by Terraform (not by Lambda on first run) so the retention can be set.
resource "aws_cloudwatch_log_group" "ingest_trigger" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = 14
}

# --- Role ------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingest_trigger" {
  name               = "platform-ingest-trigger-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "ingest_trigger" {
  statement {
    sid       = "ReadIngestQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.ingest.arn]
  }
  statement {
    sid = "WriteOwnLogs"
    # No logs:CreateLogGroup: Terraform creates the group above.
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingest_trigger.arn}:*"]
  }
  statement {
    sid       = "StartIngestWorkflow"
    actions   = ["states:StartExecution"]
    resources = [local.state_machine_arn]
  }
}

# Inline policy: belongs to this role only and is deleted with it.
# No AWSLambdaBasicExecutionRole: the console added it, but it allows logs anywhere.
resource "aws_iam_role_policy" "ingest_trigger" {
  name   = "ingest-trigger-permissions"
  role   = aws_iam_role.ingest_trigger.id
  policy = data.aws_iam_policy_document.ingest_trigger.json
}

# --- Function ----------------------------------------------------------------------
resource "aws_lambda_function" "ingest_trigger" {
  function_name    = local.lambda_name
  role             = aws_iam_role.ingest_trigger.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler" # file handler.py, function lambda_handler
  filename         = data.archive_file.ingest_trigger.output_path
  source_code_hash = data.archive_file.ingest_trigger.output_base64sha256
  timeout          = 30 # the queue's visibility timeout (180 s) is 6 x this
  memory_size      = 128

  environment {
    variables = {
      STATE_MACHINE_ARN = local.state_machine_arn
    }
  }

  # The log group and permissions must exist before the first invocation.
  depends_on = [aws_cloudwatch_log_group.ingest_trigger, aws_iam_role_policy.ingest_trigger]
}

# --- Trigger: queue -> function -------------------------------------------------------
resource "aws_lambda_event_source_mapping" "ingest_queue" {
  event_source_arn                   = aws_sqs_queue.ingest.arn
  function_name                      = aws_lambda_function.ingest_trigger.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"] # only failed messages are retried

  scaling_config {
    maximum_concurrency = 2 # at most 2 copies of the function at once (decision 30)
  }
}
