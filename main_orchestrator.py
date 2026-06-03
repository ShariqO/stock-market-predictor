"""
main_orchestrator.py — Full pipeline orchestrator

Runs the entire NASDAQ Day Trading Predictor pipeline end-to-end:
  1. Ingest prices → Bronze
  2. Enrich ticker metadata → Bronze
  3. Build features → Silver
  4. Train model + predict → Gold

If any step fails, logs the error and stops.

Usage:
    python main_orchestrator.py
    docker compose run predictor python main_orchestrator.py
"""

import sys
import time

from pipeline.config import setup_logger, get_mode
from pipeline.ingest_prices import run_ingest
from pipeline.enrich_tickers import run_enrich
from pipeline.build_features import run_build_features
from pipeline.train_predict import run_train_predict
from pipeline.validate_data import (
    validate_bronze_prices,
    validate_silver_features,
    validate_gold_predictions,
    validate_gold_metrics,
)
from pipeline.utils import get_today_str

logger = setup_logger("orchestrator")


def run_pipeline():
    """Execute the full data pipeline end-to-end."""
    target_date = get_today_str()
    mode = get_mode()
    start_time = time.time()

    logger.info("=" * 70)
    logger.info("  NASDAQ DAY TRADING PREDICTOR — Pipeline Run")
    logger.info(f"  Mode: {mode} | Date: {target_date}")
    logger.info("=" * 70)

    try:
        # ══════════════════════════════════════════════════
        # STEP 1: Bronze — Ingest Prices
        # ══════════════════════════════════════════════════
        logger.info("\n" + "─" * 50)
        logger.info("STEP 1/4: Ingesting OHLCV prices → Bronze")
        logger.info("─" * 50)

        prices_df = run_ingest(target_date)
        if prices_df.empty:
            logger.error("❌ PIPELINE ABORTED: No price data ingested")
            return False

        # Validate
        report = validate_bronze_prices(prices_df)
        logger.info(report.summary())

        # ══════════════════════════════════════════════════
        # STEP 2: Bronze — Enrich Ticker Metadata
        # ══════════════════════════════════════════════════
        logger.info("\n" + "─" * 50)
        logger.info("STEP 2/4: Enriching ticker metadata → Bronze")
        logger.info("─" * 50)

        tickers_df = run_enrich(target_date, price_df=prices_df)
        if tickers_df.empty:
            logger.warning("⚠️  No filtered tickers — proceeding with all")

        # ══════════════════════════════════════════════════
        # STEP 3: Silver — Build Features
        # ══════════════════════════════════════════════════
        logger.info("\n" + "─" * 50)
        logger.info("STEP 3/4: Engineering features → Silver")
        logger.info("─" * 50)

        features_df = run_build_features(target_date)
        if features_df.empty:
            logger.error("❌ PIPELINE ABORTED: No features generated")
            return False

        # Validate
        report = validate_silver_features(features_df)
        logger.info(report.summary())

        # ══════════════════════════════════════════════════
        # STEP 4: Gold — Train & Predict
        # ══════════════════════════════════════════════════
        logger.info("\n" + "─" * 50)
        logger.info("STEP 4/4: Training model + predictions → Gold")
        logger.info("─" * 50)

        predictions_df, metrics_df = run_train_predict(target_date)
        if predictions_df.empty:
            logger.error("❌ PIPELINE ABORTED: No predictions generated")
            return False

        # Validate
        pred_report = validate_gold_predictions(predictions_df)
        logger.info(pred_report.summary())

        if not metrics_df.empty:
            metrics_report = validate_gold_metrics(metrics_df)
            logger.info(metrics_report.summary())

        # ══════════════════════════════════════════════════
        # SUMMARY
        # ══════════════════════════════════════════════════
        elapsed = time.time() - start_time
        top_5 = predictions_df.head(5)

        logger.info("\n" + "=" * 70)
        logger.info("  PIPELINE COMPLETE")
        logger.info("=" * 70)
        logger.info(f"  Duration: {elapsed:.1f}s")
        logger.info(f"  Date: {target_date}")
        logger.info(f"  Prices: {len(prices_df):,} rows, "
                    f"{prices_df['ticker'].nunique()} tickers")
        logger.info(f"  Universe: {len(tickers_df)} filtered tickers")
        logger.info(f"  Features: {len(features_df):,} rows, "
                    f"{features_df['ticker'].nunique()} tickers")
        logger.info(f"  Predictions: {len(predictions_df)} tickers scored")

        if not metrics_df.empty:
            logger.info(f"  Backtest precision@5: "
                       f"{metrics_df['precision_at_5'].mean():.3f}")
            logger.info(f"  Backtest hit rate: "
                       f"{metrics_df['hit_rate'].mean():.3f}")

        logger.info("\n  📊 TOP 5 PICKS:")
        for _, row in top_5.iterrows():
            ticker = row.get("ticker", "???")
            prob = row.get("predicted_probability", 0)
            sector = row.get("sector", "N/A")
            close = row.get("last_close", row.get("close", 0))
            rank = int(row.get("rank", 0))
            logger.info(f"    #{rank} {ticker:6s} | P={prob:.3f} | "
                       f"${close:.2f} | {sector}")

        logger.info("=" * 70)
        return True

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ PIPELINE FAILED after {elapsed:.1f}s: {e}",
                     exc_info=True)
        return False


if __name__ == "__main__":
    success = run_pipeline()
    sys.exit(0 if success else 1)
