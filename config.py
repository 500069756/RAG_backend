"""Backend configuration — loads from environment variables."""

import os
from pathlib import Path

# ── Base Paths ────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = DATA_DIR / "index"

# ── LLM (Groq) ───────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL_PRIMARY = "llama-3.3-70b-versatile"
GROQ_MODEL_FALLBACK = "llama-3.3-8b-instant"
GROQ_TEMPERATURE = 0.1
GROQ_MAX_TOKENS = 300

# ── Flask ─────────────────────────────────────────────────
FLASK_ENV = os.environ.get("FLASK_ENV", "development")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
# ── Frontend URL ──────────────────────────────────────────
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
# ── Rate Limiting ─────────────────────────────────────────
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30"))
