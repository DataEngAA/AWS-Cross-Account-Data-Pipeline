# Alerts: the SNS topic the workflow publishes failures to, and an alarm on the DLQ.

resource "aws_sns_topic" "alerts" {
  #checkov:skip=CKV_AWS_26:With the AWS-managed SNS key, CloudWatch alarms cannot publish to the topic; alerts hold no sensitive data
  name = "platform-alerts"
}

# AWS emails a confirmation link after every fresh create; until it is clicked the
# subscription stays "PendingConfirmation" and no alerts are delivered.
resource "aws_sns_topic_subscription" "alert_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Any message in the DLQ means the Lambda could not handle it: tell someone.
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "platform-dlq-not-empty"
  alarm_description   = "Messages in platform-ingest-dlq: the ingest Lambda failed on them 3 times"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching" # an idle queue sends no data, which is fine
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}
