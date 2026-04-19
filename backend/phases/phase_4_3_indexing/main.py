"""
Phase 4.3 — Main Entry Point
Orchestrates the indexing pipeline from embedded chunks to Chroma Cloud.

Usage:
    # Upsert embedded chunks to Chroma Cloud
    python -m phases.phase_4_3_indexing --mode upsert

    # Verify active collection
    python -m phases.phase_4_3_indexing --mode verify

    # Cleanup old versions
    python -m phases.phase_4_3_indexing --mode cleanup

    # Rollback to previous version
    python -m phases.phase_4_3_indexing --mode rollback
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from phases.phase_4_3_indexing.indexer import IndexerService

logger = logging.getLogger(__name__)


class Phase4_3_Pipeline:
    """Orchestrates Phase 4.3: Indexing pipeline."""

    def __init__(
        self,
        input_dir: str = "data/embedded/",
        collection_base: str = None,
        date: str = None
    ):
        """
        Initialize Phase 4.3 Pipeline.

        Args:
            input_dir: Directory containing embedded_chunks.json
            collection_base: Base collection name (optional)
            date: Collection date YYYYMMDD (optional)
        """
        self.input_dir = Path(input_dir)
        self.collection_base = collection_base
        self.date = date

    def run_upsert(self) -> dict:
        """
        Execute the complete indexing pipeline.

        Returns:
            Dictionary with pipeline statistics
        """
        start_time = time.time()
        logger.info("=" * 70)
        logger.info("PHASE 4.3 — INDEXING PIPELINE")
        logger.info("=" * 70)

        # Step 1: Load embedded chunks
        embedded_chunks = self._load_embedded_chunks()
        if not embedded_chunks:
            logger.error("No embedded chunks to index — aborting")
            return {"status": "failed", "reason": "no_chunks"}

        logger.info(f"Loaded {len(embedded_chunks)} embedded chunks from {self.input_dir}")

        # Step 2: Initialize indexer
        try:
            indexer = IndexerService(collection_base=self.collection_base)
        except ValueError as e:
            logger.error(f"Failed to initialize indexer: {e}")
            return {"status": "failed", "reason": str(e)}

        # Step 3: Get previous count for verification
        previous_collection = indexer._get_active_collection_name()
        previous_count = None
        if previous_collection:
            try:
                prev_coll = indexer.client.get_collection(previous_collection)
                previous_count = prev_coll.count()
                logger.info(f"Previous collection [{previous_collection}] has {previous_count} docs")
            except Exception as e:
                logger.warning(f"Could not get previous count: {e}")

        # Step 4: Create today's versioned collection
        collection = indexer.create_collection(date=self.date)

        # Step 5: Upsert all chunks
        logger.info("Starting upsert process...")
        indexer.upsert_chunks(collection, embedded_chunks)

        # Step 6: Verify collection
        logger.info("Running quality verification...")
        if not indexer.verify_collection(collection.name, previous_count):
            logger.error("Collection verification failed — rolling back")
            indexer.rollback()
            return {
                "status": "failed",
                "reason": "verification_failed",
                "rolled_back": True
            }

        # Step 7: Promote collection
        if not indexer.promote_collection(collection.name):
            logger.error("Collection promotion failed")
            return {"status": "failed", "reason": "promotion_failed"}

        # Step 8: Cleanup old versions
        indexer.cleanup_old_versions()

        # Step 9: Save stats
        elapsed = time.time() - start_time
        indexer.stats.elapsed_seconds = elapsed

        stats = {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "collection_name": collection.name,
            "chunks_upserted": indexer.stats.chunks_upserted,
            "chunks_deleted": indexer.stats.chunks_deleted,
            "sources_processed": indexer.stats.sources_processed,
            "elapsed_seconds": round(elapsed, 2),
            "indexer_stats": indexer.stats.to_dict()
        }

        stats_file = self.input_dir / "indexing_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)

        logger.info(f"Indexing stats saved to {stats_file}")
        logger.info(f"Total pipeline time: {elapsed:.2f}s")

        indexer.log_summary()
        return stats

    def _load_embedded_chunks(self) -> list:
        """Load embedded chunks from input directory."""
        chunks_file = self.input_dir / "embedded_chunks.json"
        if not chunks_file.exists():
            logger.error(f"Embedded chunks file not found: {chunks_file}")
            return []

        with open(chunks_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        if not isinstance(chunks, list):
            logger.error(f"Invalid chunks format — expected list, got {type(chunks)}")
            return []

        # Validate chunk structure
        for i, chunk in enumerate(chunks):
            if "embedding" not in chunk:
                logger.error(f"Chunk {i} missing 'embedding' field")
                return []
            if "chunk_id" not in chunk:
                logger.error(f"Chunk {i} missing 'chunk_id' field")
                return []

        return chunks


def main():
    """CLI entry point for Phase 4.3 pipeline."""
    parser = argparse.ArgumentParser(
        description="Phase 4.3 — Indexing Pipeline"
    )
    parser.add_argument(
        "--mode",
        choices=["upsert", "verify", "cleanup", "rollback"],
        default="upsert",
        help="Pipeline mode (default: upsert)"
    )
    parser.add_argument(
        "--input",
        default="data/embedded/",
        help="Input directory containing embedded_chunks.json"
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Base collection name"
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Collection date (YYYYMMDD format)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Run pipeline
    pipeline = Phase4_3_Pipeline(
        input_dir=args.input,
        collection_base=args.collection,
        date=args.date
    )

    if args.mode == "upsert":
        stats = pipeline.run_upsert()
        if stats["status"] == "failed":
            logger.error(f"Pipeline failed: {stats.get('reason')}")
            sys.exit(1)
        else:
            logger.info("Pipeline completed successfully")
            logger.info(f"  Chunks upserted: {stats['chunks_upserted']}")
            logger.info(f"  Chunks deleted: {stats['chunks_deleted']}")
            logger.info(f"  Sources synced: {stats['sources_processed']}")
            logger.info(f"  Total time: {stats['elapsed_seconds']:.2f}s")

    elif args.mode == "verify":
        try:
            indexer = IndexerService(collection_base=args.collection)
            active = indexer._get_active_collection_name()
            if not active:
                logger.error("No active collection found")
                sys.exit(1)

            if indexer.verify_collection(active):
                logger.info(f"Collection [{active}] verification PASSED")
            else:
                logger.error(f"Collection [{active}] verification FAILED")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            sys.exit(1)

    elif args.mode == "cleanup":
        try:
            indexer = IndexerService(collection_base=args.collection)
            indexer.cleanup_old_versions()
            logger.info("Cleanup complete")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            sys.exit(1)

    elif args.mode == "rollback":
        try:
            indexer = IndexerService(collection_base=args.collection)
            previous = indexer.rollback()
            if previous:
                logger.info(f"Rolled back to: {previous}")
            else:
                logger.error("Rollback failed")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
