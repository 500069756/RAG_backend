"""
Indexer Service — Phase 4.3
Manages Chroma Cloud collections: upsert, versioning, rollback, cleanup.

Responsibilities:
    - Create date-versioned Chroma collections (mutual_fund_faq_YYYYMMDD)
    - Batch upsert embedded chunks (100 per batch)
    - Clean-on-Source-Change strategy (delete old, upsert new)
    - Promote/rollback collection versions
    - Clean up old versions (keep last 3)
    - Quality verification (volume check, metadata scan)

Usage:
    python -m phases.phase_4_3_indexing --mode upsert
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import chromadb

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────


@dataclass
class IndexerStats:
    """Tracks indexing run statistics."""
    chunks_upserted: int = 0
    chunks_deleted: int = 0
    batches: int = 0
    sources_processed: int = 0
    collection_name: Optional[str] = None
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "chunks_upserted": self.chunks_upserted,
            "chunks_deleted": self.chunks_deleted,
            "batches": self.batches,
            "sources_processed": self.sources_processed,
            "collection_name": self.collection_name,
            "elapsed_seconds": round(self.elapsed_seconds, 2)
        }


# ── Indexer Service ─────────────────────────────────────────


class IndexerService:
    """Manages Chroma Cloud collections: upsert, versioning, rollback, cleanup."""

    BASE_COLLECTION = "mutual_fund_faq"
    UPSERT_BATCH_SIZE = 100       # Chroma recommended batch size
    MAX_VERSIONS_KEEP = 3         # Number of collection versions to retain
    VOLUME_CHECK_THRESHOLD = 0.20 # 20% drop triggers failure

    def __init__(
        self,
        api_key: Optional[str] = None,
        tenant: Optional[str] = None,
        database: Optional[str] = None,
        collection_base: Optional[str] = None,
    ):
        """
        Initialize Indexer Service.

        Args:
            api_key: Chroma Cloud API key (or set CHROMA_API_KEY env var)
            tenant: Chroma Cloud tenant (or set CHROMA_TENANT env var)
            database: Chroma Cloud database (or set CHROMA_DATABASE env var)
            collection_base: Base collection name (or set CHROMA_COLLECTION_BASE env var)
        """
        self.api_key = api_key or os.environ.get("CHROMA_API_KEY", "")
        self.tenant = tenant or os.environ.get("CHROMA_TENANT", "")
        self.database = database or os.environ.get("CHROMA_DATABASE", "")
        self.BASE_COLLECTION = collection_base or os.environ.get(
            "CHROMA_COLLECTION_BASE",
            self.BASE_COLLECTION
        )

        if not all([self.api_key, self.tenant, self.database]):
            raise ValueError(
                "CHROMA_API_KEY, CHROMA_TENANT, and CHROMA_DATABASE are required. "
                "Set them as environment variables or pass them to IndexerService()."
            )

        # Connect to Chroma Cloud
        self.client = chromadb.HttpClient(
            host="api.trychroma.com",
            port=443,
            ssl=True,
            headers={"Authorization": f"Bearer {self.api_key}"},
            tenant=self.tenant,
            database=self.database
        )

        self.stats = IndexerStats()

        logger.info(f"IndexerService connected to Chroma Cloud "
                    f"(tenant={self.tenant}, db={self.database}, "
                    f"collection={self.BASE_COLLECTION})")

    # ── Collection Management ─────────────────────────────────

    def _versioned_name(self, date: Optional[str] = None) -> str:
        """
        Generate versioned collection name: mutual_fund_faq_YYYYMMDD

        Args:
            date: Optional date string (YYYYMMDD format)

        Returns:
            Versioned collection name
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{self.BASE_COLLECTION}_{date}"

    def _list_versions(self) -> list[str]:
        """
        List all versioned collections, sorted by date (oldest first).

        Returns:
            List of collection names
        """
        try:
            all_collections = self.client.list_collections()
            versions = [
                c.name for c in all_collections
                if c.name.startswith(self.BASE_COLLECTION + "_")
            ]
            return sorted(versions)
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []

    def _get_active_collection_name(self) -> Optional[str]:
        """Get the currently active (latest) collection name."""
        versions = self._list_versions()
        return versions[-1] if versions else None

    def create_collection(self, date: Optional[str] = None) -> chromadb.Collection:
        """
        Create a new versioned collection for today's sync.

        Args:
            date: Optional date string (YYYYMMDD format)

        Returns:
            Chroma collection object
        """
        name = self._versioned_name(date)
        collection = self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )
        self.stats.collection_name = name
        logger.info(f"Created collection: {name}")
        return collection

    def get_active_collection(self) -> chromadb.Collection:
        """
        Get the latest versioned collection for querying.

        Returns:
            Chroma collection object

        Raises:
            RuntimeError: If no collections exist
        """
        versions = self._list_versions()
        if not versions:
            raise RuntimeError("No indexed collections found in Chroma Cloud!")
        latest = versions[-1]
        logger.info(f"Active collection: {latest}")
        return self.client.get_collection(latest)

    # ── Clean-on-Source-Change Strategy ───────────────────────

    def delete_by_source_id(self, collection: chromadb.Collection, source_id: str) -> int:
        """
        Delete all chunks belonging to a specific source_id.

        Args:
            collection: Chroma collection
            source_id: Source ID to delete

        Returns:
            Number of chunks deleted
        """
        try:
            # Get count before deletion
            before_count = collection.count()

            # Delete by metadata filter
            collection.delete(where={"source_id": source_id})

            # Get count after deletion
            after_count = collection.count()
            deleted = before_count - after_count

            if deleted > 0:
                logger.info(f"  Deleted {deleted} chunks for source_id: {source_id}")
                self.stats.chunks_deleted += deleted

            return deleted
        except Exception as e:
            logger.error(f"Failed to delete source_id {source_id}: {e}")
            return 0

    # ── Upsert Operations ─────────────────────────────────────

    def upsert_chunks(
        self,
        collection: chromadb.Collection,
        embedded_chunks: list[dict]
    ) -> int:
        """
        Batch upsert embedded chunks into a Chroma collection with cleanup.
        Implements the Clean-on-Source-Change strategy.

        Args:
            collection: Target Chroma collection
            embedded_chunks: List of dicts with keys:
                chunk_id, text, embedding, source_url, source_id,
                scheme_name, document_type, category, scraped_at,
                chunk_index, total_chunks, token_count, content_hash,
                embedding_model

        Returns:
            Number of chunks successfully upserted
        """
        if not embedded_chunks:
            logger.info("No chunks to upsert.")
            return 0

        # Step 1: Identify all unique source_ids present in this sync
        unique_source_ids = sorted(list(set(
            chunk["source_id"] for chunk in embedded_chunks if "source_id" in chunk
        )))

        self.stats.sources_processed = len(unique_source_ids)
        logger.info(f"Syncing {len(unique_source_ids)} unique sources to [{collection.name}]")

        # Step 2: Clear out old chunks for these sources (Phase 4.3 Upsert Strategy)
        for sid in unique_source_ids:
            self.delete_by_source_id(collection, sid)

        # Step 3: Batch upsert new chunks
        total = len(embedded_chunks)
        logger.info(f"Upserting {total} new chunks to [{collection.name}] "
                    f"(batch_size={self.UPSERT_BATCH_SIZE})")

        for batch_start in range(0, total, self.UPSERT_BATCH_SIZE):
            batch = embedded_chunks[batch_start:batch_start + self.UPSERT_BATCH_SIZE]

            ids = [chunk["chunk_id"] for chunk in batch]
            embeddings = [chunk["embedding"] for chunk in batch]
            documents = [chunk["text"] for chunk in batch]
            metadatas = [
                {
                    "source_url": chunk.get("source_url", ""),
                    "source_id": chunk.get("source_id", ""),
                    "scheme_name": chunk.get("scheme_name", ""),
                    "document_type": chunk.get("document_type", ""),
                    "category": chunk.get("category", ""),
                    "scraped_at": chunk.get("scraped_at", ""),
                    "chunk_index": chunk.get("chunk_index", 0),
                    "total_chunks": chunk.get("total_chunks", 0),
                    "token_count": chunk.get("token_count", 0),
                    "content_hash": chunk.get("content_hash", ""),
                    "embedding_model": chunk.get("embedding_model", ""),
                }
                for chunk in batch
            ]

            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

            self.stats.batches += 1
            self.stats.chunks_upserted += len(batch)

            batch_num = batch_start // self.UPSERT_BATCH_SIZE + 1
            total_batches = (total + self.UPSERT_BATCH_SIZE - 1) // self.UPSERT_BATCH_SIZE
            logger.info(f"  Batch {batch_num}/{total_batches}: "
                        f"upserted {len(batch)} chunks")

        logger.info(f"Upsert complete: {self.stats.chunks_upserted} chunks "
                    f"in {self.stats.batches} batches")
        return self.stats.chunks_upserted

    # ── Versioning & Rollback ─────────────────────────────────

    def promote_collection(self, collection_name: str) -> bool:
        """
        Promote a versioned collection as the active one.
        Verifies the collection exists and is queryable.

        Args:
            collection_name: Name of collection to promote

        Returns:
            True if promotion successful
        """
        try:
            collection = self.client.get_collection(collection_name)
            count = collection.count()
            logger.info(f"Promoted [{collection_name}] as active "
                        f"({count} documents)")
            return True
        except Exception as e:
            logger.error(f"Failed to promote [{collection_name}]: {e}")
            return False

    def rollback(self) -> Optional[str]:
        """
        Rollback to the previous collection version.
        Deletes the latest version and returns the previous one.

        Returns:
            Previous collection name or None
        """
        versions = self._list_versions()
        if len(versions) < 2:
            logger.error("Cannot rollback: less than 2 versions available")
            return None

        latest = versions[-1]
        previous = versions[-2]

        logger.warning(f"Rolling back: deleting [{latest}], "
                       f"activating [{previous}]")
        self.client.delete_collection(latest)
        return previous

    def cleanup_old_versions(self):
        """Delete old collection versions, keeping only the latest N."""
        versions = self._list_versions()

        if len(versions) <= self.MAX_VERSIONS_KEEP:
            logger.info(f"Cleanup: {len(versions)} versions, "
                        f"nothing to delete (limit={self.MAX_VERSIONS_KEEP})")
            return

        to_delete = versions[:-self.MAX_VERSIONS_KEEP]
        for version_name in to_delete:
            logger.info(f"Cleanup: deleting old collection [{version_name}]")
            self.client.delete_collection(version_name)

        logger.info(f"Cleanup complete: deleted {len(to_delete)} old versions, "
                    f"kept {self.MAX_VERSIONS_KEEP}")

    # ── Quality Verification ──────────────────────────────────

    def verify_collection(self, collection_name: str, previous_count: Optional[int] = None) -> bool:
        """
        Verify collection quality after upsert.

        Checks:
            - Volume check (count didn't drop by more than 20%)
            - Collection is queryable

        Args:
            collection_name: Collection to verify
            previous_count: Count from previous version (for volume check)

        Returns:
            True if verification passed
        """
        try:
            collection = self.client.get_collection(collection_name)
            current_count = collection.count()

            logger.info(f"Verification: [{collection_name}] has {current_count} documents")

            # Volume check
            if previous_count is not None:
                drop_ratio = (previous_count - current_count) / max(previous_count, 1)
                if drop_ratio > self.VOLUME_CHECK_THRESHOLD:
                    logger.error(f"Volume check FAILED: {drop_ratio*100:.1f}% drop "
                                 f"(threshold: {self.VOLUME_CHECK_THRESHOLD*100}%)")
                    return False
                else:
                    logger.info(f"Volume check PASSED: {drop_ratio*100:.1f}% change")

            # Test query
            collection.query(
                query_embeddings=[[0.0] * 384],  # Dummy vector
                n_results=1
            )
            logger.info("Query test PASSED")

            return True

        except Exception as e:
            logger.error(f"Verification FAILED: {e}")
            return False

    # ── Summary ───────────────────────────────────────────────

    def log_summary(self):
        """Log indexing run summary."""
        logger.info("=" * 60)
        logger.info("INDEXER SUMMARY")
        logger.info(f"  Collection:      {self.stats.collection_name}")
        logger.info(f"  Chunks upserted: {self.stats.chunks_upserted}")
        logger.info(f"  Chunks deleted:  {self.stats.chunks_deleted}")
        logger.info(f"  Sources syncd:   {self.stats.sources_processed}")
        logger.info(f"  Batches:         {self.stats.batches}")
        logger.info(f"  Elapsed time:    {self.stats.elapsed_seconds:.2f}s")
        versions = self._list_versions()
        logger.info(f"  Active versions: {len(versions)}")
        for v in versions:
            logger.info(f"    - {v}")
        logger.info("=" * 60)


