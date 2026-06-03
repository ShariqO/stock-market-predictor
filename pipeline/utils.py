"""
pipeline/utils.py — Shared utilities

Parquet I/O, CSV output, date helpers, ticker cleaning, and
reusable helpers used across all pipeline modules.

I/O functions are MODE-aware:
  MODE=local → reads/writes to local _lake/ directory
  MODE=aws   → reads/writes to S3 bucket
"""

import re
import datetime as dt
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from pipeline.config import setup_logger, get_universe_config, get_mode, get_s3_bucket

logger = setup_logger("pipeline.utils")


# ── Mode-aware I/O ─────────────────────────────────────────

def _is_aws_mode() -> bool:
    """Check if we're running in AWS mode."""
    return get_mode() == "aws"


def _s3_key_from_path(path: Path, filename: str) -> str:
    """
    Convert a local lake path to an S3 key.

    Local path: ./_lake/bronze/prices/dt=2024-01-15/
    S3 key:     bronze/prices/dt=2024-01-15/data.parquet
    """
    # Find the part after _lake/
    parts = path.parts
    try:
        lake_idx = parts.index("_lake")
        relative = "/".join(parts[lake_idx + 1:])
    except ValueError:
        relative = str(path)
    return f"{relative}/{filename}"


def _s3_prefix_from_path(path: Path) -> str:
    """Convert a local lake base path to an S3 prefix."""
    parts = path.parts
    try:
        lake_idx = parts.index("_lake")
        relative = "/".join(parts[lake_idx + 1:])
    except ValueError:
        relative = str(path)
    return f"{relative}/"


# ── Parquet I/O ────────────────────────────────────────────

def write_parquet(df: pd.DataFrame, path: Path, filename: str = "data.parquet") -> Path:
    """
    Write a DataFrame as a Parquet file.

    In local mode, writes to the local filesystem.
    In AWS mode, writes to S3.

    Args:
        df: DataFrame to write.
        path: Directory path (e.g., _lake/bronze/prices/dt=2024-01-15/).
        filename: Parquet file name within the directory.

    Returns:
        Full path to the written file (local mode) or Path with S3 info.
    """
    if _is_aws_mode():
        from pipeline.s3_storage import s3_write_parquet
        bucket = get_s3_bucket()
        key = _s3_key_from_path(path, filename)
        s3_write_parquet(df, bucket, key)
        return path / filename
    else:
        path.mkdir(parents=True, exist_ok=True)
        full_path = path / filename
        df.to_parquet(full_path, index=False, engine="pyarrow")
        logger.info(f"Wrote {len(df):,} rows → {full_path}")
        return full_path


def read_parquet(path: Path, filename: str = "data.parquet") -> pd.DataFrame:
    """
    Read a Parquet file from a partitioned directory.

    In local mode, reads from local filesystem.
    In AWS mode, reads from S3.

    Args:
        path: Directory containing the Parquet file.
        filename: Name of the Parquet file.

    Returns:
        DataFrame.

    Raises:
        FileNotFoundError: If the file doesn't exist.
    """
    if _is_aws_mode():
        from pipeline.s3_storage import s3_read_parquet
        bucket = get_s3_bucket()
        key = _s3_key_from_path(path, filename)
        return s3_read_parquet(bucket, key)
    else:
        full_path = path / filename
        if not full_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {full_path}")
        df = pd.read_parquet(full_path, engine="pyarrow")
        logger.debug(f"Read {len(df):,} rows ← {full_path}")
        return df


def read_latest_parquet(base_path: Path, filename: str = "data.parquet") -> tuple[pd.DataFrame, str]:
    """
    Read the most recent partition from a data lake directory.

    Scans for dt=YYYY-MM-DD subdirectories and reads the latest.

    Args:
        base_path: Base directory (e.g., _lake/gold/predictions/).
        filename: Parquet file name.

    Returns:
        Tuple of (DataFrame, date_string).

    Raises:
        FileNotFoundError: If no partitions exist.
    """
    if _is_aws_mode():
        from pipeline.s3_storage import s3_read_latest_parquet
        bucket = get_s3_bucket()
        prefix = _s3_prefix_from_path(base_path)
        return s3_read_latest_parquet(bucket, prefix, filename)
    else:
        if not base_path.exists():
            raise FileNotFoundError(f"Base path not found: {base_path}")

        partitions = sorted([
            d.name for d in base_path.iterdir()
            if d.is_dir() and d.name.startswith("dt=")
        ])
        if not partitions:
            raise FileNotFoundError(f"No partitions found in {base_path}")

        latest = partitions[-1]
        date_str = latest.replace("dt=", "")
        df = read_parquet(base_path / latest, filename)
        return df, date_str


