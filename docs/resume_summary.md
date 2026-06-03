# Resume Summary — NASDAQ Day Trading Predictor

## One-Line Summary

> Built an end-to-end data engineering + ML pipeline (Python, pandas, scikit-learn, Docker, AWS) that predicts Top 5 NASDAQ stocks for daily intraday gains using a medallion-architecture data lake and Streamlit dashboard.

---

## Detailed Summary

Production-grade pipeline ingesting NASDAQ OHLCV data, engineering 20+ technical features (RSI, ATR, volume spikes, moving averages), and training a Logistic Regression model to predict ≥$1 intraday moves. Medallion architecture (Bronze/Silver/Gold) with partitioned Parquet storage, automated data quality checks, walk-forward backtesting, Docker containerization, and Streamlit reporting. Cloud deployment on AWS S3, Glue, Athena, ECS Fargate with EventBridge scheduling and GitHub Actions CI/CD.

---

## Resume Bullet Points

- **Engineered an end-to-end ML pipeline** using Python, pandas, and scikit-learn that ingests NASDAQ stock data, computes 20+ technical indicators, and generates daily Top 5 stock picks with walk-forward backtesting.

- **Designed a medallion-architecture data lake** (Bronze→Silver→Gold) with partitioned Parquet storage, 7+ automated data quality checks per layer, and dual-format output for Streamlit and Power BI consumption.

- **Built a containerized pipeline** with Docker Compose, supporting modular job execution, with cloud deployment on AWS ECS Fargate, S3, Glue, Athena, and EventBridge scheduling.

- **Developed an interactive Streamlit dashboard** with prediction display, probability analysis, sector breakdowns, and historical model performance tracking for non-technical stakeholders.
