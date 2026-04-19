"""
Flask Application — Simplified RAG backend.
Uses local FAISS index + TF-IDF embeddings + Groq LLM.

Usage:
    Development:  python app.py
    Production:   gunicorn "app:create_app()" -w 2 -b 0.0.0.0:$PORT
"""

import logging
import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()


def create_app() -> Flask:
    """Flask app factory — initializes all services and routes."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

    # CORS
    allowed_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
    CORS(app, origins=allowed_origins, supports_credentials=True)

    # Rate Limiting
    rate_limit = os.environ.get("RATE_LIMIT_PER_MINUTE", "30")
    Limiter(
        get_remote_address,
        app=app,
        default_limits=[f"{rate_limit}/minute"],
        storage_uri="memory://",
    )

    # ── Initialize Services ──────────────────────────────────
    from core.embedder import Embedder
    from core.retriever import Retriever
    from core.ingest import run_ingestion
    from phases.phase_5_runtime.pipeline import RAGPipeline
    from phases.phase_5_runtime.session_manager import SessionManager

    embedder = Embedder()

    # Auto-ingest seed data on first run
    if not embedder._fitted:
        logger.info("No index found — running seed data ingestion...")
        run_ingestion()
        embedder = Embedder()  # reload after ingestion

    retriever = Retriever(embedder=embedder)
    pipeline = RAGPipeline(retriever=retriever)
    session_manager = SessionManager()

    app.config["RAG_PIPELINE"] = pipeline
    app.config["RETRIEVER"] = retriever
    app.config["SESSION_MANAGER"] = session_manager
    app.config["EMBEDDING_SERVICE"] = embedder

    logger.info(
        f"Services ready — {retriever.chunk_count} chunks indexed (FAISS)"
    )

    # ── Register Routes ──────────────────────────────────────
    from phases.phase_5_runtime.routes import chat_bp, init_routes

    init_routes(pipeline=pipeline, session_mgr=session_manager)
    app.register_blueprint(chat_bp)

    # Legacy routes disabled — phase 5 routes handle /api/*

    logger.info(f"Flask app initialized (env={os.environ.get('FLASK_ENV', 'development')})")
    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    try:
        from waitress import serve as waitress_serve
        print(f" * Production server (waitress) running on http://0.0.0.0:{port}")
        waitress_serve(app, host="0.0.0.0", port=port, threads=4)
    except ImportError:
        app.run(host="0.0.0.0", port=port, debug=False)
