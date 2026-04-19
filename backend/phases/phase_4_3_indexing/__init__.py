"""
Phase 4.3 — Indexer Service (Vector DB Upsert)

Manages Chroma Cloud collections: upsert, versioning, rollback, cleanup.

Responsibilities:
    - Create date-versioned Chroma collections (mutual_fund_faq_YYYYMMDD)
    - Batch upsert embedded chunks (100 per batch)
    - Clean-on-Source-Change strategy (delete old, upsert new)
    - Promote/rollback collection versions
    - Clean up old versions (keep last 3)

Usage:
    python -m phases.phase_4_3_indexing --mode upsert
"""

from .indexer import IndexerService

__all__ = ["IndexerService"]
