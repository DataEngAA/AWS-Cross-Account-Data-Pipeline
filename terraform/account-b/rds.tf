# RDS PostgreSQL and everything that depends on it. All of it exists only while
# enable_rds = true: `count = 0` means "create none", `count = 1` means "create one".

resource "aws_db_subnet_group" "platform" {
  count      = var.enable_rds ? 1 : 0
  name       = "platform-db-subnets"
  subnet_ids = [for s in aws_subnet.private : s.id]
}

resource "aws_db_instance" "platform" {
  count = var.enable_rds ? 1 : 0

  identifier        = "platform-db"
  engine            = "postgres" # no engine_version: AWS picks its current default
  instance_class    = "db.t4g.micro"
  allocated_storage = 20
  storage_type      = "gp3"
  # No max_allocated_storage, so storage autoscaling stays off (the console turned it on).
  storage_encrypted = true

  db_name  = "platform"
  username = "platform_admin"
  # RDS creates the password and keeps it in Secrets Manager; it never appears in
  # Terraform code or state.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.platform[0].name
  vpc_security_group_ids = [aws_security_group.rds.id]
  availability_zone      = aws_subnet.private["a"].availability_zone
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period  = 1
  skip_final_snapshot      = true # lab data, reloadable from curated
  delete_automated_backups = true
  deletion_protection      = false
  apply_immediately        = true
}

# The Glue role may read this one secret only.
data "aws_iam_policy_document" "glue_rds_secret" {
  count = var.enable_rds ? 1 : 0
  statement {
    sid       = "ReadRdsSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_db_instance.platform[0].master_user_secret[0].secret_arn]
  }
}

resource "aws_iam_role_policy" "glue_rds_secret" {
  count  = var.enable_rds ? 1 : 0
  name   = "glue-rds-secret"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_rds_secret[0].json
}

# Load job: curated Parquet -> RDS, inside the VPC. The database address and secret are
# passed in automatically, so recreating RDS needs no manual parameter changes.
resource "aws_glue_job" "load_rds" {
  count = var.enable_rds ? 1 : 0

  name              = "platform-load-rds"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  execution_class   = "FLEX"
  timeout           = 10
  max_retries       = 0
  connections       = [aws_glue_connection.vpc.name] # run inside the VPC

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "${local.curated_s3}/${aws_s3_object.load_script.key}"
  }

  default_arguments = {
    "--job-language" = "python"
    "--curated_path" = "${local.curated_s3}/curated/products/"
    "--secret_id"    = aws_db_instance.platform[0].master_user_secret[0].secret_arn
    "--db_host"      = aws_db_instance.platform[0].address
    "--db_name"      = aws_db_instance.platform[0].db_name
  }

  # The job can only reach Secrets Manager and Logs once the endpoints exist.
  depends_on = [aws_vpc_endpoint.interface, aws_iam_role_policy.glue_rds_secret]
}
