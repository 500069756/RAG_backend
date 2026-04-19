"""
Chat API Routes — Phase 5.3
Flask REST API endpoints for the RAG chat assistant.

Endpoints:
    POST /api/chat          - Send a message (with thread support)
    GET  /api/threads       - List all threads
    GET  /api/threads/<id>/messages - Get thread message history
    DELETE /api/threads/<id> - Delete a thread
    GET  /api/health        - Health check
"""

import logging
import os

from flask import Blueprint, jsonify, request

from phases.phase_5_runtime.guardrails import validate_input
from phases.phase_5_runtime.pipeline import RAGPipeline
from phases.phase_5_runtime.session_manager import SessionManager

logger = logging.getLogger(__name__)

# Create blueprint
chat_bp = Blueprint("chat", __name__, url_prefix="/api")

# Global instances (initialized in app.py)
rag_pipeline: RAGPipeline = None
session_manager: SessionManager = None


def init_routes(pipeline: RAGPipeline, session_mgr: SessionManager):
    """Initialize routes with pipeline and session manager instances."""
    global rag_pipeline, session_manager
    rag_pipeline = pipeline
    session_manager = session_mgr
    logger.info("Chat API routes initialized")


# ── POST /api/chat ──────────────────────────────────────────────

@chat_bp.route("/chat", methods=["POST"])
def chat():
    """
    Send a message within a chat thread.
    
    Request JSON:
    {
        "thread_id": "uuid-string" (optional),
        "message": "What is the expense ratio of HDFC Top 100 Fund?",
        "scheme_filter": "HDFC Top 100 Fund" (optional),
        "category_filter": "large-cap" (optional)
    }
    
    Response JSON:
    {
        "thread_id": "uuid-string",
        "response": "The expense ratio is...",
        "source_url": "https://...",
        "last_updated": "2026-04-19",
        "is_refusal": false,
        "confidence_score": 0.87,
        "processing_time_ms": 1250
    }
    """
    try:
        # Check if pipeline is initialized
        if rag_pipeline is None:
            return jsonify({
                "error": "RAG pipeline not initialized. Check HF_API_TOKEN and other environment variables.",
                "response": "The service is currently unavailable. Please ensure all API keys are configured in the .env file.",
                "is_refusal": True,
                "confidence_score": 0.0
            }), 503

        data = request.get_json()
        if not data or "message" not in data:
            return jsonify({"error": "Missing 'message' field"}), 400

        user_message = data["message"].strip()
        if not user_message:
            return jsonify({"error": "Message cannot be empty"}), 400

        # Get or create thread
        if session_manager is None:
            return jsonify({"error": "Session manager not initialized"}), 503
            
        thread_id = data.get("thread_id")
        thread = session_manager.get_or_create_thread(thread_id)

        # Add user message to thread
        session_manager.add_message(
            thread_id=thread.thread_id,
            role="user",
            content=user_message
        )

        # Execute RAG pipeline
        result = rag_pipeline.query(
            user_query=user_message,
            scheme_filter=data.get("scheme_filter"),
            category_filter=data.get("category_filter")
        )

        # Add assistant response to thread
        session_manager.add_message(
            thread_id=thread.thread_id,
            role="assistant",
            content=result.response,
            source_url=result.source_url,
            is_refusal=result.is_refusal,
            confidence_score=result.confidence_score
        )

        # Return response
        return jsonify({
            "thread_id": thread.thread_id,
            "response": result.response,
            "source_url": result.source_url,
            "last_updated": result.last_updated,
            "is_refusal": result.is_refusal,
            "confidence_score": result.confidence_score,
            "processing_time_ms": round(result.processing_time_ms, 2),
            "chunks_used": result.chunks_used
        })

    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        return jsonify({
            "error": "Internal server error",
            "detail": str(e)
        }), 500


# ── GET /api/threads ───────────────────────────────────────────

