"""
CapEx Intelligence Platform - Configuration
All settings, company definitions, and environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / "backend" / ".env")

# ---------------------------------------------------------------------------
# API KEYS
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "CapExIntel/1.0 (team@example.com)")

# ---------------------------------------------------------------------------
# LLM PROVIDER  ("openai" or "anthropic")
# Auto-detected from available API keys if not explicitly set.
# ---------------------------------------------------------------------------
def _default_provider() -> str:
    explicit = os.getenv("LLM_PROVIDER", "")
    if explicit:
        return explicit
    if os.getenv("ANTHROPIC_API_KEY", ""):
        return "anthropic"
    return "openai"

LLM_PROVIDER = _default_provider()

# ---------------------------------------------------------------------------
# MODEL CONFIG
# ---------------------------------------------------------------------------
# OpenAI models
LLM_MODEL = "gpt-4o"
RERANK_MODEL = "gpt-4o-mini"

# Anthropic models (used when LLM_PROVIDER="anthropic")
ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_RERANK_MODEL = "claude-haiku-4-5-20251001"

# Embedding model (local, free)
EMBEDDING_MODEL = "all-mpnet-base-v2"

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
CHROMADB_PATH = str(BASE_DIR / "chromadb_store")
DATA_DIR = BASE_DIR / "data"

# ---------------------------------------------------------------------------
# WEB SEARCH
# ---------------------------------------------------------------------------
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
WEB_SEARCH_RESULTS = 5

# ---------------------------------------------------------------------------
# ANALYTICS THRESHOLDS
# ---------------------------------------------------------------------------
ANOMALY_THRESHOLD = 0.20
SENTIMENT_SHIFT_THRESHOLD = 0.3

# ---------------------------------------------------------------------------
# SCHEDULER
# ---------------------------------------------------------------------------
INGESTION_SCHEDULE = os.getenv("INGESTION_SCHEDULE", "0 16 * * 1-5")

# ---------------------------------------------------------------------------
# COMPANY DEFINITIONS
# ---------------------------------------------------------------------------
COMPANIES = {
    "FLEX": {
        "name": "Flex Ltd",
        "cik": "0000866374",
        "sector": "EMS",
        "description": "Global electronics manufacturing services provider",
    },
    "JBL": {
        "name": "Jabil Inc",
        "cik": "0000898293",
        "sector": "EMS",
        "description": "Worldwide manufacturing services and solutions provider",
    },
    "CLS": {
        "name": "Celestica Inc",
        "cik": "0001030894",
        "sector": "EMS",
        "description": "Global provider of electronics manufacturing services",
    },
    "BHE": {
        "name": "Benchmark Electronics",
        "cik": "0001080020",
        "sector": "EMS",
        "description": "Provider of integrated electronics manufacturing services",
    },
    "SANM": {
        "name": "Sanmina Corporation",
        "cik": "0000897723",
        "sector": "EMS",
        "description": "Global electronics manufacturing services company",
    },
    "PLXS": {
        "name": "Plexus Corp",
        "cik": "0000785786",
        "sector": "EMS",
        "description": "Global product design, manufacturing, and aftermarket services provider",
    },
}

TRACKED_COMPANY_NAMES = [company["name"].split()[0] for company in COMPANIES.values()]

COMPANY_NAME_TO_TICKER = {
    "Flex": "FLEX",
    "Jabil": "JBL",
    "Celestica": "CLS",
    "Benchmark": "BHE",
    "Sanmina": "SANM",
    "Plexus": "PLXS",
}
