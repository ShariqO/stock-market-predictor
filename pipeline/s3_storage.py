"""
pipeline/s3_storage.py — S3-backed storage layer

Provides read/write functions for Parquet and CSV files on S3,
mirroring the local file I/O interface in utils.py.

Used when MODE=aws. All S3 paths follow the same partition
structure as the local data lake:
    s3://<bucket>/<layer>/<dataset>/dt=YYYY-MM-DD/<filename>
"""

import io
import os
from typing import Optional

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.config import setup_logger, get_s3_bucket, get_aws_region

logger = setup_logger("pipeline.s3_storage")

# ── Lazy boto3 client ──────────────────────────────────────

_s3_client = None


def _get_s3_client():
    """Get or create a boto3 S3 client (singleton)."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=get_aws_region())
    return _s3_client


# ── Path helpers ───────────────────────────────────────────

def s3_lake_key(layer: str, dataset: str, dt: str,
                filename: str = "data.parquet") -> str:
    """
    Build an S3 object key for the data lake.

    Example:
        s3_lake_key("bronze", "prices", "2024-01-15")
        → "bronze/prices/dt=2024-01-15/data.parquet"
    """
    return f"{layer}/{dataset}/dt={dt}/{filename}"


# ── Write operations ───────────────────────────────────────

def s3_write_parquet(df: pd.DataFrame, bucket: str, key: str) -> str:
    """
    Write a DataFrame as Parquet to S3.

    Args:
        df: DataFrame to write.
        bucket: S3 bucket name.
        key: S3 object key (path).

    Returns:
        Full S3 URI (s3://bucket/key).
    """
    client = _get_s3_client()

    # Convert DataFrame to Parquet bytes in memory
    table = pa.Table.from_pandas(df, preserve_index=False)
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    buffer.seek(0)

    client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())
    uri = f"s3://{bucket}/{key}"
    logger.info(f"Wrote {len(df):,} rows → {uri}")
    return uri


def s3_write_csv(df: pd.DataFrame, bucket: str, key: str) -> str:
    """
    Write a DataFrame as CSV to S3.

    Args:
        df: DataFrame to write.
        bucket: S3 bucket name.
        key: S3 object key (path).

    Returns:
        Full S3 URI.
    """
    client = _get_s3_client()

    buffer = io.StringIO()
    df.to_csv(buffer, index=False)

    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue().encode("utf-8"),
    )
    uri = f"s3://{bucket}/{key}"
    logger.info(f"Wrote {len(df):,} rows (CSV) → {uri}")
    return uri


# ── Read operations ────────────────────────────────────────

def s3_read_parquet(bucket: str, key: str) -> pd.DataFrame:
    """
    Read a Parquet file from S3.

    Args:
        bucket: S3 bucket name.
        key: S3 object key.

    Returns:
        DataFrame.

    Raises:
        FileNotFoundError: If the object doesn't exist.
    """
    client = _get_s3_client()

    try:
        response = client.get_object(Bucket=bucket, Key=key)
        buffer = io.BytesIO(response["Body"].read())
        df = pd.read_parquet(buffer, engine="pyarrow")
        logger.debug(f"Read {len(df):,} rows ← s3://{bucket}/{key}")
        return df
    except client.exceptions.NoSuchKey:
        raise FileNotFoundError(f"S3 object not found: s3://{bucket}/{key}")
    except Exception as e:
        if "NoSuchKey" in str(e) or "404" in str(e):
            raise FileNotFoundError(f"S3 object not found: s3://{bucket}/{key}")
        raise


def s3_list_partitions(bucket: str, prefix: str) -> list[str]:
    """
    List dt= partition dates under an S3 prefix.

    Args:
        bucket: S3 bucket name.
        prefix: S3 prefix (e.g., "gold/predictions/").

    Returns:
        Sorted list of date strings.
    """
    client = _get_s3_client()

    # Ensure prefix ends with /
    if not prefix.endswith("/"):
        prefix += "/"

    response = client.list_objects_v2(
        Bucket=bucket,
        Prefix=prefix,
        Delimiter="/",
    )

    dates = []
    for cp in response.get("CommonPrefixes", []):
        folder = cp["Prefix"].rstrip("/").split("/")[-1]
        if folder.startswith("dt="):
            dates.append(folder.replace("dt=", ""))

    # Handle pagination
    while response.get("IsTruncated"):
        response = client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            Delimiter="/",
            ContinuationToken=response["NextContinuationToken"],
        )
        for cp in response.get("CommonPrefixes", []):
            folder = cp["Prefix"].rstrip("/").split("/")[-1]
            if folder.startswith("dt="):
                dates.append(folder.replace("dt=", ""))

    return sorted(dates)


def s3_read_latest_parquet(bucket: str, prefix: str,
                           filename: str = "data.parquet") -> tuple[pd.DataFrame, str]:
    """
    Read the most recent partition from an S3 data lake path.

    Args:
        bucket: S3 bucket name.
        prefix: Base prefix (e.g., "gold/predictions/").
        filename: Parquet filename.

    Returns:
        Tuple of (DataFrame, date_string).
    """
    dates = s3_list_partitions(bucket, prefix)
    if not dates:
        raise FileNotFoundError(f"No partitions found at s3://{bucket}/{prefix}")

    latest_date = dates[-1]
    key = f"{prefix}dt={latest_date}/{filename}"
    df = s3_read_parquet(bucket, key)
    return df, latest_date


def s3_read_all_parquet(bucket: str, prefix: str,
                        filename: str = "data.parquet") -> pd.DataFrame:
    """
    Read all partitions from an S3 path and concatenate.

    Adds a 'dt' column with the partition date.

    Returns:
        Concatenated DataFrame with 'dt' column.
    """
    dates = s3_list_partitions(bucket, prefix)
    if not dates:
        return pd.DataFrame()

    frames = []
    for date_str in dates:
        key = f"{prefix}dt={date_str}/{filename}"
        try:
            df = s3_read_parquet(bucket, key)
            df["dt"] = date_str
            frames.append(df)
        except FileNotFoundError:
            pass

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ── Connectivity test ──────────────────────────────────────

def test_s3_connection():
    """
    Test S3 connectivity by listing the bucket.
    Prints success/failure message.
    """
    bucket = get_s3_bucket()
    if not bucket:
        print("❌ S3_BUCKET not configured. Set it in .env or config.yaml.")
        return False

    try:
        client = _get_s3_client()
        client.head_bucket(Bucket=bucket)
        print(f"✅ S3 connection successful: s3://{bucket}/")
        return True
    except Exception as e:
        print(f"❌ S3 connection failed: {e}")
        return False


if __name__ == "__main__":
    test_s3_connection()
