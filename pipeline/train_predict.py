"""
pipeline/train_predict.py — Gold layer: ML training, prediction & backtesting

Trains a Logistic Regression model on historical feature data,
scores all tickers for the most recent date, selects the Top 5
picks, and evaluates model performance via backtesting.

ML Pipeline: SimpleImputer → StandardScaler → LogisticRegression
"""

import pandas as pd
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

from pipeline.config import (
    setup_logger, get_model_config, lake_path, get_mode
)
from pipeline.utils import (
    write_parquet, write_csv, read_parquet, get_today_str
)

logger = setup_logger("pipeline.train_predict")


# ── Feature column definitions ─────────────────────────────

FEATURE_COLUMNS = [
    "vol_spike_ratio",
    "atr_pct",
    "volatility_20d",
    "rsi_14d",
    "price_vs_sma5",
    "price_vs_sma20",
    "price_vs_sma50",
    "return_1d",
    "return_3d",
    "return_5d",
    "gap",
    "intraday_range_pct",
    "daily_return",
]

META_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "volume",
                "name", "sector", "industry", "sector_rank"]


def build_ml_pipeline(max_iter: int = 1000,
                      random_state: int = 42) -> Pipeline:
    """
    Build the sklearn Pipeline: Impute → Scale → Classify.

    Returns:
        sklearn Pipeline ready for .fit() and .predict_proba().
    """
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(
            max_iter=max_iter,
            random_state=random_state,
            solver="lbfgs",
            class_weight="balanced",  # handle class imbalance
        ))
    ])


