"""Glue ETL job: raw product JSON -> data quality -> curated Parquet (Account B).

Chunk 4 version:
  1. Read raw files (each one JSON object with a "records" list) from Account A.
  2. Flatten them: one row per product record, with proper column types.
  3. Glue Data Quality checks every row against RULESET (DQDL).
  4. Rows that fail any rule, and duplicates, go to quarantine with the reasons.
  5. The rule scorecard is written to dq-results. If more than MAX_FAILED_SHARE
     of the rows were rejected (rule DQ-08) the job fails on purpose here.
  6. Otherwise valid rows are written as Parquet, partitioned by date and category.

Job parameters (Glue job -> "Job details" -> "Job parameters"):
  --input_path        s3://.../raw/... file or folder to read
  --output_path       s3://.../curated/products/
  --quarantine_path   s3://.../quarantine/products/
  --dq_results_path   s3://.../dq-results/products/
"""

import sys
from datetime import datetime, timezone

from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from awsglue.job import Job
from awsglue.transforms import SelectFromCollection
from awsglue.utils import getResolvedOptions
from awsgluedq.transforms import EvaluateDataQuality
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import (ArrayType, BooleanType, DoubleType, StringType,
                               StructField, StructType)

# Rule IDs in comments match docs/03-quality-ops/DATA_QUALITY.md.
RULESET = """
Rules = [
    RowCount > 0,
    IsComplete "product_id",
    IsComplete "name",
    ColumnLength "name" > 0,
    IsComplete "price",
    ColumnValues "price" > 0,
    ColumnValues "currency" in ["GBP", "USD", "EUR"],
    IsComplete "scraped_at",
    ColumnValues "scraped_at" <= now(),
    IsComplete "category"
]
"""
# DQ-07: RowCount. DQ-01: product_id (uniqueness is handled after the checks).
# DQ-02: name. DQ-03: price. DQ-04: currency. DQ-05: scraped_at. DQ-06: category.

MAX_FAILED_SHARE = 0.30  # DQ-08: fail the job if more rows than this are rejected

# The shape of a raw file. Declaring it (instead of letting Spark guess) means a
# file with a missing or oddly typed field still reads the same way every time.
RAW_SCHEMA = StructType([
    StructField("source", StringType()),
    StructField("scraped_at", StringType()),
    StructField("records", ArrayType(StructType([
        StructField("product_id", StringType()),
        StructField("name", StringType()),
        StructField("category", StringType()),
        StructField("price", DoubleType()),
        StructField("currency", StringType()),
        StructField("in_stock", BooleanType()),
        StructField("scraped_at", StringType()),
        StructField("url", StringType()),
    ]))),
])

PRODUCT_COLUMNS = ["product_id", "name", "category", "price", "currency",
                   "in_stock", "source", "scraped_at"]


def flatten(raw):
    """One row per product record, with the types the curated table expects."""
    # Remember which file each row came from before anything else.
    with_file = raw.withColumn("input_file", F.input_file_name())
    records = (with_file
               .select("source", "input_file", F.explode("records").alias("r"))
               .select("source", "input_file", "r.*"))
    # A timestamp that cannot be parsed becomes null instead of failing the job;
    # the original text is kept in scraped_at_raw so quarantine shows what arrived.
    return records.select(
        F.col("product_id"),
        F.trim(F.col("name")).alias("name"),
        F.col("category"),
        F.col("price").cast("decimal(10,2)").alias("price"),
        F.col("currency"),
        F.col("in_stock"),
        F.col("source"),
        F.to_timestamp("scraped_at", "yyyy-MM-dd'T'HH:mm:ss'Z'").alias("scraped_at"),
        F.col("scraped_at").alias("scraped_at_raw"),
        F.col("input_file"),
    )


