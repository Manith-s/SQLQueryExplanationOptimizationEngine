"""
Application configuration management.
Loads settings from environment variables (via .env if present).
"""

import os
from typing import List
from dotenv import load_dotenv

# Load .env once at import time (real OS env still wins if set)
load_dotenv(override=False)


class Settings:
    # Application environment
    APP_ENV: str = os.getenv("APP_ENV", "development")

    # Database configuration (match your .env scheme)
    # Keep the +psycopg2 so SQLAlchemy knows the driver;
    # when using raw psycopg2, we'll strip the +psycopg2.
    DB_URL: str = os.getenv(
        "DB_URL",
        "postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt",
    )

    # LLM configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "dummy")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "llama2")
    LLM_TIMEOUT_S: int = int(os.getenv("LLM_TIMEOUT_S", "30"))
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # API configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_KEY: str = os.getenv("API_KEY", "dev-key-12345")
    AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() == "true"

    # Development settings
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Optimizer configuration
    OPT_MIN_ROWS_FOR_INDEX: int = int(os.getenv("OPT_MIN_ROWS_FOR_INDEX", "10000"))
    OPT_MAX_INDEX_COLS: int = int(os.getenv("OPT_MAX_INDEX_COLS", "3"))
    OPT_ALLOW_COVERING: bool = os.getenv("OPT_ALLOW_COVERING", "false").lower() == "true"
    OPT_ALLOW_PARTIAL: bool = os.getenv("OPT_ALLOW_PARTIAL", "false").lower() == "true"
    OPT_TOP_K: int = int(os.getenv("OPT_TOP_K", "10"))
    OPT_ANALYZE_DEFAULT: bool = os.getenv("OPT_ANALYZE_DEFAULT", "false").lower() == "true"
    OPT_TIMEOUT_MS_DEFAULT: int = int(os.getenv("OPT_TIMEOUT_MS_DEFAULT", "10000"))

    # Advanced index advisor (EPIC A)
    OPT_SUPPRESS_LOW_GAIN_PCT: float = float(os.getenv("OPT_SUPPRESS_LOW_GAIN_PCT", "5"))
    OPT_INDEX_MAX_WIDTH_BYTES: int = int(os.getenv("OPT_INDEX_MAX_WIDTH_BYTES", "8192"))
    OPT_JOIN_COL_PRIOR_BOOST: float = float(os.getenv("OPT_JOIN_COL_PRIOR_BOOST", "1.2"))

    # Metrics configuration
    METRICS_ENABLED: bool = os.getenv("METRICS_ENABLED", "false").lower() == "true"
    METRICS_NAMESPACE: str = os.getenv("METRICS_NAMESPACE", "qeo")
    METRICS_BUCKETS: str = os.getenv("METRICS_BUCKETS", "0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2,5")

    # What-if (HypoPG) evaluator configuration
    WHATIF_ENABLED: bool = os.getenv("WHATIF_ENABLED", "false").lower() == "true"
    WHATIF_MAX_TRIALS: int = int(os.getenv("WHATIF_MAX_TRIALS", "10"))
    WHATIF_MIN_COST_REDUCTION_PCT: float = float(os.getenv("WHATIF_MIN_COST_REDUCTION_PCT", "5"))
    WHATIF_PARALLELISM: int = int(os.getenv("WHATIF_PARALLELISM", "2"))
    WHATIF_TRIAL_TIMEOUT_MS: int = int(os.getenv("WHATIF_TRIAL_TIMEOUT_MS", "4000"))
    WHATIF_GLOBAL_TIMEOUT_MS: int = int(os.getenv("WHATIF_GLOBAL_TIMEOUT_MS", "12000"))
    WHATIF_EARLY_STOP_PCT: float = float(os.getenv("WHATIF_EARLY_STOP_PCT", "2"))

    # Caching / pooling / workload
    CACHE_SCHEMA_TTL_S: int = int(os.getenv("CACHE_SCHEMA_TTL_S", "60"))
    WORKLOAD_MAX_INDEXES: int = int(os.getenv("WORKLOAD_MAX_INDEXES", "5"))
    NL_CACHE_ENABLED: bool = os.getenv("NL_CACHE_ENABLED", "true").lower() == "true"
    POOL_MINCONN: int = int(os.getenv("POOL_MINCONN", "1"))
    POOL_MAXCONN: int = int(os.getenv("POOL_MAXCONN", "5"))

    # SQL Linting configuration
    LARGE_TABLE_PATTERNS: List[str] = [
        s.strip() for s in os.getenv(
            "LARGE_TABLE_PATTERNS",
            "events,logs,transactions,fact_*,audit_*,metrics,analytics",
        ).split(",") if s.strip()
    ]

    NUMERIC_COLUMN_PATTERNS: List[str] = [
        s.strip() for s in os.getenv(
            "NUMERIC_COLUMN_PATTERNS",
            "_id,count,amount,price,quantity,score,rating",
        ).split(",") if s.strip()
    ]

    # ---- Convenience helpers ----
    @property
    def db_url_sqlalchemy(self) -> str:
        """Use this if you connect via SQLAlchemy/async engines."""
        return self.DB_URL

    @property
    def db_url_psycopg(self) -> str:
        """Use this if you call psycopg2.connect() directly."""
        return self.DB_URL.replace("postgresql+psycopg2://", "postgresql://")


settings = Settings()
