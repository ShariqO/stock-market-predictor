# NASDAQ Day Trading Predictor 📈

> **AI-powered stock prediction pipeline** — an end-to-end data engineering + machine learning application that identifies the Top 5 NASDAQ stocks with the highest probability of a ≥$1 intraday gain.

⚠️ **Disclaimer**: This project is for **educational and portfolio demonstration purposes only**. It is NOT financial advice. Stock predictions are inherently uncertain. Never invest money you cannot afford to lose. Past performance does not guarantee future results.

---

## 🎯 Project Purpose

This project demonstrates production-grade data engineering skills by building a complete pipeline that:

1. **Ingests** real-time NASDAQ stock data (OHLCV) via yfinance
2. **Enriches** ticker metadata with sector/industry classification
3. **Engineers** 20+ technical features (RSI, ATR, volume spikes, moving averages, gap analysis)
4. **Trains** a Logistic Regression model to predict ≥$1 intraday moves
5. **Outputs** the Top 5 daily stock picks with probabilities and reasoning
6. **Stores** all data in a partitioned data lake (Bronze → Silver → Gold)
7. **Visualizes** results in a Streamlit dashboard
8. **Runs** containerized in Docker

Target sectors: **Technology**, **Healthcare**, **Gaming/Interactive Entertainment**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR (main_orchestrator.py)          │
├─────────────┬─────────────┬─────────────┬──────────────────────────┤
│             │             │             │                          │
│  ┌──────────▼──────────┐  │  ┌──────────▼──────────┐              │
│  │   INGEST PRICES     │  │  │   ENRICH TICKERS    │              │
│  │   (yfinance API)    │  │  │   (yfinance .info)  │              │
│  └──────────┬──────────┘  │  └──────────┬──────────┘              │
│             │             │             │                          │
│             ▼             │             ▼                          │
│  ┌─────────────────────────────────────────────────┐               │
│  │              BRONZE LAYER (_lake/bronze/)        │               │
│  │  prices/dt=YYYY-MM-DD/   tickers/dt=YYYY-MM-DD/ │               │
│  └─────────────────────────┬───────────────────────┘               │
│                            │                                       │
│                 ┌──────────▼──────────┐                            │
│                 │   BUILD FEATURES    │                            │
│                 │   (20+ technical    │                            │
│                 │    indicators)      │                            │
│                 └──────────┬──────────┘                            │
│                            ▼                                       │
│  ┌─────────────────────────────────────────────────┐               │
│  │              SILVER LAYER (_lake/silver/)        │               │
│  │  features/dt=YYYY-MM-DD/                        │               │
│  └─────────────────────────┬───────────────────────┘               │
│                            │                                       │
│                 ┌──────────▼──────────┐                            │
│                 │   TRAIN & PREDICT   │                            │
│                 │   LogReg + Backtest │                            │
│                 └──────────┬──────────┘                            │
│                            ▼                                       │
│  ┌─────────────────────────────────────────────────┐               │
│  │              GOLD LAYER (_lake/gold/)            │               │
│  │  predictions/dt=YYYY-MM-DD/                     │               │
│  │  model_metrics/dt=YYYY-MM-DD/                   │               │
│  └─────────────────────────┬───────────────────────┘               │
│                            │                                       │
│                 ┌──────────▼──────────┐                            │
│                 │  STREAMLIT DASHBOARD │                            │
│                 │  (localhost:8501)    │                            │
│                 └─────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11 |
| Data Ingestion | yfinance |
| Data Processing | pandas, NumPy |
| ML Model | scikit-learn (LogisticRegression + SimpleImputer + StandardScaler) |
| Storage | Parquet (PyArrow) + CSV |
| Configuration | YAML + python-dotenv |
| Dashboard | Streamlit + Plotly |
| Containerization | Docker + Docker Compose |
| Testing | pytest |
| BI Layer | Power BI Desktop (optional) |

**Phase 2 (planned)**: AWS S3, Glue, Athena, ECS Fargate, EventBridge, CloudWatch, GitHub Actions CI/CD

---

## 📁 Data Lake Layout

```
_lake/
├── bronze/                          # Raw data
│   ├── prices/dt=YYYY-MM-DD/       # OHLCV from yfinance
│   └── tickers/dt=YYYY-MM-DD/      # Ticker metadata
├── silver/                          # Cleaned + features
│   └── features/dt=YYYY-MM-DD/     # Feature-engineered data
└── gold/                            # ML outputs
    ├── predictions/dt=YYYY-MM-DD/   # Top 5 picks (Parquet + CSV)
    └── model_metrics/dt=YYYY-MM-DD/ # Backtest metrics (Parquet + CSV)
```

