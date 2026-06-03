# ============================================================
# NASDAQ Day Trading Predictor — Dockerfile
# ============================================================
# Multi-stage build for the prediction pipeline.
# Supports running individual jobs or the full orchestrator.
#
# Usage:
#   docker build -t stock-predictor .
#   docker run stock-predictor python main_orchestrator.py
#   docker run stock-predictor python jobs/job_ingest_prices.py
# ============================================================

FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY config.yaml .
COPY main_orchestrator.py .
COPY pipeline/ pipeline/
COPY jobs/ jobs/
COPY dashboard/ dashboard/

# Create data lake directory
RUN mkdir -p _lake

# Default command: run the full pipeline
CMD ["python", "main_orchestrator.py"]
