"""
dashboard/app.py — Streamlit reporting dashboard

Displays:
  1. Daily Top 5 stock picks with probabilities
  2. Probability score by ticker (bar chart)
  3. Sector breakdown (donut chart)
  4. Model performance over time (line chart)

Usage:
    streamlit run dashboard/app.py
    docker compose up dashboard
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from pipeline.config import get_lake_root


# ── Page config ────────────────────────────────────────────
st.set_page_config(
    page_title="NASDAQ Day Trading Predictor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .main-header {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        padding: 2rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }

    .main-header h1 {
        font-size: 2.2rem;
        font-weight: 700;
        margin: 0;
        background: linear-gradient(90deg, #00d2ff, #7b2ff7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .main-header p {
        color: #a0aec0;
        margin-top: 0.5rem;
        font-size: 0.95rem;
    }

    .metric-card {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid rgba(123, 47, 247, 0.3);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }

    .metric-card h3 {
        color: #a0aec0;
        font-size: 0.8rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.3rem;
    }

    .metric-card .value {
        color: #00d2ff;
        font-size: 1.8rem;
        font-weight: 700;
    }

    .pick-card {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid rgba(123, 47, 247, 0.2);
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        transition: transform 0.2s, border-color 0.2s;
    }

    .pick-card:hover {
        transform: translateY(-2px);
        border-color: rgba(0, 210, 255, 0.5);
    }

    .rank-badge {
        display: inline-block;
        background: linear-gradient(135deg, #7b2ff7, #00d2ff);
        color: white;
        font-weight: 700;
        width: 32px;
        height: 32px;
        line-height: 32px;
        text-align: center;
        border-radius: 50%;
        font-size: 0.9rem;
    }

    .disclaimer {
        background: rgba(255, 193, 7, 0.1);
        border: 1px solid rgba(255, 193, 7, 0.3);
        border-radius: 8px;
        padding: 1rem;
        margin-top: 2rem;
        font-size: 0.8rem;
        color: #ffc107;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.5rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: #1a1a2e;
        border-radius: 8px 8px 0 0;
        padding: 0.5rem 1.5rem;
        color: #a0aec0;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #302b63, #24243e);
        color: #00d2ff;
    }
</style>
""", unsafe_allow_html=True)


# ── Data loading functions ─────────────────────────────────

@st.cache_data(ttl=300)
def load_predictions(lake_root: Path) -> tuple[pd.DataFrame, list[str]]:
    """Load all prediction data from Gold layer."""
    pred_base = lake_root / "gold" / "predictions"
    if not pred_base.exists():
        return pd.DataFrame(), []

    dates = sorted([
        d.name.replace("dt=", "") for d in pred_base.iterdir()
        if d.is_dir() and d.name.startswith("dt=")
    ])

    frames = []
    for date_str in dates:
        path = pred_base / f"dt={date_str}" / "data.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            if "as_of_date" not in df.columns:
                df["as_of_date"] = date_str
            frames.append(df)

    if not frames:
        return pd.DataFrame(), dates

    return pd.concat(frames, ignore_index=True), dates


@st.cache_data(ttl=300)
def load_all_predictions(lake_root: Path) -> pd.DataFrame:
    """Load all scored predictions (not just top 5)."""
    pred_base = lake_root / "gold" / "predictions"
    if not pred_base.exists():
        return pd.DataFrame()

    frames = []
    for d in sorted(pred_base.iterdir()):
        if d.is_dir() and d.name.startswith("dt="):
            path = d / "all_predictions.parquet"
            if path.exists():
                df = pd.read_parquet(path)
                if "as_of_date" not in df.columns:
                    df["as_of_date"] = d.name.replace("dt=", "")
                frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


