"""
jobs/job_predict.py — Job runner: Gold layer predictions

Entry point for the ML training, prediction, and backtesting step.
Reads Silver features, trains model, generates Top 5 picks, and
validates Gold output.

Usage:
    python jobs/job_predict.py
    docker compose run predictor python jobs/job_predict.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import setup_logger
from pipeline.train_predict import run_train_predict
from pipeline.validate_data import validate_gold_predictions, validate_gold_metrics
from pipeline.utils import get_today_str

logger = setup_logger("jobs.predict")


def main():
    """Run the Gold layer ML prediction pipeline."""
    target_date = get_today_str()
    logger.info(f"{'='*60}")
    logger.info(f"  JOB: Train & Predict — dt={target_date}")
    logger.info(f"{'='*60}")

    try:
        # Step 1: Train, predict, and backtest
        logger.info("Step 1/2: Training model and generating predictions...")
        predictions_df, metrics_df = run_train_predict(target_date)

        if predictions_df.empty:
            logger.error("❌ Prediction returned no data — aborting")
            sys.exit(1)

        # Step 2: Validate Gold data
        logger.info("Step 2/2: Validating Gold data...")

        # Validate predictions
        pred_report = validate_gold_predictions(predictions_df)
        logger.info(pred_report.summary())

        if not pred_report.all_passed:
            for failure in pred_report.failures:
                logger.warning(f"  {failure}")

        # Validate metrics
        if not metrics_df.empty:
            metrics_report = validate_gold_metrics(metrics_df)
            logger.info(metrics_report.summary())

            if not metrics_report.all_passed:
                for failure in metrics_report.failures:
                    logger.warning(f"  {failure}")

        all_passed = pred_report.all_passed and (
            metrics_df.empty or metrics_report.all_passed
        )

        if not all_passed:
            logger.warning("⚠️  Some validation checks failed — "
                          "review output carefully")

        logger.info(f"✅ JOB COMPLETE: Train & Predict")
        logger.info(f"   Predictions: {len(predictions_df)} tickers scored")
        logger.info(f"   Backtest: {len(metrics_df)} days evaluated")

        if not metrics_df.empty:
            avg_p5 = metrics_df["precision_at_5"].mean()
            avg_hr = metrics_df["hit_rate"].mean()
            logger.info(f"   Avg precision@5: {avg_p5:.3f}")
            logger.info(f"   Avg hit rate: {avg_hr:.3f}")

        sys.exit(0)

    except Exception as e:
        logger.error(f"❌ JOB FAILED: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
