-- ============================================================
-- NASDAQ Day Trading Predictor — Athena Queries
-- ============================================================
-- Run these in the Athena console after:
--   1. Creating Glue tables:  python aws/glue_tables.py
--   2. Running the pipeline:  MODE=aws python main_orchestrator.py
--   3. Repairing partitions:  MSCK REPAIR TABLE ...
--
-- Workgroup: stock-predictor-workgroup
-- Database:  stock_predictor
-- ============================================================


-- ═══════════════════════════════════════════════════════════
-- PARTITION REPAIR (run after each new pipeline run)
-- ═══════════════════════════════════════════════════════════

MSCK REPAIR TABLE stock_predictor.silver_features;
MSCK REPAIR TABLE stock_predictor.gold_predictions;
MSCK REPAIR TABLE stock_predictor.gold_model_metrics;


-- ═══════════════════════════════════════════════════════════
-- QUERY 1: Daily Top 5 predictions for a specific date
-- ═══════════════════════════════════════════════════════════

SELECT
    rank,
    ticker,
    sector,
    industry,
    predicted_probability,
    last_close,
    top_features,
    as_of_date
FROM stock_predictor.gold_predictions
WHERE dt = '2026-05-01'
  AND rank <= 5
ORDER BY rank;


-- ═══════════════════════════════════════════════════════════
-- QUERY 2: Latest Top 5 predictions (most recent date)
-- ═══════════════════════════════════════════════════════════

SELECT
    rank,
    ticker,
    sector,
    industry,
    predicted_probability,
    last_close,
    as_of_date
FROM stock_predictor.gold_predictions
WHERE dt = (
    SELECT MAX(dt) FROM stock_predictor.gold_predictions
)
AND rank <= 5
ORDER BY rank;


-- ═══════════════════════════════════════════════════════════
-- QUERY 3: Historical model performance (last 30 days)
-- ═══════════════════════════════════════════════════════════

SELECT
    as_of_date,
    precision_at_5,
    hit_rate,
    num_tickers_scored,
    positive_rate
FROM stock_predictor.gold_model_metrics
ORDER BY as_of_date DESC
LIMIT 30;


-- ═══════════════════════════════════════════════════════════
-- QUERY 4: Average model metrics
-- ═══════════════════════════════════════════════════════════

SELECT
    COUNT(*) AS days_evaluated,
    AVG(precision_at_5) AS avg_precision_at_5,
    AVG(hit_rate) AS avg_hit_rate,
    MIN(precision_at_5) AS min_precision,
    MAX(precision_at_5) AS max_precision,
    AVG(num_tickers_scored) AS avg_tickers_scored
FROM stock_predictor.gold_model_metrics;


-- ═══════════════════════════════════════════════════════════
-- QUERY 5: Sector-level performance
-- ═══════════════════════════════════════════════════════════

SELECT
    sector,
    COUNT(*) AS times_in_top5,
    AVG(predicted_probability) AS avg_probability,
    MIN(predicted_probability) AS min_probability,
    MAX(predicted_probability) AS max_probability,
    COUNT(DISTINCT as_of_date) AS unique_days
FROM stock_predictor.gold_predictions
WHERE rank <= 5
GROUP BY sector
ORDER BY times_in_top5 DESC;


-- ═══════════════════════════════════════════════════════════
-- QUERY 6: Most frequently picked tickers
-- ═══════════════════════════════════════════════════════════

SELECT
    ticker,
    sector,
    COUNT(*) AS times_in_top5,
    AVG(predicted_probability) AS avg_probability,
    AVG(last_close) AS avg_close_price,
    MIN(as_of_date) AS first_picked,
    MAX(as_of_date) AS last_picked
FROM stock_predictor.gold_predictions
WHERE rank <= 5
GROUP BY ticker, sector
ORDER BY times_in_top5 DESC
LIMIT 20;


-- ═══════════════════════════════════════════════════════════
-- QUERY 7: Daily prediction count and probability stats
-- ═══════════════════════════════════════════════════════════

SELECT
    as_of_date,
    COUNT(*) AS tickers_scored,
    AVG(predicted_probability) AS avg_probability,
    MAX(predicted_probability) AS max_probability,
    MIN(predicted_probability) AS min_probability
FROM stock_predictor.gold_predictions
GROUP BY as_of_date
ORDER BY as_of_date DESC
LIMIT 30;


-- ═══════════════════════════════════════════════════════════
-- QUERY 8: Feature statistics from Silver layer
-- ═══════════════════════════════════════════════════════════

SELECT
    sector,
    COUNT(DISTINCT ticker) AS unique_tickers,
    AVG(rsi_14d) AS avg_rsi,
    AVG(atr_14d) AS avg_atr,
    AVG(vol_spike_ratio) AS avg_vol_spike,
    AVG(volatility_20d) AS avg_volatility
FROM stock_predictor.silver_features
WHERE dt = (SELECT MAX(dt) FROM stock_predictor.silver_features)
GROUP BY sector
ORDER BY unique_tickers DESC;


-- ═══════════════════════════════════════════════════════════
-- QUERY 9: Model drift detection
--   Compare recent performance vs overall average
-- ═══════════════════════════════════════════════════════════

WITH recent AS (
    SELECT AVG(precision_at_5) AS recent_avg
    FROM stock_predictor.gold_model_metrics
    WHERE as_of_date >= DATE_FORMAT(DATE_ADD('day', -7, CURRENT_DATE), '%Y-%m-%d')
),
overall AS (
    SELECT AVG(precision_at_5) AS overall_avg
    FROM stock_predictor.gold_model_metrics
)
SELECT
    recent.recent_avg AS last_7d_precision,
    overall.overall_avg AS overall_precision,
    recent.recent_avg - overall.overall_avg AS drift
FROM recent, overall;