@chat_bp.route("/threads", methods=["GET"])
def list_threads():
    """
    List all active chat threads.
    
    Response JSON:
    {
        "threads": [
            {
                "thread_id": "uuid",
                "title": "HDFC Top 100 Expense Ratio",
                "created_at": "2026-04-19T10:00:00Z",
                "message_count": 3,
                "last_message_at": "2026-04-19T10:05:00Z"
            }
        ]
    }
    """
    try:
        threads = session_manager.get_threads()
        return jsonify({
            "threads": [
                {
                    "thread_id": t.thread_id,
                    "title": t.title,
                    "created_at": t.created_at,
                    "message_count": t.message_count,
                    "last_message_at": t.last_message_at
                }
                for t in threads
            ]
        })

    except Exception as e:
        logger.error(f"List threads error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


# ── GET /api/threads/<thread_id>/messages ──────────────────────

@chat_bp.route("/threads/<thread_id>/messages", methods=["GET"])
def get_thread_messages(thread_id: str):
    """
    Get full message history for a thread.
    
    Response JSON:
    {
        "thread_id": "uuid",
        "messages": [
            {
                "role": "user",
                "content": "What is the expense ratio?",
                "timestamp": "2026-04-19T10:00:00Z"
            },
            {
                "role": "assistant",
                "content": "The expense ratio is...",
                "source_url": "https://...",
                "is_refusal": false,
                "timestamp": "2026-04-19T10:00:02Z"
            }
        ]
    }
    """
    try:
        messages = session_manager.get_thread_messages(thread_id)
        if not messages:
            return jsonify({"error": "Thread not found"}), 404

        return jsonify({
            "thread_id": thread_id,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "source_url": msg.source_url,
                    "is_refusal": msg.is_refusal,
                    "confidence_score": msg.confidence_score
                }
                for msg in messages
            ]
        })

    except Exception as e:
        logger.error(f"Get messages error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


# ── DELETE /api/threads/<thread_id> ────────────────────────────

@chat_bp.route("/threads/<thread_id>", methods=["DELETE"])
def delete_thread(thread_id: str):
    """
    Delete a chat thread and all its messages.
    
    Response JSON:
    {
        "success": true,
        "message": "Thread deleted"
    }
    """
    try:
        deleted = session_manager.delete_thread(thread_id)
        if not deleted:
            return jsonify({"error": "Thread not found"}), 404

        return jsonify({
            "success": True,
            "message": "Thread deleted successfully"
        })

    except Exception as e:
        logger.error(f"Delete thread error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


# ── GET /api/health ────────────────────────────────────────────

@chat_bp.route("/health", methods=["GET"])
def health_check():
    """
    Health check endpoint for monitoring.
    
    Response JSON:
    {
        "status": "healthy",
        "chroma": "connected",
        "groq": "reachable",
        "hf": "reachable",
        "version": "1.0.0"
    }
    """
    try:
        # Check if services are initialized
        if rag_pipeline is None or session_manager is None:
            return jsonify({
                "status": "degraded",
                "message": "RAG pipeline not initialized. Check environment variables.",
                "version": "1.0.0",
                "threads_active": 0
            }), 503

        faiss_status = "ready"
        chunks_indexed = 0
        try:
            chunks_indexed = rag_pipeline.retriever.chunk_count
            if chunks_indexed == 0:
                faiss_status = "empty"
        except Exception as e:
            faiss_status = f"error: {str(e)[:50]}"

        return jsonify({
            "status": "healthy",
            "vector_store": "faiss",
            "faiss": faiss_status,
            "chunks_indexed": chunks_indexed,
            "version": "1.0.0",
            "threads_active": len(session_manager.threads)
        })

    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return jsonify({
            "status": "degraded",
            "error": str(e)
        }), 503


# ── Error Handlers ─────────────────────────────────────────────

@chat_bp.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad request", "detail": str(error)}), 400


@chat_bp.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@chat_bp.errorhandler(429)
def rate_limit(error):
    return jsonify({"error": "Rate limited", "retry_after": 60}), 429


@chat_bp.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500
