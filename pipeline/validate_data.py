"""
pipeline/validate_data.py — Lightweight data quality checks

Runs validation checks at each layer of the data lake.
Returns structured results (pass/fail + details) so the pipeline
can decide whether to continue or halt.
"""

from typing import Optional

import pandas as pd
import numpy as np

from pipeline.config import setup_logger

logger = setup_logger("pipeline.validate")


class ValidationResult:
    """Container for a single validation check result."""

    def __init__(self, check_name: str, passed: bool, message: str,
                 details: Optional[dict] = None):
        self.check_name = check_name
        self.passed = passed
        self.message = message
        self.details = details or {}

    def __repr__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status} | {self.check_name}: {self.message}"


class ValidationReport:
    """Aggregates multiple ValidationResults."""

    def __init__(self, layer: str):
        self.layer = layer
        self.results: list[ValidationResult] = []

    def add(self, result: ValidationResult):
        self.results.append(result)
        level = "info" if result.passed else "warning"
        getattr(logger, level)(str(result))

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed]

    def summary(self) -> str:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        status = "ALL PASSED" if self.all_passed else f"{failed} FAILED"
        return f"[{self.layer.upper()}] Validation: {passed}/{total} checks passed — {status}"


# ═══════════════════════════════════════════════════════════
# Bronze-layer checks
# ═══════════════════════════════════════════════════════════

def validate_bronze_prices(df: pd.DataFrame) -> ValidationReport:
    """Validate raw OHLCV price data from the Bronze layer."""
    report = ValidationReport("bronze/prices")

    # Check 1: Required columns exist
    required_cols = {"ticker", "date", "open", "high", "low", "close", "volume"}
    # Be flexible with column case
    df_cols_lower = {c.lower() for c in df.columns}
    missing = required_cols - df_cols_lower
    report.add(ValidationResult(
        "required_columns",
        len(missing) == 0,
        f"Missing columns: {missing}" if missing else "All OHLCV columns present",
        {"missing": list(missing)}
    ))

    if missing:
        return report  # Can't run further checks without columns

    # Normalize column names for remaining checks
    df = df.rename(columns={c: c.lower() for c in df.columns})

    # Check 2: No negative volume
    neg_vol = (df["volume"] < 0).sum()
    report.add(ValidationResult(
        "no_negative_volume",
        neg_vol == 0,
        f"{neg_vol} rows have negative volume" if neg_vol > 0 else "No negative volumes",
        {"negative_volume_count": int(neg_vol)}
    ))

    # Check 3: No duplicate ticker/date rows
    dupes = df.duplicated(subset=["ticker", "date"]).sum()
    report.add(ValidationResult(
        "no_duplicate_ticker_date",
        dupes == 0,
        f"{dupes} duplicate ticker/date rows" if dupes > 0 else "No duplicates",
        {"duplicate_count": int(dupes)}
    ))

    # Check 4: OHLC are non-null
    price_cols = ["open", "high", "low", "close"]
    null_counts = {c: int(df[c].isna().sum()) for c in price_cols}
    total_nulls = sum(null_counts.values())
    report.add(ValidationResult(
        "ohlc_non_null",
        total_nulls == 0,
        f"Null values in price columns: {null_counts}" if total_nulls > 0
        else "All OHLC values present",
        {"null_counts": null_counts}
    ))

    # Check 5: High >= Low
    if total_nulls == 0:
        violations = (df["high"] < df["low"]).sum()
        report.add(ValidationResult(
            "high_gte_low",
            violations == 0,
            f"{violations} rows where High < Low" if violations > 0
            else "High >= Low for all rows",
            {"violation_count": int(violations)}
        ))

    # Check 6: Data has reasonable row count
    min_rows = 10
    report.add(ValidationResult(
        "minimum_rows",
        len(df) >= min_rows,
        f"Only {len(df)} rows (need >= {min_rows})" if len(df) < min_rows
        else f"{len(df):,} total rows",
        {"row_count": len(df)}
    ))

    return report


# ═══════════════════════════════════════════════════════════
# Silver-layer checks
# ═══════════════════════════════════════════════════════════

