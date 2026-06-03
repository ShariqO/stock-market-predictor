"""
tests/test_validate.py — Unit tests for data quality validation

Tests all validation checks in pipeline/validate_data.py using
synthetic DataFrames with known good/bad data.

Usage:
    pytest tests/test_validate.py -v
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np

from pipeline.validate_data import (
    validate_bronze_prices,
    validate_silver_features,
    validate_gold_predictions,
    validate_gold_metrics,
    ValidationResult,
    ValidationReport,
)


# ═══════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def good_bronze_df():
    """Valid Bronze OHLCV data."""
    np.random.seed(42)
    n = 100
    return pd.DataFrame({
        "ticker": ["AAPL"] * 50 + ["MSFT"] * 50,
        "date": (pd.date_range("2024-01-01", periods=50).tolist() * 2),
        "open": np.random.uniform(100, 200, n),
        "high": np.random.uniform(150, 250, n),
        "low": np.random.uniform(80, 150, n),
        "close": np.random.uniform(100, 200, n),
        "volume": np.random.randint(1000000, 50000000, n),
    })


@pytest.fixture
def bad_bronze_df():
    """Bronze data with multiple quality issues."""
    return pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "MSFT", "MSFT"],
        "date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03"],
        "open": [150.0, 150.0, None, 160.0],
        "high": [140.0, 155.0, 165.0, 170.0],  # First row: high < low
        "low": [145.0, 148.0, 158.0, 155.0],
        "close": [152.0, 152.0, 162.0, 168.0],
        "volume": [1000000, 1000000, -500, 2000000],  # Negative volume
    })


@pytest.fixture
def good_silver_df():
    """Valid Silver feature data."""
    np.random.seed(42)
    n = 200
    return pd.DataFrame({
        "ticker": ["AAPL"] * 100 + ["MSFT"] * 100,
        "date": (pd.date_range("2024-01-01", periods=100).tolist() * 2),
        "open": np.random.uniform(100, 200, n),
        "high": np.random.uniform(150, 250, n),
        "low": np.random.uniform(80, 150, n),
        "close": np.random.uniform(100, 200, n),
        "volume": np.random.randint(1000000, 50000000, n),
        "rsi_14d": np.random.uniform(20, 80, n),
        "atr_14d": np.random.uniform(1, 10, n),
        "sma_5d": np.random.uniform(100, 200, n),
        "sma_20d": np.random.uniform(100, 200, n),
        "vol_spike_ratio": np.random.uniform(0.5, 3.0, n),
        "return_1d": np.random.uniform(-0.05, 0.05, n),
    })


@pytest.fixture
def good_gold_predictions():
    """Valid Gold predictions."""
    return pd.DataFrame({
        "ticker": ["AAPL", "MSFT", "NVDA", "AMD", "GOOG"],
        "predicted_probability": [0.85, 0.78, 0.72, 0.68, 0.55],
        "rank": [1, 2, 3, 4, 5],
        "as_of_date": ["2024-01-15"] * 5,
        "sector": ["Technology"] * 5,
        "last_close": [185.0, 390.0, 550.0, 160.0, 140.0],
    })


@pytest.fixture
def good_gold_metrics():
    """Valid Gold metrics."""
    return pd.DataFrame({
        "as_of_date": ["2024-01-10", "2024-01-11", "2024-01-12"],
        "precision_at_5": [0.4, 0.6, 0.2],
        "hit_rate": [1.0, 1.0, 1.0],
    })


# ═══════════════════════════════════════════════════════════
# Tests: ValidationResult / ValidationReport
# ═══════════════════════════════════════════════════════════

class TestValidationResult:

    def test_pass_result(self):
        r = ValidationResult("test_check", True, "All good")
        assert r.passed is True
        assert "PASS" in repr(r)

    def test_fail_result(self):
        r = ValidationResult("test_check", False, "Something wrong")
        assert r.passed is False
        assert "FAIL" in repr(r)

    def test_details(self):
        r = ValidationResult("test", True, "ok", {"count": 42})
        assert r.details["count"] == 42


class TestValidationReport:

    def test_all_passed(self):
        report = ValidationReport("test")
        report.add(ValidationResult("a", True, "ok"))
        report.add(ValidationResult("b", True, "ok"))
        assert report.all_passed is True
        assert len(report.failures) == 0

    def test_has_failures(self):
        report = ValidationReport("test")
        report.add(ValidationResult("a", True, "ok"))
        report.add(ValidationResult("b", False, "bad"))
        assert report.all_passed is False
        assert len(report.failures) == 1

    def test_summary(self):
        report = ValidationReport("bronze")
        report.add(ValidationResult("a", True, "ok"))
        summary = report.summary()
        assert "BRONZE" in summary
        assert "1/1" in summary


# ═══════════════════════════════════════════════════════════
# Tests: Bronze validation
# ═══════════════════════════════════════════════════════════

class TestBronzeValidation:

    def test_good_data_passes(self, good_bronze_df):
        # Fix high >= low
        good_bronze_df["high"] = good_bronze_df[["open", "high", "low", "close"]].max(axis=1) + 1
        good_bronze_df["low"] = good_bronze_df[["open", "high", "low", "close"]].min(axis=1) - 1
        report = validate_bronze_prices(good_bronze_df)
        assert report.all_passed

    def test_missing_columns(self):
        df = pd.DataFrame({"ticker": ["AAPL"], "date": ["2024-01-01"]})
        report = validate_bronze_prices(df)
        assert not report.all_passed
        assert any("required_columns" in r.check_name for r in report.failures)

    def test_negative_volume(self, bad_bronze_df):
        report = validate_bronze_prices(bad_bronze_df)
        neg_vol = [r for r in report.results
                   if r.check_name == "no_negative_volume"]
        assert len(neg_vol) == 1
        assert not neg_vol[0].passed

    def test_duplicate_ticker_date(self, bad_bronze_df):
        report = validate_bronze_prices(bad_bronze_df)
        dupes = [r for r in report.results
                 if r.check_name == "no_duplicate_ticker_date"]
        assert len(dupes) == 1
        assert not dupes[0].passed

    def test_null_ohlc(self, bad_bronze_df):
        report = validate_bronze_prices(bad_bronze_df)
        nulls = [r for r in report.results if r.check_name == "ohlc_non_null"]
        assert len(nulls) == 1
        assert not nulls[0].passed

    def test_high_gte_low_violation(self):
        df = pd.DataFrame({
            "ticker": ["AAPL"],
            "date": ["2024-01-01"],
            "open": [150.0],
            "high": [140.0],   # < low!
            "low": [145.0],
            "close": [148.0],
            "volume": [1000000],
        })
        report = validate_bronze_prices(df)
        check = [r for r in report.results if r.check_name == "high_gte_low"]
        assert len(check) == 1
        assert not check[0].passed


# ═══════════════════════════════════════════════════════════
# Tests: Silver validation
# ═══════════════════════════════════════════════════════════

class TestSilverValidation:

    def test_good_data_passes(self, good_silver_df):
        report = validate_silver_features(good_silver_df, min_lookback=50)
        assert report.all_passed

    def test_insufficient_lookback(self):
        df = pd.DataFrame({
            "ticker": ["AAPL"] * 10,
            "date": pd.date_range("2024-01-01", periods=10),
            "open": [150.0] * 10,
            "high": [155.0] * 10,
            "low": [148.0] * 10,
            "close": [152.0] * 10,
            "volume": [1000000] * 10,
            "rsi_14d": [50.0] * 10,
            "atr_14d": [5.0] * 10,
            "sma_5d": [150.0] * 10,
            "sma_20d": [149.0] * 10,
            "vol_spike_ratio": [1.0] * 10,
            "return_1d": [0.01] * 10,
        })
        report = validate_silver_features(df, min_lookback=60)
        insufficient = [r for r in report.results
                       if r.check_name == "sufficient_lookback"]
        assert len(insufficient) == 1
        assert not insufficient[0].passed


# ═══════════════════════════════════════════════════════════
# Tests: Gold validation
# ═══════════════════════════════════════════════════════════

class TestGoldPredictionValidation:

    def test_good_predictions_pass(self, good_gold_predictions):
        report = validate_gold_predictions(good_gold_predictions)
        assert report.all_passed

    def test_duplicate_ranks(self):
        df = pd.DataFrame({
            "ticker": ["AAPL", "MSFT"],
            "predicted_probability": [0.8, 0.7],
            "rank": [1, 1],  # Duplicate!
            "as_of_date": ["2024-01-15"] * 2,
        })
        report = validate_gold_predictions(df)
        dup_ranks = [r for r in report.results
                    if r.check_name == "no_duplicate_ranks"]
        assert len(dup_ranks) == 1
        assert not dup_ranks[0].passed

    def test_probability_out_of_range(self):
        df = pd.DataFrame({
            "ticker": ["AAPL", "MSFT", "NVDA", "AMD", "GOOG"],
            "predicted_probability": [1.5, 0.8, 0.7, -0.1, 0.5],
            "rank": [1, 2, 3, 4, 5],
            "as_of_date": ["2024-01-15"] * 5,
        })
        report = validate_gold_predictions(df)
        prob = [r for r in report.results
               if r.check_name == "probability_range"]
        assert len(prob) == 1
        assert not prob[0].passed

    def test_missing_columns(self):
        df = pd.DataFrame({"ticker": ["AAPL"]})
        report = validate_gold_predictions(df)
        assert not report.all_passed


class TestGoldMetricsValidation:

    def test_good_metrics_pass(self, good_gold_metrics):
        report = validate_gold_metrics(good_gold_metrics)
        assert report.all_passed

    def test_metrics_out_of_range(self):
        df = pd.DataFrame({
            "as_of_date": ["2024-01-10"],
            "precision_at_5": [1.5],  # > 1
            "hit_rate": [0.5],
        })
        report = validate_gold_metrics(df)
        assert not report.all_passed
