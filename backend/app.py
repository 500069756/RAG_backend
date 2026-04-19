"""
Flask Application Factory — Phase 5
Creates and configures the Flask app with all services wired up.

Usage:
    Development:  python app.py
    Production:   gunicorn "app:create_app()" -w 2 -b 0.0.0.0:$PORT
"""

import logging
import os
import sys

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load environment variables from .env file
load_dotenv()


def create_app() -> Flask:
    """Flask app factory — initializes all services and routes."""

    # ── Logging ──────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger(__name__)

    # ── Flask App ────────────────────────────────────────────
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

    # ── CORS ─────────────────────────────────────────────────
    allowed_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
    CORS(app, origins=allowed_origins, supports_credentials=True)

    # ── Rate Limiting ────────────────────────────────────────
    rate_limit = os.environ.get("RATE_LIMIT_PER_MINUTE", "30")
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[f"{rate_limit}/minute"],
        storage_uri="memory://",
    )

    # ── Initialize Services ──────────────────────────────────
    try:
        from phases.phase_4_2_embedding.embedder import EmbeddingService
        from core.retriever import Retriever
        from phases.phase_5_runtime.guardrails import InputGuardrail, OutputGuardrail
        from phases.phase_5_runtime.pipeline import RAGPipeline
        from phases.phase_5_runtime.session_manager import SessionManager

        # Embedding service (shared for query-time embedding)
        embedding_service = EmbeddingService()

        # Retriever (Chroma Cloud)
        retriever = Retriever(embedding_service=embedding_service)

        # RAG Pipeline (orchestrator with guardrails + Groq)
        pipeline = RAGPipeline(
            embedding_service=embedding_service,
            retriever=retriever
        )

        # Session Manager (chat threads)
        session_manager = SessionManager()

        # Store in app config for route access
        app.config["RAG_PIPELINE"] = pipeline
        app.config["RETRIEVER"] = retriever
        app.config["SESSION_MANAGER"] = session_manager
        app.config["EMBEDDING_SERVICE"] = embedding_service

        logger.info("All Phase 5 services initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize Phase 5 services: {e}")
        logger.warning("App will start in degraded mode — check env vars")

        # Provide minimal stubs so endpoints return proper errors
        from phases.phase_5_runtime.session_manager import SessionManager
        app.config["SESSION_MANAGER"] = SessionManager()
        app.config["RAG_PIPELINE"] = None
        app.config["RETRIEVER"] = None
        app.config["EMBEDDING_SERVICE"] = None

    # ── Register Routes ──────────────────────────────────────
    # Phase 5: Chat API routes
    from phases.phase_5_runtime.routes import chat_bp, init_routes

    # Initialize routes with pipeline and session manager
    # In degraded mode, pipeline will be None and routes will return proper errors
    pipeline = app.config.get("RAG_PIPELINE")
    session_mgr = app.config.get("SESSION_MANAGER")
    
    if pipeline and session_mgr:
        init_routes(pipeline=pipeline, session_mgr=session_mgr)
        logger.info("Phase 5 routes initialized with full pipeline")
    else:
        # Initialize with None to enable error handling in routes
        init_routes(pipeline=None, session_mgr=session_mgr)
        logger.warning("Phase 5 routes initialized in degraded mode (pipeline unavailable)")

    # Register blueprint
    app.register_blueprint(chat_bp)

    # Legacy routes (if needed for backward compatibility)
    try:
        from api.routes import api_bp
        from api.middleware import register_middleware
        register_middleware(app)
        app.register_blueprint(api_bp)
        logger.info("Legacy API routes registered")
    except Exception as e:
        logger.warning(f"Legacy routes not available: {e}")

    logger.info(f"Flask app initialized with Phase 5 (env={os.environ.get('FLASK_ENV', 'development')})")

    return app


# ── Development Server ───────────────────────────────────────

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_ENV") == "development"
    )
