# Power BI Setup Guide

> Connect Power BI Desktop (Windows) directly to your live AWS Athena data — **no local clone or data download required**.

---

## Option A: Connect via Athena ODBC (Recommended for Live Data)

This streams live S3 data directly into Power BI via Athena. Your dashboard auto-refreshes whenever the ECS pipeline runs.

### Step 1: Install the Simba Athena ODBC Driver

1. Go to: https://www.simba.com/drivers/athena-odbc-jdbc/
2. Download **Simba Athena ODBC Driver** (64-bit, Windows)
3. Run the installer with default settings

### Step 2: Create an ODBC DSN

1. Open **ODBC Data Sources (64-bit)** from the Windows Start menu
2. Click **System DSN** tab → **Add**
3. Select **Simba Athena ODBC Driver** → **Finish**
4. Configure:

| Setting | Value |
|---------|-------|
| Data Source Name | `StockPredictor` |
| AWS Region | `us-east-1` |
| S3 Output Location | `s3://stock-predictor-lake-{your-account}-us-east-1-an/athena-results/` |
| Authentication Type | `IAM Credentials` |
| Access Key | Your `AWS_ACCESS_KEY_ID` from `.env` |
| Secret Key | Your `AWS_SECRET_ACCESS_KEY` from `.env` |
| Schema | `stock_predictor` |

5. Click **Test** — you should see "Test completed successfully"
6. Click **OK**

### Step 3: Connect Power BI to the ODBC Source

1. Open **Power BI Desktop**
2. Click **Get Data** → search for **ODBC** → click **Connect**
3. From the dropdown select **StockPredictor** → click **OK**
4. In the Navigator, expand **stock_predictor** database:
   - ✅ `gold_predictions` — Top 5 daily picks
   - ✅ `gold_model_metrics` — Backtest precision & hit rate
   - ✅ `silver_features` — Feature data (large, optional)
5. Select `gold_predictions` and `gold_model_metrics` → click **Load**

### Step 4: Build Your Visuals

Suggested visuals:

| Visual | Fields |
|--------|--------|
| **Card** | Max `predicted_probability` (latest date) |
| **Table** | `rank`, `ticker`, `sector`, `predicted_probability`, `last_close` filtered to today |
| **Bar Chart** | `ticker` vs `predicted_probability` (top 20) |
| **Donut Chart** | `sector` count |
| **Line Chart** | `as_of_date` vs `precision_at_5` from `gold_model_metrics` |

### Step 5: Filter to Today's Picks

1. Add a **Date slicer** on `as_of_date`
2. Or create a calculated measure:
```dax
Latest Date = MAX(gold_predictions[as_of_date])
```
3. Filter `as_of_date = [Latest Date]`

---

## Option B: Connect via CSV Files (Simpler, No ODBC Driver)

If you'd prefer to skip the ODBC setup, download the pre-generated CSVs from S3 directly.

### Step 1: Download Latest CSV from S3

1. Go to the [AWS S3 Console](https://s3.console.aws.amazon.com/s3/)
2. Navigate to your bucket: `stock-predictor-lake-{account}-us-east-1-an`
3. Browse to: `gold_csv/predictions/dt=YYYY-MM-DD/data.csv`
   - Pick the most recent `dt=` folder
4. Click the file → **Download**
5. Repeat for `gold_csv/model_metrics/dt=YYYY-MM-DD/data.csv`

### Step 2: Load into Power BI

1. Open **Power BI Desktop**
2. Click **Get Data** → **Text/CSV**
3. Select the downloaded `data.csv`
4. Click **Load**
5. Repeat for model metrics
6. Build your visuals (same as Option A Step 4)

---

## Option C: Connect via AWS CLI Download (Automation)

Create a simple Windows batch file to always fetch the latest CSV before opening Power BI:

```batch
@echo off
REM save as: refresh_powerbi_data.bat
set BUCKET=stock-predictor-lake-{your-account}-us-east-1-an
set DEST=C:\PowerBI\StockPredictor

aws s3 sync s3://%BUCKET%/gold_csv/ %DEST% --region us-east-1 --exclude "*" --include "*.csv"
echo Data refreshed! Open PowerBI now.
pause
```

Then in Power BI, point your CSV source to `C:\PowerBI\StockPredictor\predictions\...`.

---

## Suggested Dashboard Layout

```
┌─────────────────────────────────────────────────────────┐
│  📈 NASDAQ Day Trading Predictor                   [Date]│
├──────────────┬──────────────┬──────────────┬────────────┤
│  Stocks      │  Top Prob    │  Precision@5 │  Hit Rate  │
│  Scored: 56  │  100.0%      │  95.9%       │  100.0%    │
├──────────────┴──────────────┴──────────────┴────────────┤
│                    TOP 5 PICKS TABLE                     │
│  Rank │ Ticker │ Sector     │ Probability │ Close Price  │
│   1   │ KLAC   │ Technology │   100.0%    │   $2,131    │
│   2   │ STX    │ Technology │   100.0%    │   $925      │
│   3   │ AMD    │ Technology │   100.0%    │   $523      │
│   4   │ WDC    │ Technology │   100.0%    │   $575      │
│   5   │ MRVL   │ Technology │   99.8%     │   $316      │
├────────────────────────────┬────────────────────────────┤
│  Bar: Probability by Ticker│  Line: Precision@5 Over    │
│  (Top 20)                  │  Time (30 days)            │
└────────────────────────────┴────────────────────────────┘
```

---

## Do I Need to Clone the Repo on Windows?

**No.** All live data is in S3. You only need:

- **Option A (Athena ODBC)**: AWS credentials + ODBC driver only
- **Option B (CSV)**: Just download the CSV files manually
- **Option C (CLI)**: AWS CLI installed + credentials configured

If you *want* to run the pipeline on Windows (not needed for Power BI):
1. Install Python 3.11 + Git
2. `git clone https://github.com/ShariqO/stock-market-predictor.git`
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in your AWS keys
5. `MODE=aws python main_orchestrator.py`