def main():
    # Glue always parses --JOB_RUN_ID itself and includes it in the result, so it
    # must not be listed here (listing it raises "conflicting option string").
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "input_path", "output_path",
                                         "quarantine_path", "dq_results_path"])

    glue_context = GlueContext(SparkContext.getOrCreate())
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    spark.conf.set("spark.sql.session.timeZone", "UTC")
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    run_id = args.get("JOB_RUN_ID") or datetime.now(timezone.utc).strftime("manual-%Y%m%dT%H%M%S")

    raw = spark.read.schema(RAW_SCHEMA).option("multiLine", True).json(args["input_path"])
    products = flatten(raw).cache()
    total_rows = products.count()

    # --- Glue Data Quality -------------------------------------------------
    # process_rows checks every row and returns two results:
    #   ruleOutcomes:     one line per rule (Passed / Failed) for the whole data
    #   rowLevelOutcomes: the input rows plus columns saying which rules each row
    #                     passed and failed, and an overall Passed / Failed
    dq = EvaluateDataQuality().process_rows(
        frame=DynamicFrame.fromDF(products, glue_context, "products"),
        ruleset=RULESET,
        publishing_options={
            "dataQualityEvaluationContext": "products_dq",
            "enableDataQualityCloudWatchMetrics": True,
            "enableDataQualityResultsPublishing": True,
        },
        additional_options={"performanceTuning.caching": "CACHE_NOTHING"},
    )
    rule_outcomes = SelectFromCollection.apply(dfc=dq, key="ruleOutcomes").toDF()
    rows = SelectFromCollection.apply(dfc=dq, key="rowLevelOutcomes").toDF().cache()

    passed = rows.filter(F.col("DataQualityEvaluationResult") == "Passed")
    failed = (rows.filter(F.col("DataQualityEvaluationResult") != "Passed")
              .withColumn("failed_rules", F.col("DataQualityRulesFail")))

    # --- Duplicates ----------------------------------------------------------
    # Same product at the same moment twice: keep the first, quarantine the rest.
    first_row = F.row_number().over(
        Window.partitionBy("product_id", "scraped_at").orderBy("input_file"))
    ranked = passed.withColumn("_n", first_row)
    valid = ranked.filter("_n = 1").select(*PRODUCT_COLUMNS)
    duplicates = (ranked.filter("_n > 1")
                  .withColumn("failed_rules", F.array(F.lit("Duplicate product_id and scraped_at"))))

    # --- Quarantine ----------------------------------------------------------
    quarantine_columns = PRODUCT_COLUMNS + ["scraped_at_raw", "input_file", "failed_rules"]
    quarantine = (failed.select(*quarantine_columns)
                  .unionByName(duplicates.select(*quarantine_columns))
                  .withColumn("run_id", F.lit(run_id))
                  .withColumn("processed_date", F.date_format(F.current_timestamp(), "yyyy-MM-dd")))

    valid_rows = valid.count()
    quarantined_rows = quarantine.count()
    print(f"records read: {total_rows}, valid: {valid_rows}, quarantined: {quarantined_rows} "
          f"(failed rules: {failed.count()}, duplicates: {duplicates.count()})")
    rule_outcomes.select("Rule", "Outcome", "FailureReason").show(truncate=False)

    # --- Quarantine and scorecard are always written ---------------------------
    if quarantined_rows:
        # JSON so rejected rows are easy to read by eye; one folder per day and run.
        (quarantine.coalesce(1)
         .write.mode("append")
         .partitionBy("processed_date", "run_id")
         .json(args["quarantine_path"]))

    (rule_outcomes
     .withColumn("run_id", F.lit(run_id))
     .withColumn("records_read", F.lit(total_rows))
     .withColumn("records_valid", F.lit(valid_rows))
     .withColumn("records_quarantined", F.lit(quarantined_rows))
     .coalesce(1)
     .write.mode("append")
     .json(f"{args['dq_results_path'].rstrip('/')}/run_id={run_id}/"))

    # --- DQ-08: too many rejects means the file itself is suspect -----------------
    # Checked before the curated write, so a suspect file adds nothing to curated.
    if total_rows == 0:
        # DQ-07: a corrupt or empty file reads as zero records.
        raise RuntimeError("DQ-07: no readable records (file is empty or not valid JSON); "
                           "nothing written to curated")
    failed_share = quarantined_rows / total_rows
    if failed_share > MAX_FAILED_SHARE:
        raise RuntimeError(
            f"DQ-08: {failed_share:.1%} of {total_rows} rows rejected "
            f"(limit {MAX_FAILED_SHARE:.0%}); nothing written to curated, see quarantine")

    # --- Curated output ------------------------------------------------------------
    (valid.withColumn("date", F.date_format("scraped_at", "yyyy-MM-dd"))
     .repartition("date", "category")
     .write.mode("overwrite")
     .partitionBy("date", "category")
     .parquet(args["output_path"]))
    print(f"wrote {valid_rows} valid rows to {args['output_path']}")

    job.commit()


if __name__ == "__main__":
    main()
