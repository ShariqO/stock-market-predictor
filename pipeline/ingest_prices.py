"""
pipeline/ingest_prices.py — Bronze layer: OHLCV data ingestion

Downloads historical stock price data from yfinance for the
filtered ticker universe. Writes raw OHLCV data to the Bronze
layer of the local data lake.
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from pipeline.config import (
    setup_logger, get_ingestion_config, lake_path, get_lake_root
)
from pipeline.utils import write_parquet, get_today_str

logger = setup_logger("pipeline.ingest_prices")


def get_ticker_universe() -> list[str]:
    """
    Return a curated list of NASDAQ tickers across Technology,
    Healthcare, and Gaming/Interactive Entertainment sectors.

    Uses a hand-curated list of well-known NASDAQ tickers plus
    supplementary tickers to ensure broad sector coverage.
    """
    # ── NASDAQ-100 core Technology tickers ──────────────────
    tech_tickers = [
        "AAPL", "MSFT", "NVDA", "AVGO", "ADBE", "CRM", "CSCO", "INTC",
        "AMD", "QCOM", "TXN", "INTU", "AMAT", "MU", "LRCX", "ADI",
        "KLAC", "SNPS", "CDNS", "MRVL", "FTNT", "PANW", "CRWD", "ZS",
        "NET", "DDOG", "SNOW", "MDB", "TEAM", "WDAY", "VEEV", "ANSS",
        "CPRT", "FICO", "MPWR", "ON", "NXPI", "MCHP", "SWKS", "QRVO",
        "AKAM", "FFIV", "JNPR", "NTAP", "WDC", "STX", "HPQ", "DELL",
        "SMCI", "ARM", "PLTR", "IONQ", "RGTI", "QUBT", "SOUN",
        "APP", "RKLB", "GRAB", "SE", "SHOP", "SQ", "MELI", "BKNG",
        "ABNB", "UBER", "LYFT", "DASH", "PINS", "SNAP", "SPOT",
        "TTD", "ROKU", "ZM", "DOCU", "OKTA", "TWLO",
        "HUBS", "PAYC", "PCTY", "BILL", "FOUR", "GPN",
        "MANH", "MNDY", "ESTC", "CFLT", "PATH", "GTLB",
        "DUOL", "TOST", "CWAN", "YOU", "FROG",
    ]

    # ── Healthcare tickers ─────────────────────────────────
    healthcare_tickers = [
        "AMGN", "GILD", "VRTX", "REGN", "ILMN", "BIIB", "MRNA", "DXCM",
        "ISRG", "IDXX", "ALGN", "HOLX", "TECH", "BIO", "SGEN",
        "BMRN", "ALNY", "INCY", "SRRK", "NBIX", "EXAS", "NTRA",
        "RARE", "IONS", "SRPT", "PCVX", "RCKT", "CYTK",
        "ARVN", "KRYS", "VERA", "DAWN", "AXSM", "CRNX",
        "HALO", "MYGN", "NVCR", "CORT", "PRCT", "LUNG",
        "RVMD", "INSM", "ACLX", "TGTX", "PTCT", "APLS",
        "MDGL", "KRTX", "CPRX", "FOLD",
    ]

    # ── Gaming / Interactive Entertainment tickers ─────────
    gaming_tickers = [
        "EA", "TTWO", "RBLX", "NFLX", "ROKU", "ZNGA",
        "SKLZ", "DKNG", "PENN", "RSI", "GENI",
        "PLTK", "MYPS", "DDI", "GRVY", "BILI",
        "SOHU", "HUYA", "DOYU",
    ]

    # Combine and deduplicate
    all_tickers = list(dict.fromkeys(
        tech_tickers + healthcare_tickers + gaming_tickers
    ))

    logger.info(f"Ticker universe: {len(all_tickers)} tickers")
    return all_tickers


def download_prices(
    tickers: list[str],
    lookback_days: int = 180,
    batch_size: int = 50,
    retry_attempts: int = 3,
    retry_delay: int = 5,
) -> pd.DataFrame:
    """
    Download OHLCV data for a list of tickers using yfinance.

    Downloads in batches to avoid API rate limiting. Retries
    failed batches.

    Args:
        tickers: List of ticker symbols.
        lookback_days: Calendar days of history to download.
        batch_size: Number of tickers per API call.
        retry_attempts: Number of retries on failure.
        retry_delay: Seconds between retries.

    Returns:
        DataFrame with columns: ticker, date, open, high, low, close, volume
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)

    logger.info(
        f"Downloading prices for {len(tickers)} tickers | "
        f"{start_date.date()} → {end_date.date()} | "
        f"batch_size={batch_size}"
    )

    all_frames = []
    failed_tickers = []

    # Process in batches
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(tickers) + batch_size - 1) // batch_size

        logger.info(f"Batch {batch_num}/{total_batches}: {len(batch)} tickers")

        for attempt in range(1, retry_attempts + 1):
            try:
                data = yf.download(
                    tickers=batch,
                    start=start_date.strftime("%Y-%m-%d"),
                    end=end_date.strftime("%Y-%m-%d"),
                    group_by="ticker",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                )

                if data.empty:
                    logger.warning(f"Batch {batch_num}: empty response")
                    break

                # Parse the multi-level column format from yfinance
                frames = _parse_yf_response(data, batch)
                all_frames.extend(frames)
                break  # Success — exit retry loop

            except Exception as e:
                logger.warning(
                    f"Batch {batch_num} attempt {attempt}/{retry_attempts} "
                    f"failed: {e}"
                )
                if attempt < retry_attempts:
                    time.sleep(retry_delay)
                else:
                    failed_tickers.extend(batch)
                    logger.error(f"Batch {batch_num}: all retries exhausted")

        # Brief pause between batches to be polite to the API
        if i + batch_size < len(tickers):
            time.sleep(1)

    if failed_tickers:
        logger.warning(f"Failed to download {len(failed_tickers)} tickers: "
                       f"{failed_tickers[:20]}...")

    if not all_frames:
        logger.error("No data downloaded at all!")
        return pd.DataFrame()

    result = pd.concat(all_frames, ignore_index=True)
    logger.info(f"Downloaded {len(result):,} total price rows for "
                f"{result['ticker'].nunique()} tickers")
    return result