---

## 🚀 Local Run Instructions (Phase 1)

### Prerequisites

- Python 3.10+
- pip
- Docker Desktop (for containerized runs)

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/stock-market-predictor.git
cd stock-market-predictor

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
```

### Run the Pipeline

```bash
# Run the full pipeline end-to-end
python main_orchestrator.py

# Or run individual steps
python jobs/job_ingest_prices.py    # Step 1: Download prices
python jobs/job_build_features.py   # Step 2: Engineer features
python jobs/job_predict.py          # Step 3: Train + predict
```

### Run Tests

```bash
pytest tests/test_validate.py -v
```

---

## 🐳 Docker Instructions

### Build and Run

```bash
# Build the image
docker compose build

# Run the full pipeline
docker compose run predictor python main_orchestrator.py

# Run individual jobs
docker compose run predictor python jobs/job_ingest_prices.py
docker compose run predictor python jobs/job_build_features.py
docker compose run predictor python jobs/job_predict.py

# Start the dashboard
docker compose up dashboard
# Open http://localhost:8501 in your browser
```

---

## 📊 Streamlit Dashboard

The dashboard displays four sections:

1. **🏆 Top 5 Picks** — Daily picks with ticker, sector, probability, close price, and key features
2. **📊 Probability Analysis** — Bar chart of top 20 tickers + probability distribution
3. **🏭 Sector Breakdown** — Donut chart of picks by sector + sector-level stats
4. **📈 Model Performance** — Precision@5 and hit rate over time with rolling averages

### Launch

```bash
# Direct
streamlit run dashboard/app.py

# Via Docker
docker compose up dashboard
```

Open **http://localhost:8501** in your browser.

---

## 📊 Power BI Connection

See [docs/powerbi_setup.md](docs/powerbi_setup.md) for detailed instructions on connecting Power BI Desktop to the Gold layer CSV/Parquet files.

Quick start:
1. Open Power BI Desktop
2. Get Data → Text/CSV or Parquet
3. Navigate to `_lake/gold/predictions/dt=YYYY-MM-DD/data.csv`
4. Build your visualizations

---

## ☁️ AWS Deployment (Phase 2)

Phase 2 will add cloud deployment with:
- **S3** — Cloud data lake (same partition structure)
- **Glue Data Catalog** — Table definitions for Athena
- **Athena** — SQL queries against S3 data
- **ECS Fargate** — Serverless container execution
- **EventBridge** — Weekday 9:00 AM scheduling
- **CloudWatch** — Logging and monitoring
- **GitHub Actions** — CI/CD pipeline
- **ECR** — Docker image registry

See [docs/aws_setup.md](docs/aws_setup.md) for setup instructions (available after Phase 2).

---

## 🧪 Features Engineered

| Feature | Description |
|---------|-------------|
| `vol_avg_5d` | 5-day rolling average volume |
| `vol_avg_20d` | 20-day rolling average volume |
| `vol_spike_ratio` | Today's volume / 20-day avg volume |
| `atr_14d` | 14-day Average True Range |
| `volatility_20d` | 20-day rolling standard deviation of returns |
| `rsi_14d` | 14-period Relative Strength Index |
| `sma_5d/10d/20d/50d` | Simple Moving Averages |
| `price_vs_sma*` | Price distance from moving averages |
| `return_1d/3d/5d` | Recent price returns |
| `gap` | Overnight gap (open vs previous close) |
| `intraday_range` | High − Low |
| `intraday_range_pct` | Intraday range as % of open |

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
│   ├── __init__.py
│   ├── config.py                # Configuration loader
│   ├── utils.py                 # Shared utilities
│   ├── ingest_prices.py         # Bronze: OHLCV ingestion
│   ├── enrich_tickers.py        # Bronze: Ticker metadata
│   ├── build_features.py        # Silver: Feature engineering
│   ├── train_predict.py         # Gold: ML training + prediction
│   └── validate_data.py         # Data quality checks
├── jobs/                        # Individual job runners
│   ├── job_ingest_prices.py
│   ├── job_build_features.py
│   └── job_predict.py
├── dashboard/                   # Streamlit reporting
│   └── app.py
├── sql/                         # Athena queries (Phase 2)
│   └── athena_queries.sql
├── docs/                        # Documentation
│   ├── architecture.md
│   ├── aws_setup.md
│   ├── powerbi_setup.md
│   └── resume_summary.md
├── tests/                       # Unit tests
│   └── test_validate.py
└── _lake/                       # Local data lake (gitignored)
    ├── bronze/
    ├── silver/
    └── gold/
```

---

## 📄 License

This project is for educational purposes only. See disclaimer above.