def prepare_data(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Prepare the feature matrix, selecting only available feature columns.
    Computes atr_pct dynamically if not already present.

    Returns:
        Tuple of (DataFrame with only feature columns, list of used feature names).
    """
    data = df.copy()
    if "atr_pct" not in data.columns and "atr_14d" in data.columns and "close" in data.columns:
        data["atr_pct"] = data["atr_14d"] / data["close"].replace(0, np.nan)

    available_features = [c for c in FEATURE_COLUMNS if c in data.columns]
    if len(available_features) < 5:
        logger.warning(f"Only {len(available_features)} feature columns found")

    return data[available_features], available_features


def select_sector_diversified_top_k(
    df: pd.DataFrame,
    top_k: int = 5,
    allocations: dict[str, int] = None,
) -> pd.DataFrame:
    """
    Select Top K picks ensuring representation across key target sectors:
    Technology, Healthcare, and Gaming / Communication Services.

    Default allocation for top_k=5:
      - Technology: 2
      - Healthcare: 2
      - Communication Services (Gaming): 1

    Fallback: If any sector has fewer stocks available, fills
    remaining slots with next-highest probability stocks overall.
    """
    if allocations is None:
        allocations = {
            "Technology": 2,
            "Healthcare": 2,
            "Communication Services": 1,
        }

    if df.empty:
        return df

    picks = []
    chosen_tickers = set()

    for sector, quota in allocations.items():
        if "sector" in df.columns:
            sec_df = df[
                (df["sector"] == sector) & (~df["ticker"].isin(chosen_tickers))
            ].sort_values("predicted_probability", ascending=False)
        else:
            sec_df = pd.DataFrame()

        for _, row in sec_df.head(quota).iterrows():
            picks.append(row)
            chosen_tickers.add(row["ticker"])

    # Fallback to fill up to top_k
    if len(picks) < top_k:
        remaining = df[~df["ticker"].isin(chosen_tickers)].sort_values(
            "predicted_probability", ascending=False
        )
        for _, row in remaining.head(top_k - len(picks)).iterrows():
            picks.append(row)
            chosen_tickers.add(row["ticker"])

    result = pd.DataFrame(picks).sort_values(
        "predicted_probability", ascending=False
    ).reset_index(drop=True)
    result["rank"] = range(1, len(result) + 1)
    return result


def train_and_predict(df: pd.DataFrame, prediction_date: str) -> tuple[pd.DataFrame, pd.DataFrame, Pipeline]:
    """
    Train on historical data, predict on the target date.

    Args:
        df: Full feature DataFrame with 'date' and 'target' columns.
        prediction_date: The date to generate predictions for.

    Returns:
        Tuple of (all predictions DataFrame, top_picks DataFrame, fitted Pipeline).
    """
    model_cfg = get_model_config()
    top_k = model_cfg.get("top_k", 5)

    # Split: train on everything before prediction_date
    train_df = df[(df["date"] < prediction_date) & (df["target"].notna())].copy()
    predict_df = df[df["date"] == prediction_date].copy()

    if train_df.empty:
        logger.error("No training data available!")
        return pd.DataFrame(), pd.DataFrame(), None

    if predict_df.empty:
        # Fall back to the most recent date with data
        latest_date = df["date"].max()
        logger.warning(f"No data for {prediction_date}, using {latest_date}")
        predict_df = df[df["date"] == latest_date].copy()
        train_df = df[(df["date"] < latest_date) & (df["target"].notna())].copy()
        prediction_date = latest_date

    logger.info(f"Training data: {len(train_df):,} rows | "
                f"Prediction date: {prediction_date} ({len(predict_df)} tickers)")

    # Prepare features
    X_train, feature_names = prepare_data(train_df)
    y_train = train_df["target"].astype(int)
    X_pred, _ = prepare_data(predict_df)

    # Check class balance
    pos_rate = y_train.mean()
    logger.info(f"Target distribution: {pos_rate:.1%} positive "
                f"({y_train.sum():.0f}/{len(y_train)})")

    # Build and fit the model
    pipeline = build_ml_pipeline(
        max_iter=model_cfg.get("max_iter", 1000),
        random_state=model_cfg.get("random_state", 42),
    )
    pipeline.fit(X_train, y_train)
    logger.info("Model trained successfully")

    # Predict probabilities
    try:
        probs = pipeline.predict_proba(X_pred)[:, 1]  # P(target=1)
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        return pd.DataFrame(), pd.DataFrame(), pipeline

    # Build predictions DataFrame
    predictions = predict_df[
        [c for c in META_COLUMNS if c in predict_df.columns and c != "sector_rank"]
    ].copy()
    predictions["predicted_probability"] = probs
    predictions["as_of_date"] = prediction_date

    # Rank by probability (descending)
    predictions = predictions.sort_values(
        "predicted_probability", ascending=False
    ).reset_index(drop=True)
    predictions["rank"] = range(1, len(predictions) + 1)

    # Sector ranking
    if "sector" in predictions.columns:
        predictions["sector_rank"] = (
            predictions.groupby("sector")["predicted_probability"]
            .rank(ascending=False, method="first")
            .astype(int)
        )
    else:
        predictions["sector_rank"] = predictions["rank"]

    # Add last close
    if "close" in predictions.columns:
        predictions["last_close"] = predictions["close"]

    # Add top contributing features for the top picks
    predictions["top_features"] = _get_top_features(
        pipeline, feature_names, X_pred, predictions.index
    )

    # Select sector-diversified top K (Tech, Healthcare, Gaming)
    top_picks = select_sector_diversified_top_k(predictions, top_k)
    top_tickers = set(top_picks["ticker"])
    remaining = predictions[~predictions["ticker"].isin(top_tickers)].sort_values(
        "predicted_probability", ascending=False
    ).reset_index(drop=True)

    # Order predictions so top picks are ranks 1..top_k, followed by remaining
    ordered_predictions = pd.concat([top_picks, remaining], ignore_index=True)
    ordered_predictions["rank"] = range(1, len(ordered_predictions) + 1)

    logger.info(f"\n{'='*60}")
    logger.info(f"  TOP {top_k} PICKS for {prediction_date} (Sector-Diversified)")
    logger.info(f"{'='*60}")
    for _, row in top_picks.iterrows():
        ticker = row.get("ticker", "???")
        prob = row.get("predicted_probability", 0)
        sector = row.get("sector", "N/A")
        close = row.get("last_close", 0)
        s_rank = row.get("sector_rank", 1)
        logger.info(f"  #{int(row['rank'])} {ticker:6s} | "
                     f"P={prob:.3f} | ${close:.2f} | {sector} (Sector #{s_rank})")
    logger.info(f"{'='*60}\n")

    return ordered_predictions, top_picks, pipeline


def _get_top_features(pipeline: Pipeline, feature_names: list[str],
                      X: pd.DataFrame, indices: pd.Index) -> list[str]:
    """
    Get the most important features for each prediction.

    Uses the model's coefficients to identify which features
    contribute most to each prediction.
    """
    try:
        classifier = pipeline.named_steps["classifier"]
        scaler = pipeline.named_steps["scaler"]
        imputer = pipeline.named_steps["imputer"]

        coefficients = classifier.coef_[0]

        # Get feature importance ranking
        importance = sorted(
            zip(feature_names, coefficients),
            key=lambda x: abs(x[1]),
            reverse=True
        )
        top_3 = [f"{name} ({coef:+.3f})" for name, coef in importance[:3]]
        top_str = "; ".join(top_3)

        return [top_str] * len(indices)
    except Exception:
        return ["N/A"] * len(indices)


# ═══════════════════════════════════════════════════════════
# Backtesting
# ═══════════════════════════════════════════════════════════

def run_backtest(df: pd.DataFrame, top_k: int = 5,
                 test_days: int = 30) -> pd.DataFrame:
    """
    Walk-forward backtest: for each of the last N trading days,
    train on prior data and evaluate predictions.

    Metrics:
    - precision@K: fraction of top K picks that actually hit target
    - hit_rate: fraction of days where at least 1 of top K hit

    Returns:
        DataFrame with daily metrics.
    """
    logger.info(f"Running backtest: last {test_days} days, top_k={top_k}")

    dates = sorted(df["date"].unique())
    if len(dates) <= test_days:
        test_dates = dates[10:]  # need at least 10 days for training
    else:
        test_dates = dates[-test_days:]

    model_cfg = get_model_config()
    metrics_records = []

    for i, test_date in enumerate(test_dates):
        train_data = df[(df["date"] < test_date) & (df["target"].notna())]
        test_data = df[df["date"] == test_date]

        if len(train_data) < 50 or len(test_data) == 0:
            continue

        try:
            X_train, feature_names = prepare_data(train_data)
            y_train = train_data["target"].astype(int)
            X_test, _ = prepare_data(test_data)
            y_test = test_data["target"] if "target" in test_data.columns else None

            pipeline = build_ml_pipeline(
                max_iter=model_cfg.get("max_iter", 1000),
                random_state=model_cfg.get("random_state", 42),
            )
            pipeline.fit(X_train, y_train)
            probs = pipeline.predict_proba(X_test)[:, 1]

            # Select sector-diversified top K picks for evaluation
            test_data_eval = test_data.copy()
            test_data_eval["predicted_probability"] = probs
            top_k_picks = select_sector_diversified_top_k(test_data_eval, top_k)

            # Calculate precision@K
            if "target" in top_k_picks.columns and not top_k_picks["target"].isna().all():
                top_k_actual = top_k_picks["target"].dropna().values
                if len(top_k_actual) > 0:
                    precision_at_k = top_k_actual.mean()
                    hit = float(int(top_k_actual.sum() > 0))
                else:
                    precision_at_k = np.nan
                    hit = np.nan
            else:
                precision_at_k = np.nan
                hit = np.nan

            metrics_records.append({
                "as_of_date": str(test_date),
                "precision_at_5": float(precision_at_k) if not np.isnan(precision_at_k) else np.nan,
                "hit_rate": float(hit) if not np.isnan(hit) else np.nan,
                "num_tickers_scored": int(len(test_data)),
                "positive_rate": float(y_train.mean()) if len(y_train) > 0 else 0.0,
            })

        except Exception as e:
            logger.debug(f"Backtest failed for {test_date}: {e}")

    if not metrics_records:
        logger.warning("No backtest results generated")
        return pd.DataFrame()

    metrics_df = pd.DataFrame(metrics_records)

    # Compute aggregate stats
    avg_precision = metrics_df["precision_at_5"].mean()
    avg_hit_rate = metrics_df["hit_rate"].mean()
    logger.info(f"Backtest results over {len(metrics_df)} days:")
    logger.info(f"  Average precision@{top_k}: {avg_precision:.3f}")
    logger.info(f"  Average hit rate: {avg_hit_rate:.3f}")

    return metrics_df


# ═══════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════

def run_train_predict(target_date: str = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Main entry point: train model, generate predictions, run
    backtest, and write results to Gold layer.

    Args:
        target_date: Date string for partition (default: today).

    Returns:
        Tuple of (predictions DataFrame, metrics DataFrame).
    """
    if target_date is None:
        target_date = get_today_str()

    model_cfg = get_model_config()
    top_k = model_cfg.get("top_k", 5)
    test_days = model_cfg.get("test_days", 30)

    # ── Read Silver layer features ─────────────────────────
    features_path = lake_path("silver", "features", target_date)
    try:
        features_df = read_parquet(features_path)
    except FileNotFoundError:
        logger.error(f"No feature data found at {features_path}")
        return pd.DataFrame(), pd.DataFrame()

    logger.info(f"Loaded {len(features_df):,} feature rows, "
                f"{features_df['ticker'].nunique()} tickers")

    # ── Determine prediction date ──────────────────────────
    # Use the most recent date in the feature data
    all_dates = sorted(features_df["date"].unique())
    prediction_date = all_dates[-1]
    logger.info(f"Prediction target date: {prediction_date}")

    # ── Train and predict ──────────────────────────────────
    predictions, top_picks, pipeline = train_and_predict(features_df, prediction_date)

    if predictions.empty or top_picks.empty:
        logger.error("No predictions generated!")
        return pd.DataFrame(), pd.DataFrame()

    # ── Run backtest ───────────────────────────────────────
    metrics_df = run_backtest(features_df, top_k=top_k, test_days=test_days)

    # ── Write to Gold layer ────────────────────────────────
    # Predictions — Top K only (Sector-Diversified)
    top_predictions = top_picks

    pred_path = lake_path("gold", "predictions", target_date)
    write_parquet(top_predictions, pred_path)

    # All scored tickers — stored in a separate dataset so Athena
    # only reads top-5 from gold/predictions/
    all_pred_path = lake_path("gold", "all_predictions", target_date)
    write_parquet(predictions, all_pred_path)

    # Metrics
    if not metrics_df.empty:
        metrics_path = lake_path("gold", "model_metrics", target_date)
        write_parquet(metrics_df, metrics_path)

    # CSV copies — in AWS mode, write to a separate gold_csv/ prefix
    # so Athena doesn't try to read CSVs as Parquet
    if get_mode() == "aws":
        csv_pred_path = lake_path("gold_csv", "predictions", target_date)
        csv_all_path = lake_path("gold_csv", "all_predictions", target_date)
        csv_metrics_path = lake_path("gold_csv", "model_metrics", target_date)
    else:
        csv_pred_path = pred_path
        csv_all_path = all_pred_path
        csv_metrics_path = lake_path("gold", "model_metrics", target_date)

    write_csv(top_predictions, csv_pred_path)
    write_csv(predictions, csv_all_path, filename="all_predictions.csv")
    if not metrics_df.empty:
        write_csv(metrics_df, csv_metrics_path)

    logger.info(f"✅ Gold layer complete: {len(top_predictions)} top picks, "
                f"{len(metrics_df)} backtest days → dt={target_date}")

    return predictions, metrics_df


if __name__ == "__main__":
    run_train_predict()
