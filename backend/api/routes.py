"""
API Routes — Phase 9
Flask route definitions for the Mutual Fund FAQ API.

Endpoints:
    POST /api/chat                      — Send a message
    GET  /api/threads                   — List threads
    GET  /api/threads/<id>/messages     — Get thread messages
    DELETE /api/threads/<id>            — Delete a thread
    GET  /api/health                    — Health check
    POST /api/ingest/trigger            — Manual re-ingestion (admin)
"""

import logging
import os
import uuid

from flask import Blueprint, request, jsonify, g

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _get_session_id() -> str:
    """Extract or create a session ID from cookies."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
    g.session_id = session_id
    return session_id


# ── POST /api/chat ───────────────────────────────────────────


@api_bp.route("/chat", methods=["POST"])
def chat():
    """
    Send a message and get a RAG-powered response.

    Request body:
        {
            "thread_id": "uuid-string" (optional, creates new thread if missing),
            "message": "What is the expense ratio of HDFC Top 100 Fund?"
        }
    """
    from flask import current_app

    data = request.get_json(silent=True)
    if not data or "message" not in data:
        return jsonify({"error": "Invalid request", "detail": "Missing 'message' field"}), 400

    message = data["message"].strip()
    if not message:
        return jsonify({"error": "Invalid request", "detail": "Message cannot be empty"}), 400

    if len(message) > 500:
        return jsonify({"error": "Invalid request", "detail": "Message too long (max 500 chars)"}), 400

    thread_id = data.get("thread_id") or str(uuid.uuid4())
    session_id = _get_session_id()

    # Get services from app context
    pipeline = current_app.config["RAG_PIPELINE"]
    session_store = current_app.config["SESSION_STORE"]

    # Store user message
    session_store.add_message(session_id, thread_id, "user", message)

    # Get conversation history for context
    history = session_store.get_conversation_history(session_id, thread_id)

    # Process through RAG pipeline
    result = pipeline.process_query(
        query=message,
        thread_id=thread_id,
        conversation_history=history[:-1]  # Exclude current message
    )

    # Store assistant response
    session_store.add_message(
        session_id, thread_id, "assistant",
        content=result["response"],
        source_url=result.get("source_url"),
        is_refusal=result.get("is_refusal", False)
    )

    response = jsonify(result)
    response.set_cookie("session_id", session_id, httponly=True, samesite="Lax", max_age=86400 * 7)
    return response


# ── GET /api/threads ─────────────────────────────────────────


@api_bp.route("/threads", methods=["GET"])
def list_threads():
    """List all chat threads for the current session."""
    from flask import current_app

    session_id = _get_session_id()
    session_store = current_app.config["SESSION_STORE"]
    threads = session_store.list_threads(session_id)
    return jsonify({"threads": threads})


# ── GET /api/threads/<thread_id>/messages ────────────────────


@api_bp.route("/threads/<thread_id>/messages", methods=["GET"])
def get_messages(thread_id):
    """Get full message history for a thread."""
    from flask import current_app

    session_id = _get_session_id()
    session_store = current_app.config["SESSION_STORE"]
    messages = session_store.get_messages(session_id, thread_id)

    if not messages:
        return jsonify({"error": "Thread not found"}), 404

    return jsonify({
        "thread_id": thread_id,
        "messages": messages
    })


# ── DELETE /api/threads/<thread_id> ──────────────────────────


@api_bp.route("/threads/<thread_id>", methods=["DELETE"])
def delete_thread(thread_id):
    """Delete a chat thread and all its messages."""
    from flask import current_app

    session_id = _get_session_id()
    session_store = current_app.config["SESSION_STORE"]
    deleted = session_store.delete_thread(session_id, thread_id)

    if not deleted:
        return jsonify({"error": "Thread not found"}), 404

    return jsonify({"deleted": True, "thread_id": thread_id})


# ── GET /api/health ──────────────────────────────────────────


@api_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Render deployment."""
    status = {
        "status": "healthy",
        "version": "1.0.0",
    }

    # Check Chroma connectivity
    try:
        from flask import current_app
        retriever = current_app.config.get("RETRIEVER")
        if retriever:
            retriever._get_collection()
            status["chroma"] = "connected"
        else:
            status["chroma"] = "not_configured"
    except Exception as e:
        status["chroma"] = f"error: {str(e)[:50]}"
        status["status"] = "degraded"

    return jsonify(status)


# ── POST /api/ingest/trigger ─────────────────────────────────


@api_bp.route("/ingest/trigger", methods=["POST"])
def trigger_ingest():
    """Manually trigger re-ingestion (admin only)."""
    auth = request.headers.get("Authorization", "")
    admin_key = os.environ.get("ADMIN_API_KEY", "")

    if not admin_key or auth != f"Bearer {admin_key}":
        return jsonify({"error": "Unauthorized"}), 401

    # Refresh the retriever's collection cache
    from flask import current_app
    retriever = current_app.config.get("RETRIEVER")
    if retriever:
        retriever.refresh_collection()

    return jsonify({
        "status": "triggered",
        "detail": "Collection cache refreshed. Run GitHub Actions for full re-ingestion."
    })
