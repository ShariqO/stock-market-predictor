# NASDAQ Day Trading Predictor

A daily batch pipeline that ingests NASDAQ OHLCV data, engineers technical features, trains a classifier, and writes the top five tickers by predicted probability of a $1 or greater intraday gain. Runs on ECS Fargate, stores everything in a partitioned S3 data lake, and is queryable through Athena.

> **Not financial advice.** This is a learning project. The model is a logistic regression on technical indicators, which is not a serious approach to trading. Do not put money behind it.

## What it does

1. Pulls daily OHLCV for roughly 100 filtered NASDAQ tickers via `yfinance`
2. Enriches with sector and industry metadata
3. Engineers 20+ technical features (RSI, ATR, volume spikes, SMAs, gaps)
4. Trains a logistic regression to predict a ≥$1 intraday move
5. Writes the top five picks with probabilities to the gold layer in S3
6. Registers tables in the Glue Data Catalog for Athena and Power BI

Universe is filtered to Technology, Healthcare, and Gaming.

## Architecture

Local mode:

```
yfinance → main_orchestrator.py → _lake/ (bronze/silver/gold) → Streamlit
```

AWS mode:

```
EventBridge (weekdays, 9am ET)
        │
        ▼
ECS Fargate task (image from ECR)
        │
        ▼
yfinance → main_orchestrator.py
        │
        ├──▶ s3://.../bronze/prices/dt=YYYY-MM-DD/
        ├──▶ s3://.../bronze/tickers/dt=YYYY-MM-DD/
        ├──▶ s3://.../silver/features/dt=YYYY-MM-DD/
        ├──▶ s3://.../gold/predictions/dt=YYYY-MM-DD/
        ├──▶ s3://.../gold/all_predictions/dt=YYYY-MM-DD/
        └──▶ s3://.../gold/model_metrics/dt=YYYY-MM-DD/
                 │
                 ▼
         Glue Data Catalog → Athena → Power BI
```

Everything is Hive-partitioned Parquet. The same orchestrator runs in both modes; `pipeline/utils.py` switches the I/O layer between local disk and S3 based on `MODE`.

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Ingestion | yfinance |
| Processing | pandas, NumPy |
| Model | scikit-learn (SimpleImputer → StandardScaler → LogisticRegression) |
| Storage | S3, Hive-partitioned Parquet |
| Catalog | AWS Glue |
| Query | AWS Athena |
| Scheduling | EventBridge |
| Compute | ECS Fargate (0.25 vCPU, 512 MB) |
| Registry | ECR |
| CI/CD | GitHub Actions |
| Dashboards | Streamlit (local), Power BI (via Athena ODBC) |
| Tests | pytest |

## On the backtest numbers

The 30-day walk-forward backtest reports average precision@5 around 96% and a hit rate near 100%. **Treat those numbers with suspicion rather than as a result.**

Two things inflate them. First, the target is loose: a $1 intraday range on a stock trading above $100 is common, so the positive class is not rare and a naive model scores well. Second, only five picks per day are evaluated, and those are the five the model is most confident about, so precision@5 measures the easiest slice of the distribution.

A fair evaluation would need a dollar-neutral target, a benchmark comparison against picking randomly from the same universe, and transaction cost assumptions. I haven't done that. The pipeline is the point here, not the model.

## Running locally

```bash
git clone https://github.com/ShariqO/stock-market-predictor.git
cd stock-market-predictor

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env     # MODE=local is the default
python main_orchestrator.py
```

Individual steps:

```bash
python jobs/job_ingest_prices.py     # bronze
python jobs/job_build_features.py    # silver
python jobs/job_predict.py           # gold
```

Tests:

```bash
pytest tests/test_validate.py -v
```

Docker:

```bash
docker compose build
docker compose run predictor python main_orchestrator.py
docker compose up dashboard          # localhost:8501
```

## AWS mode

Needs credentials in `.env` and the infrastructure in `aws/` provisioned. Setup is in `docs/aws_setup.md`.

Deployed resources: an S3 bucket for the lake, an ECR repository, an ECS cluster and Fargate task definition, a CloudWatch log group, a Glue database with three tables, an Athena workgroup, and an EventBridge rule firing weekdays at 9am ET.

```bash
MODE=aws python main_orchestrator.py
```

## Athena

Full query set is in `sql/athena_queries.sql`.

```sql
-- today's picks
SELECT rank, ticker, sector, ROUND(predicted_probability, 4) AS prob, last_close, as_of_date
FROM stock_predictor.gold_predictions
WHERE rank <= 5
ORDER BY rank;

-- model performance over the last 30 days
SELECT as_of_date, ROUND(precision_at_5, 3) AS precision, hit_rate
FROM stock_predictor.gold_model_metrics
ORDER BY as_of_date DESC
LIMIT 30;
```

## CI/CD

On push to `main`, `.github/workflows/deploy.yml` runs pytest, builds the image for `linux/amd64`, pushes to ECR tagged `latest` and the git SHA, then registers a new ECS task definition revision.

## Features

| Feature | Description |
|---|---|
| `vol_avg_5d`, `vol_avg_20d` | Rolling average volume |
| `vol_spike_ratio` | Today's volume over the 20-day average |
| `atr_14d` | 14-day Average True Range |
| `volatility_20d` | 20-day rolling standard deviation of returns |
| `rsi_14d` | 14-period Relative Strength Index |
| `sma_5d`, `sma_10d`, `sma_20d`, `sma_50d` | Simple moving averages |
| `price_vs_sma*` | Distance from each moving average |
| `return_1d`, `return_3d`, `return_5d` | Short-term returns |
| `gap` | Open versus previous close |
| `intraday_range`, `intraday_range_pct` | High minus low |
| `daily_return` | Same-day return |

## Project structure

```
.
├── main_orchestrator.py     # full pipeline runner
├── config.yaml
├── pipeline/
│   ├── config.py            # mode-aware config loader
│   ├── utils.py             # dual-mode I/O (local ↔ S3)
│   ├── s3_storage.py
│   ├── ingest_prices.py     # bronze
│   ├── enrich_tickers.py    # bronze
│   ├── build_features.py    # silver
│   ├── train_predict.py     # gold
│   └── validate_data.py
├── jobs/                    # individual job runners
├── aws/                     # Glue tables, ECS task def, EventBridge rule
├── dashboard/app.py         # Streamlit
├── sql/athena_queries.sql
├── tests/
└── docs/
```

## License

Educational use. See the disclaimer above.