# ── CLI Entry Point ───────────────────────────────────────────


def main():
    """CLI entry point for the indexer service."""
    parser = argparse.ArgumentParser(
        description="Phase 4.3 — Mutual Fund FAQ Indexer (Chroma Cloud)"
    )
    parser.add_argument(
        "--mode",
        choices=["upsert", "verify", "cleanup", "rollback"],
        default="upsert",
        help="Indexer mode (default: upsert)"
    )
    parser.add_argument(
        "--input",
        default="data/embedded/",
        help="Directory containing embedded_chunks.json"
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Base collection name (default: from env CHROMA_COLLECTION_BASE)"
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Collection date (YYYYMMDD format, default: today)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Initialize indexer
    try:
        indexer = IndexerService(collection_base=args.collection)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Execute mode
    if args.mode == "upsert":
        # Load embedded chunks
        chunks_file = Path(args.input) / "embedded_chunks.json"
        if not chunks_file.exists():
            logger.error(f"Embedded chunks file not found: {chunks_file}")
            sys.exit(1)

        with open(chunks_file, "r", encoding="utf-8") as f:
            embedded_chunks = json.load(f)

        logger.info(f"Loaded {len(embedded_chunks)} embedded chunks from {chunks_file}")

        # Get previous count for verification
        previous_collection = indexer._get_active_collection_name()
        previous_count = None
        if previous_collection:
            try:
                prev_coll = indexer.client.get_collection(previous_collection)
                previous_count = prev_coll.count()
                logger.info(f"Previous collection [{previous_collection}] has {previous_count} docs")
            except Exception as e:
                logger.warning(f"Could not get previous count: {e}")

        # Create today's versioned collection
        collection = indexer.create_collection(date=args.date)

        # Upsert all chunks (implements source-based cleanup internally)
        indexer.upsert_chunks(collection, embedded_chunks)

        # Verify & promote
        if indexer.verify_collection(collection.name, previous_count):
            if indexer.promote_collection(collection.name):
                indexer.cleanup_old_versions()
            else:
                logger.error("Collection promotion failed — consider rollback")
                sys.exit(1)
        else:
            logger.error("Collection verification failed — rolling back")
            indexer.rollback()
            sys.exit(1)

    elif args.mode == "verify":
        active = indexer._get_active_collection_name()
        if not active:
            logger.error("No active collection found")
            sys.exit(1)
        
        if indexer.verify_collection(active):
            logger.info(f"Collection [{active}] verification PASSED")
        else:
            logger.error(f"Collection [{active}] verification FAILED")
            sys.exit(1)

    elif args.mode == "cleanup":
        indexer.cleanup_old_versions()

    elif args.mode == "rollback":
        previous = indexer.rollback()
        if previous:
            logger.info(f"Rolled back to: {previous}")
        else:
            logger.error("Rollback failed")
            sys.exit(1)

    indexer.log_summary()
    logger.info("Indexing complete!")


if __name__ == "__main__":
    main()
