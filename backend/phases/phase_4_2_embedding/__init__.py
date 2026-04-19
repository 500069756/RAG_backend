"""
Phase 4.2 — Embedding Service

Converts text chunks into dense vector representations using HuggingFace Inference API.

Responsibilities:
    - Batch embedding at index time (daily sync via GitHub Actions)
    - Single embedding at query time (user requests via Flask)
    - SHA-256+model-keyed disk cache to avoid re-embedding unchanged chunks
    - Retry with exponential backoff for rate limits and model loading
    - Model consistency enforcement (same model for index + query)

Usage:
    python -m phases.phase_4_2_embedding --input data/chunks/ --output data/embedded/
"""

from .embedder import EmbeddingService

__all__ = ["EmbeddingService"]
