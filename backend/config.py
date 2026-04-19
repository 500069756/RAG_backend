"""
Backend configuration — loads from environment variables.
Shared across all services (scraper, embedder, indexer, Flask API).
"""

import os
from pathlib import Path

# ── Base Paths ────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SCRAPED_DIR = DATA_DIR / "scraped"
CHUNKS_DIR = DATA_DIR / "chunks"
EMBEDDINGS_CACHE_DIR = DATA_DIR / "embeddings_cache"

# ── Phase 1: Corpus Registry ──────────────────────────────
PHASE_1_DIR = BASE_DIR / "phases" / "phase_1_corpus"
SOURCES_JSON = PHASE_1_DIR / "sources.json"
TEST_QUERIES_JSON = PHASE_1_DIR / "test_queries.json"

# ── LLM (Groq) ───────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL_PRIMARY = "llama-3.3-70b-versatile"
GROQ_MODEL_FALLBACK = "llama-3.3-8b-instant"
GROQ_TEMPERATURE = 0.1
GROQ_MAX_TOKENS = 300

# ── Vector DB (Chroma Cloud) ─────────────────────────────
CHROMA_API_KEY = os.environ.get("CHROMA_API_KEY", "")
CHROMA_TENANT = os.environ.get("CHROMA_TENANT", "")
CHROMA_DATABASE = os.environ.get("CHROMA_DATABASE", "")
CHROMA_COLLECTION_BASE = os.environ.get("CHROMA_COLLECTION_BASE", "mutual_fund_faq")

# ── Embeddings (HuggingFace) ─────────────────────────────
HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "")
HF_EMBEDDING_MODEL = os.environ.get(
    "HF_EMBEDDING_MODEL",
    "BAAI/bge-small-en-v1.5"
)

# ── Flask ─────────────────────────────────────────────────
FLASK_ENV = os.environ.get("FLASK_ENV", "development")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")

# ── Rate Limiting ─────────────────────────────────────────
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30"))

# ── Scraper Settings ─────────────────────────────────────
SCRAPER_REQUEST_TIMEOUT = 30        # seconds
SCRAPER_RATE_LIMIT_DELAY = 2.0      # seconds between requests
SCRAPER_MAX_RETRIES = 3
SCRAPER_RETRY_BACKOFF = [2, 5, 10]  # seconds
SCRAPER_MAX_PDF_SIZE_MB = 50
SCRAPER_MIN_CONTENT_LENGTH = 50
SCRAPER_USER_AGENT = "MutualFundFAQ-Bot/1.0 (+https://github.com/yourrepo)"
