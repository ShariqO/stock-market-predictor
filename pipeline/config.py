"""
pipeline/config.py — Configuration loader

Loads config.yaml and .env, provides typed accessors for all
pipeline settings. Resolves paths based on mode (local vs aws).
"""

import os
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv


# ── Load .env if it exists ─────────────────────────────────
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


def _load_yaml() -> dict:
    """Load and return the config.yaml dictionary."""
    config_path = _project_root / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"config.yaml not found at {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# Singleton config dict
_CONFIG: dict = _load_yaml()


# ── Public accessors ───────────────────────────────────────

def get_mode() -> str:
    """Return current mode: 'local' or 'aws'."""
    return os.getenv("MODE", _CONFIG.get("mode", "local")).lower()


def get_project_root() -> Path:
    """Return the absolute project root path."""
    return _project_root


def get_lake_root() -> Path:
    """Return the absolute path to the local data lake root."""
    raw = _CONFIG.get("local", {}).get("lake_root", "./_lake")
    return (_project_root / raw).resolve()


def get_s3_bucket() -> str:
    """Return S3 bucket name (Phase 2)."""
    return os.getenv("S3_BUCKET", _CONFIG.get("aws", {}).get("s3_bucket", ""))


def get_aws_region() -> str:
    """Return AWS region."""
    return os.getenv("AWS_DEFAULT_REGION",
                      _CONFIG.get("aws", {}).get("region", "us-east-1"))


def get_aws_config() -> dict:
    """Return the full AWS configuration dict."""
    return _CONFIG.get("aws", {})


def get_glue_database() -> str:
    """Return Glue Data Catalog database name."""
    return os.getenv("GLUE_DATABASE",
                      _CONFIG.get("aws", {}).get("glue_database", "stock_predictor"))


def get_ecr_repository() -> str:
    """Return ECR repository name."""
    return os.getenv("ECR_REPOSITORY",
                      _CONFIG.get("aws", {}).get("ecr_repository", "stock-predictor"))


def get_ecs_cluster() -> str:
    """Return ECS cluster name."""
    return os.getenv("ECS_CLUSTER",
                      _CONFIG.get("aws", {}).get("ecs_cluster", "stock-predictor-cluster"))


def get_ecs_task_family() -> str:
    """Return ECS task definition family name."""
    return _CONFIG.get("aws", {}).get("ecs_task_family", "stock-predictor")


def get_log_group() -> str:
    """Return CloudWatch log group name."""
    return _CONFIG.get("aws", {}).get("log_group", "/ecs/stock-predictor")


def get_vpc_subnets() -> list[str]:
    """Return list of VPC subnet IDs for Fargate tasks."""
    raw = os.getenv("VPC_SUBNETS",
                     _CONFIG.get("aws", {}).get("vpc_subnets", ""))
    return [s.strip() for s in raw.split(",") if s.strip()]


def get_security_groups() -> list[str]:
    """Return list of security group IDs for Fargate tasks."""
    raw = os.getenv("SECURITY_GROUP",
                     _CONFIG.get("aws", {}).get("security_groups", ""))
    return [s.strip() for s in raw.split(",") if s.strip()]


def get_universe_config() -> dict:
    """Return ticker universe configuration."""
    return _CONFIG.get("universe", {})


def get_ingestion_config() -> dict:
    """Return ingestion parameters."""
    return _CONFIG.get("ingestion", {})


def get_features_config() -> dict:
    """Return feature engineering parameters."""
    return _CONFIG.get("features", {})


def get_model_config() -> dict:
    """Return ML model parameters."""
    return _CONFIG.get("model", {})


def get_logging_config() -> dict:
    """Return logging configuration."""
    return _CONFIG.get("logging", {})


# ── Path builders ──────────────────────────────────────────

def lake_path(layer: str, dataset: str, dt: str) -> Path:
    """
    Build a data lake path for the given layer/dataset/date.

    Examples:
        lake_path("bronze", "prices", "2024-01-15")
        → <lake_root>/bronze/prices/dt=2024-01-15/
    """
    return get_lake_root() / layer / dataset / f"dt={dt}"


# ── Logger factory ─────────────────────────────────────────

def setup_logger(name: str) -> logging.Logger:
    """Create a consistently formatted logger."""
    log_cfg = get_logging_config()
    level = os.getenv("LOG_LEVEL", log_cfg.get("level", "INFO"))
    fmt = log_cfg.get("format",
                       "%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s")

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger
