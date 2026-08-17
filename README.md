# NASDAQ Day Trading Predictor 📈

> **AI-powered stock prediction pipeline** — a production-grade, AWS-native data engineering + ML application that ingests daily NASDAQ OHLCV data, engineers 20+ technical features, trains a predictive model, and outputs the Top 5 stocks with the highest probability of a ≥$1 intraday gain — scheduled serverlessly on ECS Fargate and queryable via Athena + Power BI.

⚠️ **Disclaimer**: This project is for **educational and portfolio demonstration purposes only**. It is NOT financial advice. Stock predictions are inherently uncertain. Never invest money you cannot afford to lose.

---

## 🎯 Project Purpose

This project demonstrates **production-grade data engineering and ML engineering skills** for a resume/portfolio. The full AWS-native stack is live and running:

1. **Ingests** daily NASDAQ OHLCV data via yfinance
2. **Enriches** ticker metadata with sector/industry classification
3. **Engineers** 20+ technical features (RSI, ATR, volume spikes, SMAs, gap analysis)
4. **Trains** a Logistic Regression model to predict ≥$1 intraday moves
5. **Outputs** the Top 5 daily picks with probabilities to S3 (Gold layer)
6. **Stores** all data in a Hive-partitioned S3 data lake (Bronze → Silver → Gold)
7. **Queries** results via Athena SQL and exposes them to Power BI
8. **Schedules** automatically via EventBridge every weekday at 9 AM ET
9. **Deploys** containerized via ECS Fargate (CI/CD via GitHub Actions + ECR)
10. **Visualizes** results in both a local Streamlit dashboard and Power BI

Target sectors: **Technology**, **Healthcare**, **Gaming/Interactive Entertainment**

---

## 🏗️ Architecture

### Local Mode (`MODE=local`)
```
yfinance API → main_orchestrator.py → _lake/ (Bronze/Silver/Gold) → Streamlit Dashboard
```

### AWS Mode (`MODE=aws`) — Production
```
EventBridge (weekday 9 AM ET)
        │
        ▼
ECS Fargate Task (Docker image from ECR)
        │
        ▼
yfinance API → main_orchestrator.py
        │
        ├──▶ S3: bronze/prices/dt=YYYY-MM-DD/         (raw OHLCV Parquet)
        ├──▶ S3: bronze/tickers/dt=YYYY-MM-DD/        (ticker metadata Parquet)
        ├──▶ S3: silver/features/dt=YYYY-MM-DD/       (feature-engineered Parquet)
        ├──▶ S3: gold/predictions/dt=YYYY-MM-DD/      (Top 5 picks Parquet)
        ├──▶ S3: gold/all_predictions/dt=YYYY-MM-DD/  (all scored tickers Parquet)
        └──▶ S3: gold/model_metrics/dt=YYYY-MM-DD/    (backtest metrics Parquet)
                 │
                 ▼
         Glue Data Catalog (3 tables)
                 │
                 ▼
         Athena SQL ──▶ Power BI Desktop
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11 |
| Data Ingestion | yfinance |
| Data Processing | pandas, NumPy |
| ML Model | scikit-learn (LogisticRegression + SimpleImputer + StandardScaler) |
| Storage (Local) | Parquet (PyArrow) + CSV |
| Storage (Cloud) | AWS S3 (Hive-partitioned Parquet) |
| Data Catalog | AWS Glue Data Catalog |
| Query Engine | AWS Athena |
| Scheduling | AWS EventBridge (cron weekdays 9 AM ET) |
| Compute | AWS ECS Fargate (0.25 vCPU, 512 MB) |
| Container Registry | AWS ECR |
| Logging | AWS CloudWatch |
| CI/CD | GitHub Actions |
| Dashboard | Streamlit + Plotly (local) / Power BI (cloud) |
| Configuration | YAML + python-dotenv |
| Testing | pytest (20 tests) |

---

## ☁️ AWS Resources Deployed

| Resource | Name | Status |
|----------|------|--------|
| S3 Bucket | `stock-predictor-lake-{account}-us-east-1-an` | ✅ Active |
| ECR Repository | `stock-predictor` | ✅ Image pushed |
| ECS Cluster | `stock-predictor-cluster` | ✅ Active |
| ECS Task Definition | `stock-predictor:1` (Fargate) | ✅ Registered |
| CloudWatch Log Group | `/ecs/stock-predictor` | ✅ Logging |
| Glue Database | `stock_predictor` | ✅ 3 tables |
| Athena Workgroup | `stock-predictor-workgroup` | ✅ Querying |
| EventBridge Rule | `stock-predictor-weekday-9am` | ✅ Enabled |

---

## 📁 S3 Data Lake Layout

```
s3://{bucket}/
├── bronze/
│   ├── prices/dt=YYYY-MM-DD/data.parquet       # Raw OHLCV from yfinance
│   └── tickers/dt=YYYY-MM-DD/data.parquet      # Ticker sector/industry metadata
├── silver/
│   └── features/dt=YYYY-MM-DD/data.parquet     # 20+ engineered features
├── gold/
│   ├── predictions/dt=YYYY-MM-DD/data.parquet  # Top 5 picks (Athena table)
│   ├── all_predictions/dt=YYYY-MM-DD/          # All scored tickers
│   └── model_metrics/dt=YYYY-MM-DD/            # Backtest metrics (Athena table)
└── gold_csv/                                   # CSV copies for Power BI direct download
    ├── predictions/dt=YYYY-MM-DD/data.csv
    └── model_metrics/dt=YYYY-MM-DD/data.csv
```

---

## 🚀 Local Run Instructions

### Prerequisites

- Python 3.10+
- Docker Desktop (for containerized runs)

### Setup

```bash
# Clone the repository
git clone https://github.com/ShariqO/stock-market-predictor.git
cd stock-market-predictor

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and set MODE=local (default)
```

### Run the Pipeline (Local Mode)

```bash
# Run the full pipeline end-to-end
python main_orchestrator.py

# Or run individual steps
python jobs/job_ingest_prices.py    # Step 1: Download prices
python jobs/job_build_features.py   # Step 2: Engineer features
python jobs/job_predict.py          # Step 3: Train + predict
```

### Run the Pipeline (AWS Mode)

```bash
# Requires AWS credentials in .env
MODE=aws python main_orchestrator.py
```

### Run Tests

```bash
pytest tests/test_validate.py -v
# Expected: 20/20 passed
```

---

## 🐳 Docker Instructions

```bash
# Build the image
docker compose build

# Run the full pipeline
docker compose run predictor python main_orchestrator.py

# Start the Streamlit dashboard
docker compose up dashboard
# Open http://localhost:8501 in your browser
```

---

## 📊 Streamlit Dashboard

The dashboard shows four tabs:

1. **🏆 Top 5 Picks** — Daily picks with ticker, sector, probability, close price, key features
2. **📊 Probability Analysis** — Bar chart of top 20 tickers + probability cutoff
3. **🏭 Sector Breakdown** — Donut chart of picks by sector
4. **📈 Model Performance** — Precision@5 and hit rate over time

```bash
streamlit run dashboard/app.py
# Open http://localhost:8501
```

---

## 🔍 Athena SQL Queries

Sample queries against the live S3 data lake (see `sql/athena_queries.sql` for all 9):

```sql
-- Today's Top 5 picks
SELECT rank, ticker, sector, ROUND(predicted_probability, 4) AS prob, last_close, as_of_date
FROM stock_predictor.gold_predictions
WHERE rank <= 5
ORDER BY rank;

-- 30-day model performance
SELECT as_of_date, ROUND(precision_at_5, 3) AS precision, hit_rate
FROM stock_predictor.gold_model_metrics
ORDER BY as_of_date DESC
LIMIT 30;
```

---

## 📊 Power BI Connection

Power BI Desktop (Windows) connects directly to Athena via the ODBC driver — no local data download required.

See [docs/powerbi_setup.md](docs/powerbi_setup.md) for full instructions.

---

## 🔁 CI/CD Pipeline (GitHub Actions)

On every push to `main`, the workflow in `.github/workflows/deploy.yml`:

1. **Test** — runs `pytest` (20 tests)
2. **Build** — builds Docker image for `linux/amd64`
3. **Push** — pushes image to ECR with `latest` + git SHA tag
4. **Deploy** — registers new ECS task definition revision

---

## 🧪 Features Engineered

| Feature | Description |
|---------|-------------|
| `vol_avg_5d` / `vol_avg_20d` | Rolling average volume |
| `vol_spike_ratio` | Today's volume / 20-day avg |
| `atr_14d` | 14-day Average True Range |
| `volatility_20d` | 20-day rolling std of returns |
| `rsi_14d` | 14-period Relative Strength Index |
| `sma_5d/10d/20d/50d` | Simple Moving Averages |
| `price_vs_sma*` | Price distance from moving averages |
| `return_1d/3d/5d` | Short-term price returns |
| `gap` | Overnight gap (open vs previous close) |
| `intraday_range` / `intraday_range_pct` | High − Low (absolute + %) |
| `daily_return` | Same-day return |

---

## 📋 Project Structure

```
.
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Container definition
├── docker-compose.yml           # Multi-service orchestration
├── .env.example                 # Environment variable template
├── config.yaml                  # Pipeline configuration
├── main_orchestrator.py         # Full pipeline runner
├── pipeline/                    # Core pipeline modules
│   ├── config.py                # Configuration loader (mode-aware)
│   ├── utils.py                 # Dual-mode I/O (local ↔ S3)
│   ├── s3_storage.py            # S3 read/write via boto3
│   ├── ingest_prices.py         # Bronze: OHLCV ingestion
│   ├── enrich_tickers.py        # Bronze: Ticker metadata
│   ├── build_features.py        # Silver: Feature engineering
│   ├── train_predict.py         # Gold: ML training + prediction
│   └── validate_data.py         # Data quality checks
├── jobs/                        # Individual job runners
├── aws/                         # AWS infrastructure
│   ├── glue_tables.py           # Glue Data Catalog setup
│   ├── ecs_task_definition.json # Fargate task definition
│   └── eventbridge_rule.json    # Weekday schedule config
├── dashboard/                   # Streamlit reporting (local)
│   └── app.py
├── sql/                         # Athena SQL queries
│   └── athena_queries.sql
├── .github/workflows/           # CI/CD
│   └── deploy.yml               # GitHub Actions pipeline
├── docs/                        # Documentation
│   ├── architecture.md
│   ├── aws_setup.md
│   ├── powerbi_setup.md
│   └── resume_summary.md
├── tests/                       # Unit tests
│   └── test_validate.py
└── _lake/                       # Local data lake (gitignored)
```

---

## 🧮 Model Performance (Backtest)

- **Algorithm**: Logistic Regression (SimpleImputer → StandardScaler → LogisticRegression)
- **Training**: Walk-forward on all available historical data before prediction date
- **Backtest (30 days)**: Avg Precision@5 = **95.9%** | Avg Hit Rate = **100%**
- **Universe**: ~100 filtered NASDAQ tickers across Technology, Healthcare, and Gaming sectors

---

## 📄 License

This project is for educational purposes only. See disclaimer above.
