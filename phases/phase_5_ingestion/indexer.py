"""
Indexer Service — Phase 4.1
Manages Chroma Cloud collections: upsert, versioning, rollback, cleanup.

Responsibilities:
    - Create date-versioned Chroma collections (mutual_fund_faq_YYYYMMDD)
    - Batch upsert embedded chunks (100 per batch)
    - Promote/rollback collection versions
    - Clean up old versions (keep last 3)

Usage:
    python -m ingestion.indexer --chunks data/chunks/ --collection mutual_fund_faq
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)


class IndexerService:
    """Manages Chroma Cloud collections: upsert, versioning, rollback, cleanup."""

    BASE_COLLECTION = "mutual_fund_faq"
    UPSERT_BATCH_SIZE = 100       # Chroma recommended batch size
    MAX_VERSIONS_KEEP = 3         # Number of collection versions to retain

    def __init__(
        self,
        api_key: str | None = None,
        tenant: str | None = None,
        database: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("CHROMA_API_KEY", "")
        self.tenant = tenant or os.environ.get("CHROMA_TENANT", "")
        self.database = database or os.environ.get("CHROMA_DATABASE", "")
        self.BASE_COLLECTION = os.environ.get(
            "CHROMA_COLLECTION_BASE",
            self.BASE_COLLECTION
        )

        if not all([self.api_key, self.tenant, self.database]):
            raise ValueError(
                "CHROMA_API_KEY, CHROMA_TENANT, and CHROMA_DATABASE are required. "
                "Set them as environment variables."
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

        self.stats = {
            "chunks_upserted": 0,
            "batches": 0,
            "collection_name": None
        }

        logger.info(f"IndexerService connected to Chroma Cloud "
                    f"(tenant={self.tenant}, db={self.database})")

    # ── Collection Management ─────────────────────────────────

    def _versioned_name(self, date: str | None = None) -> str:
        """Generate versioned collection name: mutual_fund_faq_YYYYMMDD"""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{self.BASE_COLLECTION}_{date}"

    def _list_versions(self) -> list[str]:
        """List all versioned collections, sorted by date (oldest first)."""
        all_collections = self.client.list_collections()
        versions = [
            c.name for c in all_collections
            if c.name.startswith(self.BASE_COLLECTION + "_")
        ]
        return sorted(versions)

    def _get_active_collection_name(self) -> str | None:
        """Get the currently active (latest) collection name."""
        versions = self._list_versions()
        return versions[-1] if versions else None

    def create_collection(self, date: str | None = None) -> chromadb.Collection:
        """Create a new versioned collection for today's sync."""
        name = self._versioned_name(date)
        collection = self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )
        self.stats["collection_name"] = name
        logger.info(f"Created collection: {name}")
        return collection

    def get_active_collection(self) -> chromadb.Collection:
        """Get the latest versioned collection for querying."""
        versions = self._list_versions()
        if not versions:
            raise RuntimeError("No indexed collections found in Chroma Cloud!")
        latest = versions[-1]
        logger.info(f"Active collection: {latest}")
        return self.client.get_collection(latest)

    # ── Upsert Operations ─────────────────────────────────────

    def delete_by_source_id(self, collection: chromadb.Collection, source_id: str):
        """Delete all chunks belonging to a specific source_id."""
        logger.info(f"Cleaning up existing chunks for source_id: {source_id}")
        collection.delete(where={"source_id": source_id})

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
                chunk_index, total_chunks, token_count, content_hash

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
        
        logger.info(f"Syncing {len(unique_source_ids)} unique sources to [{collection.name}]")

        # Step 2: Clear out old chunks for these sources (Phase 4.1 Upsert Strategy)
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
                }
                for chunk in batch
            ]

            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

            self.stats["batches"] += 1
            self.stats["chunks_upserted"] += len(batch)

            batch_num = batch_start // self.UPSERT_BATCH_SIZE + 1
            total_batches = (total + self.UPSERT_BATCH_SIZE - 1) // self.UPSERT_BATCH_SIZE
            logger.info(f"  Batch {batch_num}/{total_batches}: "
                        f"upserted {len(batch)} chunks")

        logger.info(f"Upsert complete: {self.stats['chunks_upserted']} chunks "
                    f"in {self.stats['batches']} batches")
        return self.stats["chunks_upserted"]

    # ── Versioning & Rollback ─────────────────────────────────

    def promote_collection(self, collection_name: str) -> bool:
        """
        Promote a versioned collection as the active one.
        Verifies the collection exists and is queryable.
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

    def rollback(self) -> str | None:
        """
        Rollback to the previous collection version.
        Deletes the latest version and returns the previous one.
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

    # ── Summary ───────────────────────────────────────────────

    def log_summary(self):
        """Log indexing run summary."""
        logger.info("=" * 60)
        logger.info("INDEXER SUMMARY")
        logger.info(f"  Collection:      {self.stats['collection_name']}")
        logger.info(f"  Chunks upserted: {self.stats['chunks_upserted']}")
        logger.info(f"  Batches:         {self.stats['batches']}")
        versions = self._list_versions()
        logger.info(f"  Active versions: {len(versions)}")
        for v in versions:
            logger.info(f"    - {v}")
        logger.info("=" * 60)


# ── CLI Entry Point ───────────────────────────────────────────


def main():
    """CLI entry point for the indexer service."""
    parser = argparse.ArgumentParser(
        description="Mutual Fund FAQ Indexer — Chroma Cloud"
    )
    parser.add_argument(
        "--chunks",
        default="data/embedded/",
        help="Directory containing embedded_chunks.json"
    )
    parser.add_argument(
        "--collection",
        default="mutual_fund_faq",
        help="Base collection name"
    )
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="Update the base collection directly instead of versioning"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Load embedded chunks
    chunks_file = Path(args.chunks) / "embedded_chunks.json"
    if not chunks_file.exists():
        logger.error(f"Embedded chunks file not found: {chunks_file}")
        sys.exit(1)

    with open(chunks_file, "r", encoding="utf-8") as f:
        embedded_chunks = json.load(f)

    logger.info(f"Loaded {len(embedded_chunks)} embedded chunks from {chunks_file}")

    # Index
    indexer = IndexerService()
    indexer.BASE_COLLECTION = args.collection

    if args.persistent:
        # Use persistent production collection
        collection = indexer.client.get_or_create_collection(
            name=args.collection,
            metadata={"hnsw:space": "cosine"}
        )
        indexer.stats["collection_name"] = args.collection
    else:
        # Create today's versioned collection
        collection = indexer.create_collection()

    # Upsert all chunks (implements source-based cleanup internally)
    indexer.upsert_chunks(collection, embedded_chunks)

    # Verify & promote (only for versioned mode)
    if not args.persistent:
        if indexer.promote_collection(collection.name):
            indexer.cleanup_old_versions()
        else:
            logger.error("Collection promotion failed — consider rollback")
            sys.exit(1)

    indexer.log_summary()
    logger.info("Indexing complete!")


if __name__ == "__main__":
    main()
