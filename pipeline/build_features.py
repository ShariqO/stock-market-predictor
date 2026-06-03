"""
pipeline/build_features.py — Silver layer: Feature engineering

Reads Bronze layer prices + tickers, joins them, and engineers
technical features per ticker. Outputs a feature matrix to the
Silver layer for ML consumption.

Features engineered:
  - Volume: 5d/20d rolling avg, volume spike ratio
  - Volatility: 14-day ATR, 20d rolling std of returns
  - RSI: 14-period Relative Strength Index
  - Moving Averages: 5d, 10d, 20d, 50d SMA; price vs SMA ratios
  - Returns: 1d, 3d, 5d returns
  - Gap: overnight gap (open vs prev close)
  - Target: binary label for >= $1 intraday move (open → high)
"""

import pandas as pd
import numpy as np

from pipeline.config import (
    setup_logger, get_features_config, get_model_config, lake_path
)
from pipeline.utils import write_parquet, read_parquet, get_today_str

logger = setup_logger("pipeline.build_features")


# ═══════════════════════════════════════════════════════════
# Feature computation functions
# ═══════════════════════════════════════════════════════════

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Compute Relative Strength Index (RSI).

    RSI = 100 - (100 / (1 + RS))
    where RS = avg_gain / avg_loss over the period.
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_atr(high: pd.Series, low: pd.Series,
                close: pd.Series, period: int = 14) -> pd.Series:
    """
    Compute Average True Range (ATR).

    True Range = max(H-L, |H-prevC|, |L-prevC|)
    ATR = rolling mean of True Range.
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean()


def engineer_features_for_ticker(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all technical features for a single ticker's time series.

    Args:
        df: DataFrame with columns [date, open, high, low, close, volume]
            sorted by date ascending.

    Returns:
        DataFrame with all original columns plus feature columns.
    """
    cfg = get_features_config()
    model_cfg = get_model_config()
    windows = cfg.get("rolling_windows", {})
    rsi_period = cfg.get("rsi_period", 14)
    atr_period = cfg.get("atr_period", 14)

    short = windows.get("short", 5)
    medium = windows.get("medium", 10)
    long = windows.get("long", 20)
    extra_long = windows.get("extra_long", 50)

    df = df.copy().sort_values("date").reset_index(drop=True)

    # ── Volume features ────────────────────────────────────
    df["vol_avg_5d"] = df["volume"].rolling(short, min_periods=short).mean()
    df["vol_avg_20d"] = df["volume"].rolling(long, min_periods=long).mean()
    df["vol_spike_ratio"] = df["volume"] / df["vol_avg_20d"].replace(0, np.nan)

    # ── Volatility features ────────────────────────────────
    df["atr_14d"] = compute_atr(df["high"], df["low"], df["close"], atr_period)
    df["daily_return"] = df["close"].pct_change()
    df["volatility_20d"] = df["daily_return"].rolling(long, min_periods=long).std()

    # ── RSI ────────────────────────────────────────────────
    df["rsi_14d"] = compute_rsi(df["close"], rsi_period)

    # ── Moving averages ────────────────────────────────────
    df["sma_5d"] = df["close"].rolling(short, min_periods=short).mean()
    df["sma_10d"] = df["close"].rolling(medium, min_periods=medium).mean()
    df["sma_20d"] = df["close"].rolling(long, min_periods=long).mean()
    df["sma_50d"] = df["close"].rolling(extra_long, min_periods=extra_long).mean()

    # Price vs SMA ratios (how far price is from each MA)
    df["price_vs_sma5"] = df["close"] / df["sma_5d"].replace(0, np.nan) - 1
    df["price_vs_sma20"] = df["close"] / df["sma_20d"].replace(0, np.nan) - 1
    df["price_vs_sma50"] = df["close"] / df["sma_50d"].replace(0, np.nan) - 1

    # ── Returns ────────────────────────────────────────────
    df["return_1d"] = df["close"].pct_change(1)
    df["return_3d"] = df["close"].pct_change(3)
    df["return_5d"] = df["close"].pct_change(short)

    # ── Gap feature (overnight gap) ────────────────────────
    df["gap"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1).replace(0, np.nan)

    # ── Intraday range ─────────────────────────────────────
    df["intraday_range"] = df["high"] - df["low"]
    df["intraday_range_pct"] = df["intraday_range"] / df["open"].replace(0, np.nan)

    # ── Target label ───────────────────────────────────────
    # Whether the NEXT day has a >= $target_move intraday move (open → high)
    target_move = model_cfg.get("target_move_dollars", 1.0)
    next_day_move = df["high"].shift(-1) - df["open"].shift(-1)
    df["target"] = (next_day_move >= target_move).astype(int)

    # The target for the last row is NaN (no next day data)
    df.loc[df.index[-1], "target"] = np.nan

    return df


