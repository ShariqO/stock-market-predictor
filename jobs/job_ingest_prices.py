"""
jobs/job_ingest_prices.py — Job runner: Bronze layer ingestion

Entry point for the data ingestion step. Downloads OHLCV prices
and enriches ticker metadata. Runs Bronze-layer validation.

Usage:
    python jobs/job_ingest_prices.py
    docker compose run predictor python jobs/job_ingest_prices.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import setup_logger
from pipeline.ingest_prices import run_ingest
from pipeline.enrich_tickers import run_enrich
from pipeline.validate_data import validate_bronze_prices
from pipeline.utils import get_today_str

logger = setup_logger("jobs.ingest_prices")


def main():
    """Run the Bronze layer ingestion pipeline."""
    target_date = get_today_str()
    logger.info(f"{'='*60}")
    logger.info(f"  JOB: Ingest Prices — dt={target_date}")
    logger.info(f"{'='*60}")

    try:
        # Step 1: Ingest OHLCV prices
        logger.info("Step 1/3: Downloading OHLCV data...")
        prices_df = run_ingest(target_date)

        if prices_df.empty:
            logger.error("❌ Price ingestion returned no data — aborting")
            sys.exit(1)

        # Step 2: Enrich ticker metadata
        logger.info("Step 2/3: Enriching ticker metadata...")
        tickers_df = run_enrich(target_date, price_df=prices_df)

        if tickers_df.empty:
            logger.warning("⚠️  Ticker enrichment returned no data — "
                          "continuing with all tickers")

        # Step 3: Validate Bronze data
        logger.info("Step 3/3: Validating Bronze data...")
        report = validate_bronze_prices(prices_df)
        logger.info(report.summary())

        if not report.all_passed:
            for failure in report.failures:
                logger.warning(f"  {failure}")
            logger.warning("⚠️  Some validation checks failed — "
                          "proceeding with warnings")

        logger.info(f"✅ JOB COMPLETE: Ingest Prices")
        logger.info(f"   Prices: {len(prices_df):,} rows, "
                    f"{prices_df['ticker'].nunique()} tickers")
        logger.info(f"   Tickers: {len(tickers_df)} in filtered universe")
        sys.exit(0)

    except Exception as e:
        logger.error(f"❌ JOB FAILED: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