def validate_silver_features(df: pd.DataFrame, min_lookback: int = 60) -> ValidationReport:
    """Validate feature-engineered data from the Silver layer."""
    report = ValidationReport("silver/features")

    # Check 1: Required base columns
    required_cols = {"ticker", "date", "open", "high", "low", "close", "volume"}
    df_cols_lower = {c.lower() for c in df.columns}
    missing = required_cols - df_cols_lower
    report.add(ValidationResult(
        "required_columns",
        len(missing) == 0,
        f"Missing columns: {missing}" if missing else "Base columns present",
    ))

    # Check 2: Feature columns exist
    feature_prefixes = ["rsi", "atr", "sma", "vol_spike", "return"]
    found_features = [c for c in df.columns
                      if any(c.lower().startswith(p) for p in feature_prefixes)]
    report.add(ValidationResult(
        "feature_columns_exist",
        len(found_features) >= 5,
        f"Found {len(found_features)} feature columns" +
        (f" (need >= 5)" if len(found_features) < 5 else ""),
        {"feature_columns": found_features}
    ))

    # Check 3: No duplicate ticker/date
    df_lower = df.rename(columns={c: c.lower() for c in df.columns})
    dupes = df_lower.duplicated(subset=["ticker", "date"]).sum()
    report.add(ValidationResult(
        "no_duplicate_ticker_date",
        dupes == 0,
        f"{dupes} duplicate ticker/date rows" if dupes > 0 else "No duplicates",
    ))

    # Check 4: Enough lookback rows per ticker
    df_lower = df.rename(columns={c: c.lower() for c in df.columns})
    rows_per_ticker = df_lower.groupby("ticker").size()
    insufficient = rows_per_ticker[rows_per_ticker < min_lookback]
    report.add(ValidationResult(
        "sufficient_lookback",
        len(insufficient) == 0,
        f"{len(insufficient)} tickers have < {min_lookback} rows"
        if len(insufficient) > 0
        else f"All tickers have >= {min_lookback} rows",
        {"insufficient_tickers": list(insufficient.index) if len(insufficient) > 0 else []}
    ))

    # Check 5: No negative volume
    if "volume" in df_cols_lower:
        vol_col = [c for c in df.columns if c.lower() == "volume"][0]
        neg_vol = (df[vol_col] < 0).sum()
        report.add(ValidationResult(
            "no_negative_volume",
            neg_vol == 0,
            f"{neg_vol} rows have negative volume" if neg_vol > 0
            else "No negative volumes",
        ))

    return report


# ═══════════════════════════════════════════════════════════
# Gold-layer checks
# ═══════════════════════════════════════════════════════════

def validate_gold_predictions(df: pd.DataFrame) -> ValidationReport:
    """Validate prediction output from the Gold layer."""
    report = ValidationReport("gold/predictions")

    # Check 1: Required columns
    required_cols = {"ticker", "predicted_probability", "rank", "as_of_date"}
    df_cols_lower = {c.lower() for c in df.columns}
    missing = required_cols - df_cols_lower
    report.add(ValidationResult(
        "required_columns",
        len(missing) == 0,
        f"Missing columns: {missing}" if missing else "All required columns present",
    ))

    if missing:
        return report

    # Normalize column names
    df = df.rename(columns={c: c.lower() for c in df.columns})

    # Check 2: No duplicate ranks per day
    if "as_of_date" in df.columns and "rank" in df.columns:
        dup_ranks = df.groupby("as_of_date")["rank"].apply(
            lambda x: x.duplicated().sum()
        ).sum()
        report.add(ValidationResult(
            "no_duplicate_ranks",
            dup_ranks == 0,
            f"{dup_ranks} duplicate ranks found" if dup_ranks > 0
            else "No duplicate ranks per day",
        ))

    # Check 3: Probabilities in [0, 1]
    if "predicted_probability" in df.columns:
        oob = ((df["predicted_probability"] < 0) |
               (df["predicted_probability"] > 1)).sum()
        report.add(ValidationResult(
            "probability_range",
            oob == 0,
            f"{oob} probabilities outside [0,1]" if oob > 0
            else "All probabilities in valid range",
        ))

    # Check 4: Has expected number of picks
    if "as_of_date" in df.columns:
        picks_per_day = df.groupby("as_of_date").size()
        has_five = (picks_per_day >= 5).all()
        report.add(ValidationResult(
            "top_k_picks",
            has_five,
            f"Some days have < 5 picks" if not has_five
            else "All days have >= 5 picks",
            {"picks_per_day": picks_per_day.to_dict()}
        ))

    return report


def validate_gold_metrics(df: pd.DataFrame) -> ValidationReport:
    """Validate model metrics from the Gold layer."""
    report = ValidationReport("gold/model_metrics")

    # Check 1: Required columns
    required_cols = {"as_of_date"}
    metric_cols = {"precision_at_5", "hit_rate"}
    df_cols_lower = {c.lower() for c in df.columns}
    missing_req = required_cols - df_cols_lower
    missing_metrics = metric_cols - df_cols_lower

    report.add(ValidationResult(
        "required_columns",
        len(missing_req) == 0,
        f"Missing columns: {missing_req}" if missing_req
        else "Required columns present",
    ))

    report.add(ValidationResult(
        "metric_columns",
        len(missing_metrics) == 0,
        f"Missing metric columns: {missing_metrics}" if missing_metrics
        else "Metric columns present",
    ))

    # Check 2: Metrics in valid ranges
    df = df.rename(columns={c: c.lower() for c in df.columns})
    for col in metric_cols & df_cols_lower:
        oob = ((df[col] < 0) | (df[col] > 1)).sum()
        report.add(ValidationResult(
            f"{col}_range",
            oob == 0,
            f"{oob} values outside [0,1] in {col}" if oob > 0
            else f"{col} values in valid range",
        ))

    return report
