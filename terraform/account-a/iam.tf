# producer-state-writer: the role Account B's workflow assumes to update scrape_state.

data "aws_iam_policy_document" "state_writer_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    # "Account B" as principal, narrowed to exactly one role by the condition. Naming the
    # role directly as principal would also work, but only if it already exists.
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.account_b_id}:root"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:PrincipalArn"
      values   = [local.platform_workflow_role]
    }
  }
}

resource "aws_iam_role" "state_writer" {
  name                 = "producer-state-writer"
  assume_role_policy   = data.aws_iam_policy_document.state_writer_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "state_writer" {
  statement {
    sid       = "ReadAndUpdateFileStatus"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.scrape_state.arn]
  }
}

resource "aws_iam_role_policy" "state_writer" {
  name   = "scrape-state-update"
  role   = aws_iam_role.state_writer.id
  policy = data.aws_iam_policy_document.state_writer.json
}
