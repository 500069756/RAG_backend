"""
Phase 4.2 — Main Entry Point
Orchestrates the embedding pipeline from chunks to vectors.

Usage:
    # Embed all chunks
    python -m phases.phase_4_2_embedding --mode embed

    # Embed with custom paths
    python -m phases.phase_4_2_embedding \
        --input data/chunks/ \
        --output data/embedded/ \
        --cache data/embeddings_cache/

    # Clear cache and re-embed everything
    python -m phases.phase_4_2_embedding --mode embed --clear-cache
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

from phases.phase_4_2_embedding.embedder import EmbeddingService

logger = logging.getLogger(__name__)


class Phase4_2_Pipeline:
    """Orchestrates Phase 4.2: Embedding pipeline."""

    def __init__(
        self,
        input_dir: str = "data/chunks/",
        output_dir: str = "data/embedded/",
        cache_dir: str = "data/embeddings_cache/",
        model: str = None,
        clear_cache: bool = False
    ):
        """
        Initialize Phase 4.2 Pipeline.

        Args:
            input_dir: Directory containing chunks.json
            output_dir: Directory for embedded chunks output
            cache_dir: Directory for embedding cache
            model: Embedding model name (optional)
            clear_cache: Whether to clear cache before embedding
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.cache_dir = Path(cache_dir)
        self.model = model
        self.clear_cache = clear_cache

        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict:
        """
        Execute the complete embedding pipeline.

        Returns:
            Dictionary with pipeline statistics
        """
        start_time = time.time()
        logger.info("=" * 70)
        logger.info("PHASE 4.2 — EMBEDDING PIPELINE")
        logger.info("=" * 70)

        # Step 1: Load chunks
        chunks = self._load_chunks()
        if not chunks:
            logger.error("No chunks to embed — aborting")
            return {"status": "failed", "reason": "no_chunks"}

        logger.info(f"Loaded {len(chunks)} chunks from {self.input_dir}")

        # Step 2: Initialize embedder
        try:
            embedder = EmbeddingService(
                cache_dir=str(self.cache_dir),
                model=self.model
            )
        except ValueError as e:
            logger.error(f"Failed to initialize embedder: {e}")
            return {"status": "failed", "reason": str(e)}

        # Step 3: Clear cache if requested
        if self.clear_cache:
            logger.info("Clearing embedding cache...")
            embedder.clear_cache()

        # Step 4: Embed chunks
        logger.info("Starting embedding process...")
        enriched_chunks = embedder.embed_chunks(chunks)

        if not enriched_chunks:
            logger.error("No embedded chunks produced — pipeline failed")
            return {"status": "failed", "reason": "embedding_failed"}

        # Step 5: Save results
        output_file = self.output_dir / "embedded_chunks.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(enriched_chunks, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(enriched_chunks)} embedded chunks to {output_file}")

        # Step 6: Save pipeline stats
        elapsed = time.time() - start_time
        stats = {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": embedder.model,
            "chunks_processed": len(enriched_chunks),
            "chunks_failed": len(chunks) - len(enriched_chunks),
            "elapsed_seconds": round(elapsed, 2),
            "embedding_stats": embedder.stats.to_dict()
        }

        stats_file = self.output_dir / "pipeline_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)

        logger.info(f"Pipeline stats saved to {stats_file}")
        logger.info(f"Total pipeline time: {elapsed:.2f}s")

        return stats

    def _load_chunks(self) -> list:
        """Load chunks from input directory."""
        chunks_file = self.input_dir / "chunks.json"
        if not chunks_file.exists():
            logger.error(f"Chunks file not found: {chunks_file}")
            return []

        with open(chunks_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        if not isinstance(chunks, list):
            logger.error(f"Invalid chunks format — expected list, got {type(chunks)}")
            return []

        # Validate chunk structure
        for i, chunk in enumerate(chunks):
            if "text" not in chunk:
                logger.error(f"Chunk {i} missing 'text' field")
                return []

        return chunks


def main():
    """CLI entry point for Phase 4.2 pipeline."""
    parser = argparse.ArgumentParser(
        description="Phase 4.2 — Embedding Pipeline"
    )
    parser.add_argument(
        "--mode",
        choices=["embed"],
        default="embed",
        help="Pipeline mode (default: embed)"
    )
    parser.add_argument(
        "--input",
        default="data/chunks/",
        help="Input directory containing chunks.json"
    )
    parser.add_argument(
        "--output",
        default="data/embedded/",
        help="Output directory for embedded chunks"
    )
    parser.add_argument(
        "--cache",
        default="data/embeddings_cache/",
        help="Directory for embedding cache"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Embedding model name"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear cache before embedding"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Run pipeline
    pipeline = Phase4_2_Pipeline(
        input_dir=args.input,
        output_dir=args.output,
        cache_dir=args.cache,
        model=args.model,
        clear_cache=args.clear_cache
    )

    stats = pipeline.run()

    if stats["status"] == "failed":
        logger.error(f"Pipeline failed: {stats.get('reason')}")
        sys.exit(1)
    else:
        logger.info("Pipeline completed successfully")
        logger.info(f"  Chunks processed: {stats['chunks_processed']}")
        logger.info(f"  Chunks failed: {stats['chunks_failed']}")
        logger.info(f"  Cache hit rate: {stats['embedding_stats']['cache_hit_rate']:.1f}%")
        logger.info(f"  Total time: {stats['elapsed_seconds']:.2f}s")


if __name__ == "__main__":
    main()