# ═══════════════════════════════════════════════════════════
# Main pipeline function
# ═══════════════════════════════════════════════════════════

def run_build_features(target_date: str = None) -> pd.DataFrame:
    """
    Main entry point: read Bronze data, engineer features, write
    to Silver layer.

    Args:
        target_date: Date string for partition (default: today).

    Returns:
        Feature-engineered DataFrame.
    """
    if target_date is None:
        target_date = get_today_str()

    cfg = get_features_config()
    min_lookback = cfg.get("min_lookback_rows", 60)

    # ── Read Bronze layer data ─────────────────────────────
    logger.info("Reading Bronze layer data...")

    prices_path = lake_path("bronze", "prices", target_date)
    tickers_path = lake_path("bronze", "tickers", target_date)

    try:
        prices_df = read_parquet(prices_path)
    except FileNotFoundError:
        logger.error(f"No price data found at {prices_path}")
        return pd.DataFrame()

    try:
        tickers_df = read_parquet(tickers_path)
    except FileNotFoundError:
        logger.warning("No ticker metadata found — proceeding with all tickers")
        tickers_df = pd.DataFrame()

    logger.info(f"Loaded {len(prices_df):,} price rows, "
                f"{prices_df['ticker'].nunique()} tickers")

    # ── Filter to valid universe ───────────────────────────
    if not tickers_df.empty and "ticker" in tickers_df.columns:
        valid_tickers = set(tickers_df["ticker"].unique())
        prices_df = prices_df[prices_df["ticker"].isin(valid_tickers)]
        logger.info(f"After universe filter: {prices_df['ticker'].nunique()} tickers")

    # ── Engineer features per ticker ───────────────────────
    logger.info("Engineering features per ticker...")
    all_features = []
    skipped = 0

    ticker_groups = prices_df.groupby("ticker")
    for ticker, group in ticker_groups:
        # Check minimum lookback
        if len(group) < min_lookback:
            logger.debug(f"Skipping {ticker}: only {len(group)} rows "
                         f"(need {min_lookback})")
            skipped += 1
            continue

        try:
            features = engineer_features_for_ticker(group)
            # Drop rows where features are NaN due to lookback requirements
            # Keep only rows where core features are computed
            features = features.dropna(
                subset=["rsi_14d", "atr_14d", "sma_20d", "vol_avg_20d"]
            )

            if len(features) > 0:
                all_features.append(features)
        except Exception as e:
            logger.warning(f"Feature engineering failed for {ticker}: {e}")
            skipped += 1

    if not all_features:
        logger.error("No features generated for any ticker!")
        return pd.DataFrame()

    result = pd.concat(all_features, ignore_index=True)

    # ── Add ticker metadata columns ────────────────────────
    if not tickers_df.empty:
        meta_cols = ["ticker", "name", "sector", "industry"]
        available_meta_cols = [c for c in meta_cols if c in tickers_df.columns]
        if available_meta_cols:
            result = result.merge(
                tickers_df[available_meta_cols],
                on="ticker",
                how="left"
            )

    logger.info(f"Feature engineering complete: {len(result):,} rows, "
                f"{result['ticker'].nunique()} tickers "
                f"({skipped} skipped for insufficient data)")

    # ── Write to Silver layer ──────────────────────────────
    out_path = lake_path("silver", "features", target_date)
    write_parquet(result, out_path)

    # Log feature summary
    feature_cols = [c for c in result.columns
                    if c not in ["ticker", "date", "open", "high", "low",
                                 "close", "volume", "name", "sector",
                                 "industry", "target"]]
    logger.info(f"✅ Silver/features complete: {len(feature_cols)} features, "
                f"{len(result):,} rows → dt={target_date}")

    return result


if __name__ == "__main__":
    run_build_features()
