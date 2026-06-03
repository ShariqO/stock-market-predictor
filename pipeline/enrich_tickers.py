"""
pipeline/enrich_tickers.py — Bronze layer: Ticker metadata enrichment

Fetches sector, industry, and other metadata for each ticker via
yfinance. Filters the universe to NASDAQ-listed stocks in target
sectors and removes non-common-stock instruments.
"""

import time
from typing import Optional

import pandas as pd

from pipeline.config import (
    setup_logger, get_universe_config, lake_path
)
from pipeline.utils import (
    write_parquet, read_parquet, get_today_str, is_valid_ticker
)

logger = setup_logger("pipeline.enrich_tickers")


def fetch_ticker_metadata(tickers: list[str],
                          delay: float = 0.2) -> pd.DataFrame:
    """
    Fetch metadata for each ticker using yfinance.Ticker().info.

    Args:
        tickers: List of ticker symbols.
        delay: Seconds to wait between API calls.

    Returns:
        DataFrame with columns: ticker, name, sector, industry,
        market_cap, exchange, quote_type
    """
    import yfinance as yf

    logger.info(f"Fetching metadata for {len(tickers)} tickers...")
    records = []
    failures = []

    for i, ticker in enumerate(tickers):
        if (i + 1) % 50 == 0:
            logger.info(f"  Progress: {i + 1}/{len(tickers)}")

        try:
            info = yf.Ticker(ticker).info

            records.append({
                "ticker": ticker,
                "name": info.get("longName", info.get("shortName", "")),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "market_cap": info.get("marketCap", None),
                "exchange": info.get("exchange", ""),
                "quote_type": info.get("quoteType", ""),
            })

        except Exception as e:
            logger.debug(f"Failed to fetch metadata for {ticker}: {e}")
            failures.append(ticker)

        if delay > 0:
            time.sleep(delay)

    if failures:
        logger.warning(f"Failed to fetch metadata for {len(failures)} tickers")

    df = pd.DataFrame(records)
    logger.info(f"Fetched metadata for {len(df)} tickers "
                f"({len(failures)} failures)")
    return df


def filter_universe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter ticker metadata to the target universe.

    Keeps only:
    - NASDAQ-listed stocks (NMS, NGM, NCM, NAS exchanges)
    - Target sectors: Technology, Healthcare, Communication Services
    - Target gaming industries
    - Common stocks only (no warrants, rights, units, ETFs, preferred)

    Args:
        df: Raw ticker metadata DataFrame.

    Returns:
        Filtered DataFrame.
    """
    if df.empty:
        return df

    cfg = get_universe_config()
    initial_count = len(df)

    # Step 1: Filter to equity quote types
    exclude_types = set(cfg.get("exclude_quote_types", []))
    if "quote_type" in df.columns:
        df = df[~df["quote_type"].isin(exclude_types)]
        # Keep only EQUITY type
        df = df[df["quote_type"].isin(["EQUITY", ""])]
    logger.info(f"After quote_type filter: {len(df)} tickers")

    # Step 2: Filter out non-common-stock by ticker/name patterns
    mask = df.apply(
        lambda row: is_valid_ticker(row["ticker"], row.get("name", "")),
        axis=1
    )
    df = df[mask]
    logger.info(f"After ticker/name pattern filter: {len(df)} tickers")

    # Step 3: Filter to target sectors + gaming industries
    target_sectors = set(cfg.get("sectors", []))
    gaming_industries = set(cfg.get("gaming_industries", []))

    def is_in_universe(row) -> bool:
        sector = row.get("sector", "")
        industry = row.get("industry", "")

        # Direct sector match
        if sector in target_sectors:
            return True

        # Gaming industry match (may be in Communication Services)
        if industry in gaming_industries:
            return True

        return False

    df = df[df.apply(is_in_universe, axis=1)]
    logger.info(f"After sector/industry filter: {len(df)} tickers")

    # Step 4: Filter to NASDAQ exchanges
    nasdaq_exchanges = {"NMS", "NGM", "NCM", "NAS", "NASDAQ"}
    if "exchange" in df.columns:
        # Some tickers may have empty exchange — keep them for now
        df = df[
            df["exchange"].isin(nasdaq_exchanges) |
            (df["exchange"] == "") |
            df["exchange"].isna()
        ]
    logger.info(f"After exchange filter: {len(df)} tickers")

    logger.info(f"Universe filter: {initial_count} → {len(df)} tickers "
                f"({initial_count - len(df)} removed)")

    return df.reset_index(drop=True)


def run_enrich(target_date: str = None,
               price_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Main entry point: fetch ticker metadata, filter universe,
    and write to Bronze layer.

    Args:
        target_date: Date string for partition (default: today).
        price_df: Optional DataFrame with 'ticker' column to limit
                  metadata fetching to only tickers we have prices for.

    Returns:
        Filtered ticker metadata DataFrame.
    """
    if target_date is None:
        target_date = get_today_str()

    # Determine which tickers to enrich
    if price_df is not None and "ticker" in price_df.columns:
        tickers = price_df["ticker"].unique().tolist()
    else:
        # Try to read from Bronze prices
        try:
            price_path = lake_path("bronze", "prices", target_date)
            prices = read_parquet(price_path)
            tickers = prices["ticker"].unique().tolist()
        except FileNotFoundError:
            logger.warning("No price data found — using full ticker universe")
            from pipeline.ingest_prices import get_ticker_universe
            tickers = get_ticker_universe()

    # Check if we already have cached ticker metadata
    out_path = lake_path("bronze", "tickers", target_date)
    try:
        cached = read_parquet(out_path)
        if len(cached) > 0:
            logger.info(f"Using cached ticker metadata ({len(cached)} tickers)")
            return cached
    except FileNotFoundError:
        pass

    # Fetch metadata
    raw_metadata = fetch_ticker_metadata(tickers, delay=0.15)

    if raw_metadata.empty:
        logger.error("No ticker metadata fetched — aborting")
        return raw_metadata

    # Write raw metadata to Bronze
    write_parquet(raw_metadata, out_path, filename="raw_metadata.parquet")

    # Filter to target universe
    filtered = filter_universe(raw_metadata)

    # Write filtered metadata
    write_parquet(filtered, out_path)

    # Log sector breakdown
    if not filtered.empty and "sector" in filtered.columns:
        sector_counts = filtered["sector"].value_counts()
        logger.info("Sector breakdown:")
        for sector, count in sector_counts.items():
            logger.info(f"  {sector}: {count} tickers")

    logger.info(f"✅ Bronze/tickers enrichment complete: {len(filtered)} tickers "
                f"→ dt={target_date}")

    return filtered


if __name__ == "__main__":
    run_enrich()
