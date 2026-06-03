# Architecture — NASDAQ Day Trading Predictor

## System Overview

The NASDAQ Day Trading Predictor is an end-to-end data engineering + ML pipeline that follows the **medallion architecture** (Bronze → Silver → Gold) for data quality and traceability.

---

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA SOURCES                              │
│                                                             │
│   yfinance API ───► OHLCV Prices (Open, High, Low, Close,  │
│                     Volume) for ~170 NASDAQ tickers         │
│                                                             │
│   yfinance .info ─► Ticker metadata (sector, industry,     │
│                     exchange, market cap, quote type)       │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    BRONZE LAYER                              │
│                                                             │
│   Raw, unmodified data as received from the source.        │
│                                                             │
│   _lake/bronze/prices/dt=YYYY-MM-DD/data.parquet           │
│   _lake/bronze/tickers/dt=YYYY-MM-DD/data.parquet          │
│                                                             │
│   Validations:                                              │
│   ✓ Required OHLCV columns exist                           │
│   ✓ No negative volume                                     │
│   ✓ No duplicate ticker/date rows                          │
│   ✓ OHLC values are non-null                               │
│   ✓ High >= Low                                             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    SILVER LAYER                              │
│                                                             │
│   Cleaned, filtered, feature-engineered data.              │
│                                                             │
│   Universe Filtering:                                       │
│   • NASDAQ exchange only (NMS, NGM, NCM)                   │
│   • Sectors: Technology, Healthcare, Communication Services│
│   • Industries: Electronic Gaming & Multimedia             │
│   • Remove: warrants, rights, units, ETFs, preferred       │
│                                                             │
│   Feature Engineering (20+ features):                      │
│   • Volume: 5d/20d avg, spike ratio                        │
│   • Volatility: ATR, rolling std                           │
│   • Momentum: RSI, moving averages, price vs SMA           │
│   • Returns: 1d, 3d, 5d                                   │
│   • Gap: overnight open vs previous close                  │
│   • Range: intraday high-low range                         │
│                                                             │
│   _lake/silver/features/dt=YYYY-MM-DD/data.parquet         │
│                                                             │
│   Validations:                                              │
│   ✓ Feature columns exist (≥5)                             │
│   ✓ Sufficient lookback per ticker (≥60 days)              │
│   ✓ No negative volume                                     │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    GOLD LAYER                                │
│                                                             │
│   ML Pipeline:                                              │
│   SimpleImputer(median) → StandardScaler → LogisticRegr    │
│                                                             │
│   Target: binary label                                      │
│   1 = next day (High - Open) >= $1.00                      │
│   0 = next day (High - Open) < $1.00                       │
│                                                             │
│   Training: all data prior to prediction date              │
│   Prediction: score all tickers for most recent date       │
│   Selection: rank by P(target=1), pick Top 5               │
│                                                             │
│   Backtesting:                                              │
│   Walk-forward evaluation over last 30 trading days        │
│   Metrics: precision@5, hit rate                           │
│                                                             │
│   _lake/gold/predictions/dt=YYYY-MM-DD/data.parquet|csv    │
│   _lake/gold/model_metrics/dt=YYYY-MM-DD/data.parquet|csv  │
│                                                             │
│   Validations:                                              │
│   ✓ No duplicate ranks per day                             │
│   ✓ Probabilities in [0, 1]                                │
│   ✓ ≥5 picks per day                                       │
│   ✓ Metrics in valid ranges                                │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    REPORTING                                 │
│                                                             │
│   Streamlit Dashboard (localhost:8501):                     │
│   • Top 5 picks table with probability + reasoning         │
│   • Probability distribution chart                         │
│   • Sector breakdown donut chart                           │
│   • Model performance time series                          │
│                                                             │
│   Power BI Desktop (optional):                             │
│   • Connect to Gold layer CSV files                        │
│   • Build custom visualizations                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Dependency Graph

```
config.yaml + .env
       │
       ▼
  pipeline/config.py ◄─── Central configuration
       │
       ▼
  pipeline/utils.py  ◄─── I/O + helpers
       │
       ├──► pipeline/validate_data.py
       │
       ├──► pipeline/ingest_prices.py ──► Bronze/prices
       │
       ├──► pipeline/enrich_tickers.py ──► Bronze/tickers
       │
       ├──► pipeline/build_features.py ──► Silver/features
       │
       └──► pipeline/train_predict.py ──► Gold/predictions + metrics
                    │
                    ▼
            main_orchestrator.py  (runs all steps in order)
                    │
            jobs/job_*.py        (runs individual steps)
                    │
            dashboard/app.py     (reads Gold layer for display)
```

---

## Key Design Decisions

1. **Medallion Architecture**: Bronze/Silver/Gold layers ensure data lineage and reproducibility. Each layer is independently queryable.

2. **Date Partitioning**: All data is partitioned by `dt=YYYY-MM-DD`, making it compatible with Hive-style partitioning used by AWS Athena and Glue.

3. **Parquet + CSV Dual Output**: Gold layer outputs both formats — Parquet for efficient querying and CSV for Power BI compatibility.

4. **Balanced Classes**: `class_weight="balanced"` in LogisticRegression handles the imbalanced target (most stocks don't move $1+ daily).

5. **Walk-Forward Backtesting**: Avoids look-ahead bias by training only on data prior to each prediction date.

6. **Config-Driven**: All parameters are in `config.yaml`, making it easy to tune without code changes and to switch between local/AWS modes.
