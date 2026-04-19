"""
Phase 4.1 — Main Entry Point
Orchestrates the chunking pipeline from scraped text to enriched chunks.

Usage:
    # Chunk all scraped files
    python -m phases.phase_4_1_chunking --mode chunk

    # Chunk with custom paths
    python -m phases.phase_4_1_chunking \
        --input data/scraped/ \
        --output data/chunks/ \
        --sources phases/phase_1_corpus/sources.json
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

from phases.phase_4_1_chunking.chunker import ChunkingService

logger = logging.getLogger(__name__)


class Phase4_1_Pipeline:
    """Orchestrates Phase 4.1: Chunking pipeline."""

    def __init__(
        self,
        input_dir: str = "data/scraped/",
        output_dir: str = "data/chunks/",
        sources_path: str = "phases/phase_1_corpus/sources.json"
    ):
        """
        Args:
            input_dir: Directory containing scraped text files
            output_dir: Directory to save chunks.json
            sources_path: Path to sources.json manifest
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.sources_path = Path(sources_path)

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize chunker
        self.chunker = ChunkingService(output_dir=str(self.output_dir))

        self.pipeline_stats = {
            "started_at": None,
            "completed_at": None,
            "files_loaded": 0,
            "chunks_created": 0,
            "chunks_discarded": 0
        }

    def load_scraped_files(self) -> list[dict]:
        """
        Load scraped text files and match with source metadata.

        Returns:
            List of {"source": dict, "text": str}
        """
        # Load sources metadata
        if not self.sources_path.exists():
            logger.error(f"Sources file not found: {self.sources_path}")
            raise FileNotFoundError(f"Sources file not found: {self.sources_path}")

        with open(self.sources_path, 'r', encoding='utf-8') as f:
            sources_data = json.load(f)
        sources_map = {s["id"]: s for s in sources_data["sources"]}

        # Load scraped text files
        scraped_results = []
        
        # Try clean files first, then raw files
        txt_files = sorted(self.input_dir.glob("*.clean.txt"))
        if not txt_files:
            txt_files = sorted(self.input_dir.glob("*.txt"))
            txt_files = [f for f in txt_files if not f.name.endswith('.meta.json')]

        if not txt_files:
            logger.warning(f"No .txt files found in {self.input_dir}")
            return []

        logger.info(f"Loading {len(txt_files)} scraped files from {self.input_dir}")

        for txt_file in txt_files:
            # Extract source_id from filename
            source_id = txt_file.stem.replace('.clean', '')
            
            if source_id not in sources_map:
                logger.warning(f"Skipping unknown source: {source_id}")
                continue

            with open(txt_file, 'r', encoding='utf-8') as f:
                text = f.read()

            scraped_results.append({
                "source": sources_map[source_id],
                "text": text
            })

        self.pipeline_stats["files_loaded"] = len(scraped_results)
        logger.info(f"Loaded {len(scraped_results)} sources for chunking")

        return scraped_results

    def run_chunking(self) -> list:
        """
        Run the complete chunking pipeline.

        Returns:
            List of Chunk objects
        """
        self.pipeline_stats["started_at"] = datetime.now(timezone.utc).isoformat()

        logger.info("=" * 70)
        logger.info("PHASE 4.1 — CHUNKING PIPELINE")
        logger.info(f"Started at: {self.pipeline_stats['started_at']}")
        logger.info("=" * 70)

        start_time = time.time()

        # Load scraped files
        scraped_results = self.load_scraped_files()
        if not scraped_results:
            logger.error("No scraped files to chunk!")
            return []

        # Chunk all sources
        chunks = self.chunker.chunk_all(scraped_results)

        # Complete
        duration = time.time() - start_time
        self.pipeline_stats["completed_at"] = datetime.now(timezone.utc).isoformat()
        self.pipeline_stats["chunks_created"] = len(chunks)
        self.pipeline_stats["chunks_discarded"] = self.chunker.stats["discarded"]

        logger.info("=" * 70)
        logger.info("PHASE 4.1 — CHUNKING COMPLETE")
        logger.info(f"Duration: {duration:.1f}s")
        logger.info(f"Files loaded: {self.pipeline_stats['files_loaded']}")
        logger.info(f"Chunks created: {self.pipeline_stats['chunks_created']}")
        logger.info(f"Chunks discarded: {self.pipeline_stats['chunks_discarded']}")
        logger.info("=" * 70)

        # Save pipeline summary
        self._save_pipeline_summary()

        return chunks

    def _save_pipeline_summary(self):
        """Save pipeline execution summary to JSON."""
        summary_file = self.output_dir / "chunking_summary.json"

        summary = {
            **self.pipeline_stats,
            "input_dir": str(self.input_dir),
            "output_dir": str(self.output_dir),
            "sources_path": str(self.sources_path)
        }

        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Chunking summary saved: {summary_file}")


def main():
    """CLI entry point for Phase 4.1 pipeline."""
    parser = argparse.ArgumentParser(
        description="Phase 4.1 — Chunking Pipeline"
    )
    parser.add_argument(
        "--mode",
        choices=["chunk"],
        default="chunk",
        help="Pipeline mode (default: chunk)"
    )
    parser.add_argument(
        "--input",
        default="data/scraped/",
        help="Input directory containing scraped text files"
    )
    parser.add_argument(
        "--output",
        default="data/chunks/",
        help="Output directory for chunks.json"
    )
    parser.add_argument(
        "--sources",
        default="phases/phase_1_corpus/sources.json",
        help="Path to sources.json manifest"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose/debug logging"
    )
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Initialize pipeline
    pipeline = Phase4_1_Pipeline(
        input_dir=args.input,
        output_dir=args.output,
        sources_path=args.sources
    )

    # Run chunking
    try:
        chunks = pipeline.run_chunking()
        
        if not chunks:
            logger.warning("No chunks were created!")
            sys.exit(1)

        logger.info(f"✅ Chunking complete: {len(chunks)} chunks created")
        logger.info(f"📁 Output: {pipeline.output_dir / 'chunks.json'}")

    except Exception as e:
        logger.error(f"❌ Chunking pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
