# Private network for jobs that talk to RDS. No internet gateway, no NAT: AWS services
# are reached only through endpoints (decision 22).
#
# Always created (free): VPC, subnets, route tables, S3 gateway endpoint, security groups,
# Glue network connection. Only with enable_rds (paid per hour): the interface endpoints.

resource "aws_vpc" "platform" {
  cidr_block           = "10.20.0.0/16" # Account A is planned as 10.10.0.0/16, so peering never overlaps
  enable_dns_hostnames = true           # needed for private DNS on interface endpoints and RDS
  enable_dns_support   = true
  tags                 = { Name = "platform-vpc" }
}

# One private subnet per Availability Zone; RDS needs subnets in at least two.
locals {
  private_subnets = {
    a = { az = "${local.region}a", cidr = "10.20.128.0/20" }
    b = { az = "${local.region}b", cidr = "10.20.144.0/20" }
  }
}

# for_each creates one subnet per entry above: aws_subnet.private["a"] and ["b"].
resource "aws_subnet" "private" {
  for_each                = local.private_subnets
  vpc_id                  = aws_vpc.platform.id
  availability_zone       = each.value.az
  cidr_block              = each.value.cidr
  map_public_ip_on_launch = false
  tags                    = { Name = "platform-subnet-private-${each.value.az}" }
}

# Route tables with only the built-in local route (no internet); the S3 endpoint adds its own.
resource "aws_route_table" "private" {
  for_each = local.private_subnets
  vpc_id   = aws_vpc.platform.id
  tags     = { Name = "platform-rtb-private-${each.value.az}" }
}

resource "aws_route_table_association" "private" {
  for_each       = local.private_subnets
  subnet_id      = aws_subnet.private[each.key].id
  route_table_id = aws_route_table.private[each.key].id
}

# Free private road to S3 (curated bucket, scripts, Account A's raw bucket).
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.platform.id
  service_name      = "com.amazonaws.${local.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for rt in aws_route_table.private : rt.id]
  tags              = { Name = "platform-vpce-s3" }
}

# --- Security groups ---------------------------------------------------------------------
# Rules are separate resources and reference groups, not IP ranges, so they stay correct
# however Glue's addresses change. Terraform removes AWS's default "allow all outbound"
# rule, so only the rules below exist.

resource "aws_security_group" "glue" {
  name        = "platform-glue-sg"
  description = "Glue jobs in the platform VPC"
  vpc_id      = aws_vpc.platform.id
  tags        = { Name = "platform-glue-sg" }
}

# Required by Glue: its workers talk to each other.
resource "aws_vpc_security_group_ingress_rule" "glue_self" {
  security_group_id            = aws_security_group.glue.id
  referenced_security_group_id = aws_security_group.glue.id
  ip_protocol                  = "tcp"
  from_port                    = 0
  to_port                      = 65535
  description                  = "Glue workers talk to each other"
}

# Glue needs outbound to reach RDS, the endpoints and S3. Nothing beyond the VPC is
# reachable anyway (no internet gateway).
resource "aws_vpc_security_group_egress_rule" "glue_all" {
  security_group_id = aws_security_group.glue.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "Outbound to RDS, endpoints and S3 inside the VPC"
}

resource "aws_security_group" "rds" {
  name        = "platform-rds-sg"
  description = "RDS PostgreSQL, Glue only"
  vpc_id      = aws_vpc.platform.id
  tags        = { Name = "platform-rds-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_glue" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.glue.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL from Glue only"
}

resource "aws_security_group" "endpoints" {
  name        = "platform-endpoints-sg"
  description = "Interface endpoints, Glue only"
  vpc_id      = aws_vpc.platform.id
  tags        = { Name = "platform-endpoints-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_glue" {
  security_group_id            = aws_security_group.endpoints.id
  referenced_security_group_id = aws_security_group.glue.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "HTTPS from Glue only"
}

# --- Interface endpoints (only with enable_rds) ---------------------------------------------
# Private doors to the AWS APIs the load job calls. One subnet only, to halve the cost
# (decision 23). toset(...) with for_each creates one endpoint per service.
resource "aws_vpc_endpoint" "interface" {
  for_each            = var.enable_rds ? toset(["secretsmanager", "logs", "glue"]) : toset([])
  vpc_id              = aws_vpc.platform.id
  service_name        = "com.amazonaws.${local.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private["a"].id]
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true
  tags                = { Name = "platform-vpce-${each.key}" }
}

# --- Glue network connection ------------------------------------------------------------
# Tells Glue to start a job's workers inside subnet a with the Glue security group.
resource "aws_glue_connection" "vpc" {
  name            = "platform-vpc-network"
  connection_type = "NETWORK"

  physical_connection_requirements {
    availability_zone      = aws_subnet.private["a"].availability_zone
    subnet_id              = aws_subnet.private["a"].id
    security_group_id_list = [aws_security_group.glue.id]
  }
}
