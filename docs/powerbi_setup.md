# Power BI Setup Guide

## Connecting Power BI Desktop to Local Gold Layer

This guide explains how to connect Power BI Desktop to the NASDAQ Day Trading Predictor's Gold layer data for custom reporting and visualization.

> **Note**: Power BI Desktop is only available on Windows. If you're on macOS, use the Streamlit dashboard (`dashboard/app.py`) instead.

---

## Prerequisites

- Power BI Desktop installed (free download from [Microsoft](https://powerbi.microsoft.com/desktop/))
- Pipeline has been run at least once (`python main_orchestrator.py`)
- Gold layer data exists in `_lake/gold/`

---

## Step 1: Connect to Predictions Data

1. Open **Power BI Desktop**
2. Click **Get Data** → **Text/CSV**
3. Navigate to your project folder: `_lake/gold/predictions/dt=YYYY-MM-DD/data.csv`
   - Select the most recent date folder
4. Click **Load**

### Alternative: Load Parquet Files
1. Click **Get Data** → **Parquet**
2. Navigate to `_lake/gold/predictions/dt=YYYY-MM-DD/data.parquet`
3. Click **Load**

---

## Step 2: Connect to Metrics Data

1. Click **Get Data** → **Text/CSV** (or Parquet)
2. Navigate to `_lake/gold/model_metrics/dt=YYYY-MM-DD/data.csv`
3. Click **Load**

---

## Step 3: Load All Historical Data

To load all dates at once:

1. Click **Get Data** → **Folder**
2. Navigate to `_lake/gold/predictions/`
3. Power BI will detect all CSV/Parquet files in subdirectories
4. Click **Combine & Load**
5. Repeat for `_lake/gold/model_metrics/`

---

## Step 4: Build Visualizations

### Recommended Visualizations

| Visualization | Data Source | Fields |
|--------------|------------|--------|
| **Top 5 Picks Table** | predictions | ticker, predicted_probability, rank, sector, last_close |
| **Probability Bar Chart** | predictions | ticker (axis), predicted_probability (values) |
| **Sector Donut Chart** | predictions | sector (legend), count of ticker (values) |
| **Precision@5 Line Chart** | model_metrics | as_of_date (axis), precision_at_5 (values) |
| **Hit Rate Line Chart** | model_metrics | as_of_date (axis), hit_rate (values) |

### Suggested Report Layout

```
┌─────────────────────────────────────────────────────┐
│  NASDAQ Day Trading Predictor — Power BI Report     │
├──────────────────────┬──────────────────────────────┤
│                      │                              │
│   Top 5 Picks        │   Probability Bar Chart      │
│   (Table)            │                              │
│                      │                              │
├──────────────────────┼──────────────────────────────┤
│                      │                              │
│   Sector Breakdown   │   Model Performance          │
│   (Donut Chart)      │   (Line Chart)               │
│                      │                              │
└──────────────────────┴──────────────────────────────┘
```

---

## Step 5: Add Filters

1. Add a **Date Slicer** using `as_of_date` to filter by prediction date
2. Add a **Sector Slicer** to filter by sector
3. Add a **Probability Slider** to filter by minimum probability

---

## Data Model

```
predictions                    model_metrics
├── ticker                     ├── as_of_date
├── predicted_probability      ├── precision_at_5
├── rank                       ├── hit_rate
├── sector                     └── num_tickers_scored
├── industry
├── last_close
├── top_features
└── as_of_date ──────────────── as_of_date (relationship)
```

Create a relationship between `predictions.as_of_date` and `model_metrics.as_of_date` for cross-filtering.

---

## Refreshing Data

After running the pipeline again:
1. Click **Refresh** in Power BI Desktop
2. If using folder-based connections, new dates will be picked up automatically
3. If using single-file connections, you may need to update the file path

---

## Tips

- Use **Conditional Formatting** on the probability column to highlight high-probability picks (green) vs low (red)
- Add **KPI cards** for average precision@5 and hit rate
- Use **Bookmarks** to save different views (daily picks, historical performance, sector analysis)