@st.cache_data(ttl=300)
def load_metrics(lake_root: Path) -> pd.DataFrame:
    """Load all model metrics from Gold layer."""
    metrics_base = lake_root / "gold" / "model_metrics"
    if not metrics_base.exists():
        return pd.DataFrame()

    frames = []
    for d in sorted(metrics_base.iterdir()):
        if d.is_dir() and d.name.startswith("dt="):
            path = d / "data.parquet"
            if path.exists():
                df = pd.read_parquet(path)
                frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ── Main app ───────────────────────────────────────────────

def main():
    lake_root = get_lake_root()

    # Header
    st.markdown("""
    <div class="main-header">
        <h1>📈 NASDAQ Day Trading Predictor</h1>
        <p>AI-powered stock picks for Technology, Healthcare & Gaming sectors</p>
    </div>
    """, unsafe_allow_html=True)

    # Load data
    predictions_df, available_dates = load_predictions(lake_root)
    all_predictions_df = load_all_predictions(lake_root)
    metrics_df = load_metrics(lake_root)

    if predictions_df.empty:
        st.warning("⚠️ No prediction data found. Run the pipeline first:")
        st.code("python main_orchestrator.py", language="bash")
        st.stop()

    # Use as_of_date from the data (actual prediction dates) for selection
    if "as_of_date" in predictions_df.columns:
        actual_dates = sorted(predictions_df["as_of_date"].unique().tolist())
    else:
        actual_dates = available_dates

    # ── Sidebar ────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 📅 Select Date")
        if actual_dates:
            selected_date = st.selectbox(
                "Prediction Date",
                options=actual_dates[::-1],  # Most recent first
                index=0,
                label_visibility="collapsed",
            )
        else:
            selected_date = None

        st.markdown("---")
        st.markdown("### ℹ️ About")
        st.markdown(
            "This dashboard shows AI-predicted stock picks "
            "for NASDAQ-listed stocks in Technology, Healthcare, "
            "and Gaming sectors."
        )
        st.markdown(
            "**Model**: Logistic Regression with "
            "SimpleImputer + StandardScaler"
        )
        st.markdown(
            "**Target**: ≥ $1 intraday move (Open → High)"
        )

    # Filter to selected date
    day_preds = predictions_df[
        predictions_df["as_of_date"] == selected_date
    ].copy()

    if day_preds.empty:
        st.warning(f"No predictions for {selected_date}")
        st.stop()

    # ── Metrics row ────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📊 Stocks Scored",
                  f"{len(all_predictions_df[all_predictions_df['as_of_date'] == selected_date]) if not all_predictions_df.empty else len(day_preds)}")

    with col2:
        top_prob = day_preds["predicted_probability"].max() if "predicted_probability" in day_preds.columns else 0
        st.metric("🎯 Top Probability", f"{top_prob:.1%}")

    with col3:
        if not metrics_df.empty and "precision_at_5" in metrics_df.columns:
            avg_p5 = metrics_df["precision_at_5"].mean()
            st.metric("📏 Avg Precision@5", f"{avg_p5:.1%}")
        else:
            st.metric("📏 Avg Precision@5", "N/A")

    with col4:
        if not metrics_df.empty and "hit_rate" in metrics_df.columns:
            avg_hr = metrics_df["hit_rate"].mean()
            st.metric("🎯 Avg Hit Rate", f"{avg_hr:.1%}")
        else:
            st.metric("🎯 Avg Hit Rate", "N/A")

    st.markdown("---")

    # ── Tabs ───────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏆 Top 5 Picks",
        "📊 Probability Analysis",
        "🏭 Sector Breakdown",
        "📈 Model Performance",
    ])

    # ── Tab 1: Top 5 Picks ────────────────────────────────
    with tab1:
        st.markdown(f"### 🏆 Top 5 Picks for {selected_date}")

        for _, row in day_preds.iterrows():
            rank = int(row.get("rank", 0))
            ticker = row.get("ticker", "N/A")
            prob = row.get("predicted_probability", 0)
            sector = row.get("sector", "N/A")
            industry = row.get("industry", "N/A")
            close = row.get("last_close", row.get("close", 0))
            features = row.get("top_features", "N/A")

            col_rank, col_info, col_prob, col_price = st.columns([1, 4, 2, 2])

            with col_rank:
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
                st.markdown(f"### {medal}")

            with col_info:
                st.markdown(f"**{ticker}**")
                st.caption(f"{sector} · {industry}")
                if features and features != "N/A":
                    st.caption(f"Key factors: {features}")

            with col_prob:
                st.metric("Probability", f"{prob:.1%}")

            with col_price:
                st.metric("Last Close", f"${close:.2f}" if close else "N/A")

            st.markdown("---")

        # Full table
        st.markdown("#### 📋 Full Data Table")
        display_cols = [c for c in ["rank", "ticker", "sector", "industry",
                                     "predicted_probability", "last_close",
                                     "close", "as_of_date", "top_features"]
                       if c in day_preds.columns]
        st.dataframe(
            day_preds[display_cols],
            use_container_width=True,
            hide_index=True,
        )

    # ── Tab 2: Probability Analysis ────────────────────────
    with tab2:
        st.markdown(f"### 📊 Predicted Probabilities — {selected_date}")

        # Use all predictions if available
        chart_df = all_predictions_df[
            all_predictions_df["as_of_date"] == selected_date
        ] if not all_predictions_df.empty else day_preds

        if not chart_df.empty:
            # Top 20 by probability
            top_20 = chart_df.nlargest(20, "predicted_probability")

            fig = px.bar(
                top_20,
                x="ticker",
                y="predicted_probability",
                color="predicted_probability",
                color_continuous_scale=["#302b63", "#7b2ff7", "#00d2ff"],
                title="Top 20 Tickers by Predicted Probability",
                labels={
                    "predicted_probability": "Probability",
                    "ticker": "Ticker",
                },
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter"),
                coloraxis_showscale=False,
                xaxis=dict(categoryorder="total descending"),
            )
            # Highlight top 5
            fig.add_hline(
                y=day_preds["predicted_probability"].min()
                if len(day_preds) > 0 else 0.5,
                line_dash="dash",
                line_color="#ffc107",
                annotation_text="Top 5 cutoff",
            )
            st.plotly_chart(fig, use_container_width=True)

            # Distribution
            fig2 = px.histogram(
                chart_df,
                x="predicted_probability",
                nbins=30,
                title="Probability Distribution (All Scored Tickers)",
                labels={"predicted_probability": "Probability"},
                color_discrete_sequence=["#7b2ff7"],
            )
            fig2.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter"),
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ── Tab 3: Sector Breakdown ────────────────────────────
    with tab3:
        st.markdown(f"### 🏭 Sector Breakdown — {selected_date}")

        if "sector" in day_preds.columns:
            sector_counts = day_preds["sector"].value_counts().reset_index()
            sector_counts.columns = ["Sector", "Count"]

            fig3 = px.pie(
                sector_counts,
                values="Count",
                names="Sector",
                hole=0.4,
                title="Top 5 Picks by Sector",
                color_discrete_sequence=["#7b2ff7", "#00d2ff", "#ff6b6b",
                                          "#ffc107", "#2ed573"],
            )
            fig3.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter"),
            )
            st.plotly_chart(fig3, use_container_width=True)

            # Sector-level probability stats
            if not all_predictions_df.empty and "sector" in all_predictions_df.columns:
                sector_stats = all_predictions_df[
                    all_predictions_df["as_of_date"] == selected_date
                ].groupby("sector").agg(
                    avg_prob=("predicted_probability", "mean"),
                    max_prob=("predicted_probability", "max"),
                    count=("ticker", "count"),
                ).reset_index()

                fig4 = px.bar(
                    sector_stats,
                    x="sector",
                    y="avg_prob",
                    color="sector",
                    title="Average Probability by Sector",
                    labels={"avg_prob": "Avg Probability", "sector": "Sector"},
                    color_discrete_sequence=["#7b2ff7", "#00d2ff", "#ff6b6b",
                                              "#ffc107", "#2ed573"],
                )
                fig4.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter"),
                    showlegend=False,
                )
                st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("Sector data not available")

    # ── Tab 4: Model Performance ───────────────────────────
    with tab4:
        st.markdown("### 📈 Model Performance Over Time")

        if not metrics_df.empty:
            if "as_of_date" in metrics_df.columns:
                metrics_sorted = metrics_df.sort_values("as_of_date")

                # Precision@5 over time
                fig5 = go.Figure()
                fig5.add_trace(go.Scatter(
                    x=metrics_sorted["as_of_date"],
                    y=metrics_sorted["precision_at_5"],
                    mode="lines+markers",
                    name="Precision@5",
                    line=dict(color="#00d2ff", width=2),
                    marker=dict(size=6),
                ))
                fig5.add_trace(go.Scatter(
                    x=metrics_sorted["as_of_date"],
                    y=metrics_sorted["hit_rate"],
                    mode="lines+markers",
                    name="Hit Rate",
                    line=dict(color="#7b2ff7", width=2),
                    marker=dict(size=6),
                ))
                fig5.update_layout(
                    title="Precision@5 and Hit Rate Over Time",
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter"),
                    yaxis=dict(title="Score", range=[0, 1.05]),
                    xaxis=dict(title="Date"),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1,
                    ),
                )
                st.plotly_chart(fig5, use_container_width=True)

                # Rolling averages
                if len(metrics_sorted) >= 5:
                    metrics_sorted["precision_5d_avg"] = (
                        metrics_sorted["precision_at_5"]
                        .rolling(5, min_periods=1).mean()
                    )
                    metrics_sorted["hit_rate_5d_avg"] = (
                        metrics_sorted["hit_rate"]
                        .rolling(5, min_periods=1).mean()
                    )

                    fig6 = go.Figure()
                    fig6.add_trace(go.Scatter(
                        x=metrics_sorted["as_of_date"],
                        y=metrics_sorted["precision_5d_avg"],
                        mode="lines",
                        name="Precision@5 (5-day avg)",
                        line=dict(color="#00d2ff", width=3),
                    ))
                    fig6.add_trace(go.Scatter(
                        x=metrics_sorted["as_of_date"],
                        y=metrics_sorted["hit_rate_5d_avg"],
                        mode="lines",
                        name="Hit Rate (5-day avg)",
                        line=dict(color="#7b2ff7", width=3),
                    ))
                    fig6.update_layout(
                        title="5-Day Rolling Averages",
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="Inter"),
                        yaxis=dict(title="Score", range=[0, 1.05]),
                        xaxis=dict(title="Date"),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1,
                        ),
                    )
                    st.plotly_chart(fig6, use_container_width=True)

                # Summary stats
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Days Evaluated",
                             len(metrics_sorted))
                with col2:
                    st.metric("Avg Precision@5",
                             f"{metrics_sorted['precision_at_5'].mean():.1%}")
                with col3:
                    st.metric("Avg Hit Rate",
                             f"{metrics_sorted['hit_rate'].mean():.1%}")
                with col4:
                    st.metric("Best Precision@5",
                             f"{metrics_sorted['precision_at_5'].max():.1%}")

                # Raw metrics table
                st.markdown("#### 📋 Daily Metrics")
                st.dataframe(
                    metrics_sorted[["as_of_date", "precision_at_5",
                                    "hit_rate", "num_tickers_scored"]],
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.info("No metrics data available. Run the pipeline to generate "
                   "backtest results.")

    # ── Disclaimer ─────────────────────────────────────────
    st.markdown("""
    <div class="disclaimer">
        <strong>⚠️ Disclaimer:</strong> This tool is for educational and portfolio
        demonstration purposes only. It is NOT financial advice. Stock predictions
        are inherently uncertain. Never invest money you cannot afford to lose.
        Past performance does not guarantee future results.
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
