"""Glue load job: curated Parquet -> RDS PostgreSQL (Account B, runs inside the VPC).

  1. Read the database password from Secrets Manager (the RDS-managed secret).
  2. Read curated Parquet from S3 (through the S3 gateway endpoint).
  3. Create the products table if it does not exist yet (the job is the only thing
     that can reach the private database, so it also owns the table definition).
  4. Copy the rows into a staging table, then insert them into products with
     ON CONFLICT DO NOTHING, so running the job twice adds no duplicates (AC-05).

Job parameters (Glue job -> "Job details" -> "Job parameters"):
  --curated_path   s3://.../curated/products/
  --secret_id      ARN of the RDS-managed secret (holds username and password)
  --db_host        RDS endpoint, e.g. platform-db.xxxx.ap-south-1.rds.amazonaws.com
  --db_name        database name, e.g. platform
"""

import json
import sys

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

# Same as docs/02-architecture/DATA_MODEL.md. The primary key is what makes
# reloading a file safe: the same product at the same moment can exist only once.
CREATE_PRODUCTS = """
CREATE TABLE IF NOT EXISTS products (
  product_id  TEXT NOT NULL,
  scraped_at  TIMESTAMPTZ NOT NULL,
  name        TEXT NOT NULL,
  category    TEXT NOT NULL,
  price       NUMERIC(10,2) NOT NULL CHECK (price > 0),
  currency    CHAR(3) NOT NULL,
  in_stock    BOOLEAN NOT NULL,
  source      TEXT NOT NULL,
  loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (product_id, scraped_at)
)
"""

# A plain landing table with no rules, emptied at the start of every run.
CREATE_STAGING = """
CREATE TABLE IF NOT EXISTS products_staging (
  product_id  TEXT,
  scraped_at  TIMESTAMPTZ,
  name        TEXT,
  category    TEXT,
  price       NUMERIC(10,2),
  currency    TEXT,
  in_stock    BOOLEAN,
  source      TEXT
)
"""

MERGE = """
INSERT INTO products (product_id, scraped_at, name, category, price, currency, in_stock, source)
SELECT product_id, scraped_at, name, category, price, currency, in_stock, source
FROM products_staging
ON CONFLICT (product_id, scraped_at) DO NOTHING
"""

COLUMNS = ["product_id", "scraped_at", "name", "category", "price", "currency",
           "in_stock", "source"]


def run_sql(spark, url, user, password, statements):
    """Run SQL statements through a plain JDBC connection on the driver.

    Spark can only read and write tables; CREATE TABLE and INSERT ... SELECT need
    a normal database connection, which Java's DriverManager provides.
    Returns the row count reported by the last statement.
    """
    jvm = spark.sparkContext._gateway.jvm
    conn = jvm.java.sql.DriverManager.getConnection(url, user, password)
    try:
        conn.setAutoCommit(False)
        stmt = conn.createStatement()
        count = 0
        for sql in statements:
            if sql.lstrip().upper().startswith("SELECT"):
                rs = stmt.executeQuery(sql)
                rs.next()
                count = rs.getLong(1)
            else:
                count = stmt.executeUpdate(sql)
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "curated_path", "secret_id",
                                         "db_host", "db_name"])
    glue_context = GlueContext(SparkContext.getOrCreate())
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    # The RDS-managed secret is JSON: {"username": "...", "password": "..."}.
    secret = json.loads(boto3.client("secretsmanager")
                        .get_secret_value(SecretId=args["secret_id"])["SecretString"])
    user, password = secret["username"], secret["password"]
    # sslmode=require: RDS PostgreSQL only accepts encrypted connections by default.
    url = f"jdbc:postgresql://{args['db_host']}:5432/{args['db_name']}?sslmode=require"

    run_sql(spark, url, user, password,
            [CREATE_PRODUCTS, CREATE_STAGING, "TRUNCATE products_staging"])

    curated = spark.read.parquet(args["curated_path"]).select(*COLUMNS)
    rows_in = curated.count()
    (curated.write
     .mode("append")
     .option("driver", "org.postgresql.Driver")
     .option("batchsize", 1000)
     .jdbc(url, "products_staging", properties={"user": user, "password": password}))

    inserted = run_sql(spark, url, user, password, [MERGE])
    total = run_sql(spark, url, user, password, ["SELECT COUNT(*) FROM products"])
    print(f"curated rows read: {rows_in}, newly inserted: {inserted}, "
          f"already present (skipped): {rows_in - inserted}, rows in products now: {total}")

    job.commit()


if __name__ == "__main__":
    main()
