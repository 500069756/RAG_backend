"""
Phase 4.0 — Scheduler & Scraping Service

Daily cron job (9:15 AM IST) via GitHub Actions that:
1. Loads source URLs from corpus registry
2. Scrapes HTML and PDF documents with change detection
3. Preprocesses and cleans extracted text
4. Outputs clean text for Phase 5 (Ingestion Pipeline)

Components:
    - scraper.py: Main scraping service with retry, dedup, and multi-format support
    - preprocessor.py: Text cleaning and normalization
    - main.py: Entry point for CLI and GitHub Actions

Usage:
    # Full pipeline (scrape + preprocess)
    python -m phases.phase_4_scheduler --mode full

    # Scrape only
    python -m phases.phase_4_scheduler --mode scrape

    # Force re-scrape all sources
    python -m phases.phase_4_scheduler --mode full --force
"""

from .scraper import ScraperService
from .preprocessor import PreprocessorService
from .main import Phase4Pipeline

__all__ = ["ScraperService", "PreprocessorService", "Phase4Pipeline"]
