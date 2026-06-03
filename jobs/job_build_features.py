"""
jobs/job_build_features.py — Job runner: Silver layer features

Entry point for the feature engineering step. Reads Bronze data,
engineers technical features, and validates Silver output.

Usage:
    python jobs/job_build_features.py
    docker compose run predictor python jobs/job_build_features.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import setup_logger, get_features_config
from pipeline.build_features import run_build_features
from pipeline.validate_data import validate_silver_features
from pipeline.utils import get_today_str

logger = setup_logger("jobs.build_features")


def main():
    """Run the Silver layer feature engineering pipeline."""
    target_date = get_today_str()
    logger.info(f"{'='*60}")
    logger.info(f"  JOB: Build Features — dt={target_date}")
    logger.info(f"{'='*60}")

    try:
        # Step 1: Build features
        logger.info("Step 1/2: Engineering features...")
        features_df = run_build_features(target_date)

        if features_df.empty:
            logger.error("❌ Feature engineering returned no data — aborting")
            sys.exit(1)

        # Step 2: Validate Silver data
        logger.info("Step 2/2: Validating Silver data...")
        cfg = get_features_config()
        min_lookback = cfg.get("min_lookback_rows", 60)
        report = validate_silver_features(features_df, min_lookback)
        logger.info(report.summary())

        if not report.all_passed:
            for failure in report.failures:
                logger.warning(f"  {failure}")
            logger.warning("⚠️  Some validation checks failed — "
                          "proceeding with warnings")

        logger.info(f"✅ JOB COMPLETE: Build Features")
        logger.info(f"   Features: {len(features_df):,} rows, "
                    f"{features_df['ticker'].nunique()} tickers")
        feature_cols = [c for c in features_df.columns
                       if c not in ["ticker", "date", "open", "high", "low",
                                    "close", "volume", "name", "sector",
                                    "industry", "target"]]
        logger.info(f"   Feature columns: {len(feature_cols)}")
        sys.exit(0)

    except Exception as e:
        logger.error(f"❌ JOB FAILED: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
