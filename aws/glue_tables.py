"""
aws/glue_tables.py — Create Glue Data Catalog tables

Creates the Glue database and tables so Athena can query
the S3 data lake directly. Tables use Hive-style partitioning
(dt=YYYY-MM-DD) and Parquet SerDe.

Usage:
    python aws/glue_tables.py

Run this once after creating the S3 bucket and populating it
with at least one day of data. Then run:
    MSCK REPAIR TABLE stock_predictor.<table_name>;
in the Athena console to discover existing partitions.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from pipeline.config import (
    setup_logger, get_s3_bucket, get_aws_region, get_glue_database
)

logger = setup_logger("aws.glue_tables")


def get_glue_client():
    """Create a boto3 Glue client."""
    return boto3.client("glue", region_name=get_aws_region())


def create_database(client, db_name: str, bucket: str):
    """Create the Glue database if it doesn't exist."""
    try:
        client.get_database(Name=db_name)
        logger.info(f"Database '{db_name}' already exists")
    except client.exceptions.EntityNotFoundException:
        client.create_database(
            DatabaseInput={
                "Name": db_name,
                "Description": "NASDAQ Day Trading Predictor - data lake catalog",
                "LocationUri": f"s3://{bucket}/",
            }
        )
        logger.info(f"✅ Created database '{db_name}'")


def create_table(client, db_name: str, table_name: str,
                 bucket: str, s3_prefix: str,
                 columns: list[dict]):
    """
    Create or update a Glue table with Parquet SerDe and dt partition.

    Args:
        client: boto3 Glue client.
        db_name: Glue database name.
        table_name: Table name.
        bucket: S3 bucket.
        s3_prefix: S3 prefix (e.g., "silver/features/").
        columns: List of column definitions [{"Name": ..., "Type": ...}].
    """
    table_input = {
        "Name": table_name,
        "Description": f"NASDAQ Predictor - {table_name}",
        "StorageDescriptor": {
            "Columns": columns,
            "Location": f"s3://{bucket}/{s3_prefix}",
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {"serialization.format": "1"},
            },
            "Compressed": False,
            "StoredAsSubDirectories": False,
        },
        "PartitionKeys": [
            {"Name": "dt", "Type": "string", "Comment": "Partition date (YYYY-MM-DD)"}
        ],
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "parquet",
            "has_encrypted_data": "false",
            "EXTERNAL": "TRUE",
        },
    }

    try:
        client.get_table(DatabaseName=db_name, Name=table_name)
        # Table exists — update it
        client.update_table(
            DatabaseName=db_name,
            TableInput=table_input,
        )
        logger.info(f"✅ Updated table '{db_name}.{table_name}'")
    except client.exceptions.EntityNotFoundException:
        # Table doesn't exist — create it
        client.create_table(
            DatabaseName=db_name,
            TableInput=table_input,
        )
        logger.info(f"✅ Created table '{db_name}.{table_name}'")


# ── Table schemas ──────────────────────────────────────────

SILVER_FEATURES_COLUMNS = [
    {"Name": "ticker", "Type": "string"},
    {"Name": "date", "Type": "string"},
    {"Name": "open", "Type": "double"},
    {"Name": "high", "Type": "double"},
    {"Name": "low", "Type": "double"},
    {"Name": "close", "Type": "double"},
    {"Name": "volume", "Type": "bigint"},
    {"Name": "vol_avg_5d", "Type": "double"},
    {"Name": "vol_avg_20d", "Type": "double"},
    {"Name": "vol_spike_ratio", "Type": "double"},
    {"Name": "atr_14d", "Type": "double"},
    {"Name": "daily_return", "Type": "double"},
    {"Name": "volatility_20d", "Type": "double"},
    {"Name": "rsi_14d", "Type": "double"},
    {"Name": "sma_5d", "Type": "double"},
    {"Name": "sma_10d", "Type": "double"},
    {"Name": "sma_20d", "Type": "double"},
    {"Name": "sma_50d", "Type": "double"},
    {"Name": "price_vs_sma5", "Type": "double"},
    {"Name": "price_vs_sma20", "Type": "double"},
    {"Name": "price_vs_sma50", "Type": "double"},
    {"Name": "return_1d", "Type": "double"},
    {"Name": "return_3d", "Type": "double"},
    {"Name": "return_5d", "Type": "double"},
    {"Name": "gap", "Type": "double"},
    {"Name": "intraday_range", "Type": "double"},
    {"Name": "intraday_range_pct", "Type": "double"},
    {"Name": "target", "Type": "double"},
    {"Name": "name", "Type": "string"},
    {"Name": "sector", "Type": "string"},
    {"Name": "industry", "Type": "string"},
]

GOLD_PREDICTIONS_COLUMNS = [
    {"Name": "ticker", "Type": "string"},
    {"Name": "date", "Type": "string"},
    {"Name": "open", "Type": "double"},
    {"Name": "high", "Type": "double"},
    {"Name": "low", "Type": "double"},
    {"Name": "close", "Type": "double"},
    {"Name": "volume", "Type": "bigint"},
    {"Name": "name", "Type": "string"},
    {"Name": "sector", "Type": "string"},
    {"Name": "industry", "Type": "string"},
    {"Name": "predicted_probability", "Type": "double"},
    {"Name": "as_of_date", "Type": "string"},
    {"Name": "rank", "Type": "bigint"},
    {"Name": "last_close", "Type": "double"},
    {"Name": "top_features", "Type": "string"},
]

GOLD_METRICS_COLUMNS = [
    {"Name": "as_of_date", "Type": "string"},
    {"Name": "precision_at_5", "Type": "double"},
    {"Name": "hit_rate", "Type": "double"},
    {"Name": "num_tickers_scored", "Type": "bigint"},
    {"Name": "positive_rate", "Type": "double"},
]


def main():
    """Create all Glue Data Catalog tables."""
    bucket = get_s3_bucket()
    db_name = get_glue_database()
    region = get_aws_region()

    if not bucket:
        logger.error("❌ S3_BUCKET not configured. Set it in .env or config.yaml.")
        sys.exit(1)

    logger.info(f"Creating Glue tables in '{db_name}' | bucket: {bucket} | region: {region}")

    client = get_glue_client()

    # Create database
    create_database(client, db_name, bucket)

    # Create tables
    create_table(client, db_name, "silver_features",
                 bucket, "silver/features/", SILVER_FEATURES_COLUMNS)

    create_table(client, db_name, "gold_predictions",
                 bucket, "gold/predictions/", GOLD_PREDICTIONS_COLUMNS)

    create_table(client, db_name, "gold_model_metrics",
                 bucket, "gold/model_metrics/", GOLD_METRICS_COLUMNS)

    logger.info(f"\n✅ All Glue tables created successfully!")
    logger.info(f"\nNext steps:")
    logger.info(f"  1. Run the pipeline with MODE=aws to populate S3")
    logger.info(f"  2. In the Athena console, run for each table:")
    logger.info(f"     MSCK REPAIR TABLE {db_name}.silver_features;")
    logger.info(f"     MSCK REPAIR TABLE {db_name}.gold_predictions;")
    logger.info(f"     MSCK REPAIR TABLE {db_name}.gold_model_metrics;")
    logger.info(f"  3. Query your data:")
    logger.info(f"     SELECT * FROM {db_name}.gold_predictions WHERE rank <= 5 LIMIT 10;")


if __name__ == "__main__":
    main()
