"""
Phase 4.1 — Chunking Service

Splits scraped text into semantically meaningful chunks with enriched metadata.

Responsibilities:
    - Document-type-aware splitting (factsheet, SID, FAQ, guide)
    - QA-pair detection for FAQ pages
    - Chunk validation (min/max length, content quality)
    - Metadata enrichment (source_url, scheme, category, etc.)
    - SHA-256 deduplication

Usage:
    python -m phases.phase_4_1_chunking --input data/scraped/ --output data/chunks/
"""

from .chunker import ChunkingService, Chunk

__all__ = ["ChunkingService", "Chunk"]
