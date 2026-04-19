"""
API Middleware — Phase 9
Request/response middleware for logging, error handling, and rate limiting.
"""

import logging
import time
import uuid

from flask import Flask, request, g, jsonify

logger = logging.getLogger(__name__)


def register_middleware(app: Flask):
    """Register all middleware with the Flask app."""

    @app.before_request
    def before_request():
        """Log incoming requests and set request metadata."""
        g.request_id = str(uuid.uuid4())[:8]
        g.start_time = time.time()
        logger.info(f"[{g.request_id}] {request.method} {request.path}")

    @app.after_request
    def after_request(response):
        """Log response and add headers."""
        latency = int((time.time() - g.get("start_time", time.time())) * 1000)
        logger.info(f"[{g.get('request_id', '?')}] "
                    f"{response.status_code} ({latency}ms)")

        # Add latency header
        response.headers["X-Request-Id"] = g.get("request_id", "")
        response.headers["X-Response-Time"] = f"{latency}ms"
        return response

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Invalid request", "detail": str(e)}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"error": "Rate limited", "retry_after": 60}), 429

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal error: {e}", exc_info=True)
        return jsonify({
            "error": "Internal error",
            "request_id": g.get("request_id", ""),
        }), 500

    @app.errorhandler(503)
    def service_unavailable(e):
        return jsonify({
            "error": "Service unavailable",
            "detail": "External service (Groq/Chroma/HF) is temporarily unavailable"
        }), 503
