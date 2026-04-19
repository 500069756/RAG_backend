"""
Phase 4.0 — Main Entry Point
Orchestrates the complete scraping and preprocessing pipeline.

Usage:
    # Scrape only
    python -m phases.phase_4_scheduler --mode scrape

    # Scrape + Preprocess (default)
    python -m phases.phase_4_scheduler --mode full

    # Force re-scrape all sources
    python -m phases.phase_4_scheduler --mode full --force

    # Preprocess only (skip scraping)
    python -m phases.phase_4_scheduler --mode preprocess
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

from phases.phase_4_scheduler.scraper import ScraperService
from phases.phase_4_scheduler.preprocessor import PreprocessorService

logger = logging.getLogger(__name__)


class Phase4Pipeline:
    """Orchestrates Phase 4.0: Scraping + Preprocessing pipeline."""

    def __init__(
        self,
        sources_path: str = "phases/phase_1_corpus/sources.json",
        scraped_dir: str = "data/scraped/",
        cleaned_dir: str = "data/scraped/",
        force: bool = False
    ):
        """
        Args:
            sources_path: Path to sources.json manifest
            scraped_dir: Directory for raw scraped text
            cleaned_dir: Directory for preprocessed text
            force: Force re-scrape all sources ignoring hash
        """
        self.sources_path = Path(sources_path)
        self.scraped_dir = Path(scraped_dir)
        self.cleaned_dir = Path(cleaned_dir)
        self.force = force

        # Ensure directories exist
        self.scraped_dir.mkdir(parents=True, exist_ok=True)
        self.cleaned_dir.mkdir(parents=True, exist_ok=True)

        # Initialize services
        self.scraper = ScraperService(
            sources_path=str(self.sources_path),
            output_dir=str(self.scraped_dir),
            force=force
        )
        self.preprocessor = PreprocessorService()

        self.pipeline_stats = {
            "started_at": None,
            "completed_at": None,
            "mode": None,
            "scraped_count": 0,
            "preprocessed_count": 0,
            "failed_count": 0
        }

    def run_scrape(self) -> list[dict]:
        """
        Run scraping phase only.

        Returns:
            List of scraped results with source metadata and text
        """
        logger.info("=" * 70)
        logger.info("PHASE 4.0 — SCRAPING")
        logger.info("=" * 70)

        if not self.sources_path.exists():
            logger.error(f"Sources file not found: {self.sources_path}")
            raise FileNotFoundError(f"Sources file not found: {self.sources_path}")

        start_time = time.time()
        results = self.scraper.scrape_all()
        duration = time.time() - start_time

        self.pipeline_stats["scraped_count"] = len(results)
        self.pipeline_stats["failed_count"] = len(self.scraper.results["failed"])

        logger.info(f"Scraping completed in {duration:.1f}s: "
                    f"{len(results)} sources scraped")

        return results

    def run_preprocess(self) -> list[Path]:
        """
        Run preprocessing phase only.

        Returns:
            List of cleaned file paths
        """
        logger.info("=" * 70)
        logger.info("PHASE 4.0 — PREPROCESSING")
        logger.info("=" * 70)

        start_time = time.time()
        cleaned_files = self.preprocessor.preprocess_directory(
            self.scraped_dir,
            self.cleaned_dir
        )
        duration = time.time() - start_time

        self.pipeline_stats["preprocessed_count"] = len(cleaned_files)

        logger.info(f"Preprocessing completed in {duration:.1f}s: "
                    f"{len(cleaned_files)} files cleaned")

        return cleaned_files

    def run_full_pipeline(self) -> dict:
        """
        Run complete Phase 4.0 pipeline: Scrape → Preprocess.

        Returns:
            Pipeline execution summary
        """
        self.pipeline_stats["started_at"] = datetime.now(timezone.utc).isoformat()
        self.pipeline_stats["mode"] = "full"

        logger.info("=" * 70)
        logger.info("PHASE 4.0 — COMPLETE PIPELINE (Scrape + Preprocess)")
        logger.info(f"Started at: {self.pipeline_stats['started_at']}")
        logger.info(f"Force mode: {self.force}")
        logger.info("=" * 70)

        overall_start = time.time()

        # Step 1: Scrape
        try:
            scraped_results = self.run_scrape()
        except Exception as e:
            logger.error(f"Scraping phase failed: {e}")
            self.pipeline_stats["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save_pipeline_summary()
            raise

        # Step 2: Preprocess
        try:
            cleaned_files = self.run_preprocess()
        except Exception as e:
            logger.error(f"Preprocessing phase failed: {e}")
            self.pipeline_stats["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save_pipeline_summary()
            raise

        # Complete
        overall_duration = time.time() - overall_start
        self.pipeline_stats["completed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info("=" * 70)
        logger.info("PHASE 4.0 — PIPELINE COMPLETE")
        logger.info(f"Duration: {overall_duration:.1f}s")
        logger.info(f"Scraped: {self.pipeline_stats['scraped_count']} sources")
        logger.info(f"Preprocessed: {self.pipeline_stats['preprocessed_count']} files")
        logger.info(f"Failed: {self.pipeline_stats['failed_count']} sources")
        logger.info("=" * 70)

        # Save summary
        self._save_pipeline_summary()

        return self.pipeline_stats

    def _save_pipeline_summary(self):
        """Save pipeline execution summary to JSON."""
        summary_file = self.scraped_dir / "pipeline_summary.json"

        summary = {
            **self.pipeline_stats,
            "sources_path": str(self.sources_path),
            "scraped_dir": str(self.scraped_dir),
            "cleaned_dir": str(self.cleaned_dir),
        }

        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Pipeline summary saved: {summary_file}")


def main():
    """CLI entry point for Phase 4.0 pipeline."""
    parser = argparse.ArgumentParser(
        description="Phase 4.0 — Scheduler & Scraping Pipeline"
    )
    parser.add_argument(
        "--mode",
        choices=["scrape", "preprocess", "full"],
        default="full",
        help="Pipeline mode: 'scrape', 'preprocess', or 'full' (default: full)"
    )
    parser.add_argument(
        "--sources",
        default="phases/phase_1_corpus/sources.json",
        help="Path to sources.json manifest"
    )
    parser.add_argument(
        "--scraped-dir",
        default="data/scraped/",
        help="Directory for raw scraped text"
    )
    parser.add_argument(
        "--cleaned-dir",
        default="data/scraped/",
        help="Directory for cleaned/preprocessed text"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force re-scrape all sources (ignore content hash)"
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
    pipeline = Phase4Pipeline(
        sources_path=args.sources,
        scraped_dir=args.scraped_dir,
        cleaned_dir=args.cleaned_dir,
        force=args.force
    )

    # Run selected mode
    try:
        if args.mode == "scrape":
            results = pipeline.run_scrape()
            logger.info(f"✅ Scraping complete: {len(results)} sources")

        elif args.mode == "preprocess":
            results = pipeline.run_preprocess()
            logger.info(f"✅ Preprocessing complete: {len(results)} files")

        elif args.mode == "full":
            results = pipeline.run_full_pipeline()
            logger.info(f"✅ Full pipeline complete")

        # Exit with error code if there were failures
        if pipeline.pipeline_stats["failed_count"] > 0:
            logger.warning(f"⚠️  {pipeline.pipeline_stats['failed_count']} sources failed")
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