def read_all_parquet(base_path: Path, filename: str = "data.parquet") -> pd.DataFrame:
    """
    Read all partitions from a data lake directory and concatenate.

    Adds a 'dt' column with the partition date.

    Returns:
        Concatenated DataFrame with 'dt' column.
    """
    if _is_aws_mode():
        from pipeline.s3_storage import s3_read_all_parquet
        bucket = get_s3_bucket()
        prefix = _s3_prefix_from_path(base_path)
        return s3_read_all_parquet(bucket, prefix, filename)
    else:
        if not base_path.exists():
            return pd.DataFrame()

        partitions = sorted([
            d for d in base_path.iterdir()
            if d.is_dir() and d.name.startswith("dt=")
        ])

        frames = []
        for part_dir in partitions:
            fpath = part_dir / filename
            if fpath.exists():
                df = pd.read_parquet(fpath, engine="pyarrow")
                df["dt"] = part_dir.name.replace("dt=", "")
                frames.append(df)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)


# ── CSV I/O ────────────────────────────────────────────────

def write_csv(df: pd.DataFrame, path: Path, filename: str = "data.csv") -> Path:
    """Write a DataFrame as CSV inside the given directory."""
    if _is_aws_mode():
        from pipeline.s3_storage import s3_write_csv
        bucket = get_s3_bucket()
        key = _s3_key_from_path(path, filename)
        s3_write_csv(df, bucket, key)
        return path / filename
    else:
        path.mkdir(parents=True, exist_ok=True)
        full_path = path / filename
        df.to_csv(full_path, index=False)
        logger.info(f"Wrote {len(df):,} rows (CSV) → {full_path}")
        return full_path


# ── Date helpers ───────────────────────────────────────────

def get_today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return dt.date.today().isoformat()


def get_trading_date() -> str:
    """
    Return the most recent trading date as YYYY-MM-DD.

    If today is a weekday, returns today.
    If today is Saturday, returns Friday.
    If today is Sunday, returns Friday.

    Note: Does not account for market holidays.
    """
    today = dt.date.today()
    weekday = today.weekday()  # Mon=0 … Sun=6
    if weekday == 5:  # Saturday
        return (today - dt.timedelta(days=1)).isoformat()
    elif weekday == 6:  # Sunday
        return (today - dt.timedelta(days=2)).isoformat()
    return today.isoformat()


# ── Ticker cleaning ───────────────────────────────────────

def is_valid_ticker(ticker: str, name: Optional[str] = None) -> bool:
    """
    Check whether a ticker represents a valid common stock.

    Filters out warrants, rights, units, preferred shares, ETFs,
    and other non-common-stock instruments based on ticker patterns
    and name patterns from config.

    Args:
        ticker: Stock ticker symbol.
        name: Optional company name for additional filtering.

    Returns:
        True if the ticker appears to be a valid common stock.
    """
    if not ticker or not isinstance(ticker, str):
        return False

    universe_cfg = get_universe_config()

    # Check ticker patterns
    for pattern in universe_cfg.get("exclude_ticker_patterns", []):
        if re.search(pattern, ticker):
            return False

    # Tickers with special characters are usually not common stocks
    if any(c in ticker for c in [".", "/", "-", "^"]):
        # Exception: BRK.B style tickers (class shares) — allow dots
        # But filter out most others
        if "/" in ticker or "-" in ticker or "^" in ticker:
            return False

    # Check name patterns
    if name:
        for pattern in universe_cfg.get("exclude_name_patterns", []):
            if pattern.lower() in name.lower():
                return False

    return True


def clean_ticker_list(tickers: list[str]) -> list[str]:
    """Filter a list of tickers to valid common stocks only."""
    valid = [t for t in tickers if is_valid_ticker(t)]
    removed = len(tickers) - len(valid)
    if removed > 0:
        logger.info(f"Removed {removed} invalid tickers from list of {len(tickers)}")
    return valid


def safe_float(value, default: float = np.nan) -> float:
    """Safely convert a value to float, returning default on failure."""
    try:
        result = float(value)
        if np.isnan(result) or np.isinf(result):
            return default
        return result
    except (ValueError, TypeError):
        return default