def _parse_yf_response(data: pd.DataFrame, tickers: list[str]) -> list[pd.DataFrame]:
    """
    Parse yfinance multi-ticker response into a flat DataFrame.

    Handles both single-ticker (flat columns) and multi-ticker
    (multi-level columns) response formats.
    """
    frames = []

    if len(tickers) == 1:
        # Single ticker — flat columns
        ticker = tickers[0]
        df = data.reset_index()
        df.columns = [c.lower() if isinstance(c, str) else str(c).lower()
                      for c in df.columns]
        df["ticker"] = ticker
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            frames.append(df[["ticker", "date", "open", "high", "low", "close", "volume"]])
    else:
        # Multi-ticker — multi-level columns
        for ticker in tickers:
            try:
                if ticker in data.columns.get_level_values(0):
                    ticker_data = data[ticker].copy()
                elif ticker.upper() in data.columns.get_level_values(0):
                    ticker_data = data[ticker.upper()].copy()
                else:
                    continue

                ticker_data = ticker_data.reset_index()
                ticker_data.columns = [c.lower() if isinstance(c, str)
                                       else str(c).lower()
                                       for c in ticker_data.columns]
                ticker_data["ticker"] = ticker

                # Check required columns exist
                required = {"date", "open", "high", "low", "close", "volume"}
                if not required.issubset(set(ticker_data.columns)):
                    continue

                # Drop rows where all OHLCV are NaN
                ohlcv = ["open", "high", "low", "close", "volume"]
                ticker_data = ticker_data.dropna(subset=ohlcv, how="all")

                if len(ticker_data) == 0:
                    continue

                ticker_data["date"] = pd.to_datetime(
                    ticker_data["date"]
                ).dt.strftime("%Y-%m-%d")
                frames.append(
                    ticker_data[["ticker", "date", "open", "high", "low",
                                 "close", "volume"]]
                )
            except Exception as e:
                logger.debug(f"Could not parse {ticker}: {e}")

    return frames


def run_ingest(target_date: str = None) -> pd.DataFrame:
    """
    Main entry point: download prices and write to Bronze layer.

    Args:
        target_date: Date string for partition (default: today).

    Returns:
        The ingested DataFrame.
    """
    if target_date is None:
        target_date = get_today_str()

    cfg = get_ingestion_config()

    # Get ticker universe
    tickers = get_ticker_universe()

    # Download
    df = download_prices(
        tickers=tickers,
        lookback_days=cfg.get("lookback_days", 180),
        batch_size=cfg.get("batch_size", 50),
        retry_attempts=cfg.get("retry_attempts", 3),
        retry_delay=cfg.get("retry_delay_seconds", 5),
    )

    if df.empty:
        logger.error("No price data ingested — aborting")
        return df

    # Write to Bronze
    out_path = lake_path("bronze", "prices", target_date)
    write_parquet(df, out_path)

    logger.info(f"✅ Bronze/prices ingestion complete: {len(df):,} rows, "
                f"{df['ticker'].nunique()} tickers → dt={target_date}")

    return df


if __name__ == "__main__":
    run_ingest()
