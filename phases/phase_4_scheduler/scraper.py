"""
Scraper Service — Phase 4.0
Fetches and extracts text content from registered source URLs.

Responsibilities:
    - Load source URLs from data/sources.json
    - Fetch HTML pages and PDF documents with retry/backoff
    - Extract clean text using trafilatura/BeautifulSoup/PyMuPDF
    - Detect content changes via SHA-256 hashing
    - Save extracted text to data/scraped/ directory
    - Update source manifest with new hashes and timestamps

Usage:
    python -m ingestion.scraper --sources data/sources.json --output data/scraped/
"""

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup

try:
    import trafilatura
except ImportError:
    trafilatura = None

logger = logging.getLogger(__name__)


class ScraperService:
    """Fetches and extracts text content from registered source URLs."""

    HEADERS = {
        "User-Agent": "MutualFundFAQ-Bot/1.0 (+https://github.com/yourrepo)",
        "Accept": "text/html,application/xhtml+xml,application/pdf",
    }
    REQUEST_TIMEOUT = 30          # seconds per request
    RATE_LIMIT_DELAY = 2.0        # seconds between requests (politeness)
    MAX_RETRIES = 3               # retry count per URL
    RETRY_BACKOFF = [2, 5, 10]    # seconds to wait between retries
    MAX_PDF_SIZE_MB = 50          # skip PDFs larger than this
    MIN_CONTENT_LENGTH = 50       # minimum characters to accept

    def __init__(self, sources_path: str = "data/sources.json",
                 output_dir: str = "data/scraped/",
                 force: bool = False):
        self.sources_path = Path(sources_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.force = force
        self.sources = self._load_sources()
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.results = {"scraped": [], "skipped": [], "failed": []}
        self._start_time = time.time()

    def _load_sources(self) -> list[dict]:
        """Load source URL registry from JSON manifest."""
        with open(self.sources_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data['sources'])} sources from {self.sources_path}")
        return data["sources"]

    def _compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content for change detection."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _is_pdf_url(self, url: str) -> bool:
        """Detect if URL points to a PDF (by extension or content-type)."""
        return urlparse(url).path.lower().endswith(".pdf")

    def _fetch_with_retry(self, url: str) -> requests.Response | None:
        """Fetch URL with exponential backoff retry."""
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.get(
                    url,
                    timeout=self.REQUEST_TIMEOUT,
                    stream=self._is_pdf_url(url)
                )
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else 0
                if status == 429:
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    logger.warning(f"Rate limited on {url}, waiting {wait}s...")
                    time.sleep(wait)
                elif status >= 500:
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    logger.warning(f"Server error {status} on {url}, retry {attempt+1}")
                    time.sleep(wait)
                else:
                    logger.error(f"HTTP {status} for {url}: {e}")
                    return None
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error for {url}: {e}")
                time.sleep(self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)])
            except requests.exceptions.Timeout:
                logger.error(f"Timeout fetching {url} (attempt {attempt+1})")
                time.sleep(self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)])
        return None

    def _extract_html(self, html: str, url: str) -> str:
        """Extract clean text from HTML using trafilatura (preferred) or BeautifulSoup."""
        # Prefer trafilatura for main content extraction
        if trafilatura:
            text = trafilatura.extract(
                html,
                include_tables=True,
                include_links=True,
                output_format="txt",
                url=url
            )
            if text and len(text.strip()) > 100:
                return text.strip()

        # Fallback: BeautifulSoup manual extraction
        soup = BeautifulSoup(html, "html.parser")

        # Remove non-content elements
        for tag in soup.find_all(["nav", "footer", "header", "script",
                                   "style", "aside", "iframe", "noscript"]):
            tag.decompose()

        # Extract text from remaining content
        text = soup.get_text(separator="\n", strip=True)

        # Normalize whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    def _extract_pdf(self, content: bytes, url: str) -> str:
        """Extract text from PDF binary content using PyMuPDF."""
        # Check file size
        size_mb = len(content) / (1024 * 1024)
        if size_mb > self.MAX_PDF_SIZE_MB:
            logger.warning(f"PDF too large ({size_mb:.1f}MB): {url}")
            return ""

        text_parts = []
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            for page_num, page in enumerate(doc):
                page_text = page.get_text("text")
                if page_text.strip():
                    text_parts.append(f"--- Page {page_num + 1} ---\n{page_text.strip()}")
            doc.close()
        except Exception as e:
            logger.error(f"PDF extraction failed for {url}: {e}")
            return ""

        return "\n\n".join(text_parts)

    def scrape_source(self, source: dict) -> dict | None:
        """
        Scrape a single source URL.
        Returns updated source dict with extracted text, or None on failure.
        """
        url = source["url"]
        source_id = source["id"]
        logger.info(f"Scraping [{source_id}]: {url}")

        response = self._fetch_with_retry(url)
        if response is None:
            self.results["failed"].append({
                "id": source_id, "url": url, "reason": "fetch_failed"
            })
            return None

        # Extract text based on content type
        content_type = response.headers.get("Content-Type", "").lower()
        if "pdf" in content_type or self._is_pdf_url(url):
            raw_text = self._extract_pdf(response.content, url)
        else:
            raw_text = self._extract_html(response.text, url)

        if not raw_text or len(raw_text.strip()) < self.MIN_CONTENT_LENGTH:
            chars = len(raw_text) if raw_text else 0
            logger.warning(f"Insufficient content from [{source_id}]: {chars} chars")
            self.results["failed"].append({
                "id": source_id, "url": url, "reason": "insufficient_content"
            })
            return None

        # Change detection via content hash
        new_hash = self._compute_hash(raw_text)
        if not self.force and source.get("content_hash") == new_hash:
            logger.info(f"No changes detected for [{source_id}], skipping.")
            self.results["skipped"].append({"id": source_id, "reason": "unchanged"})
            return None

        # Update source metadata
        source["content_hash"] = new_hash
        source["last_scraped"] = datetime.now(timezone.utc).isoformat()

        self.results["scraped"].append({
            "id": source_id,
            "chars": len(raw_text),
            "hash": new_hash[:12]
        })

        return {
            "source": source,
            "text": raw_text
        }

    def scrape_all(self) -> list[dict]:
        """
        Scrape all registered source URLs.
        Returns list of {source, text} dicts for changed content only.
        """
        results = []
        total = len(self.sources)

        for idx, source in enumerate(self.sources, 1):
            logger.info(f"Progress: [{idx}/{total}] - {source['id']}")
            result = self.scrape_source(source)
            if result:
                results.append(result)
                # Save individual scraped text to file
                self._save_scraped_text(result)

            # Rate limiting: wait between requests
            if idx < total:
                time.sleep(self.RATE_LIMIT_DELAY)

        # Save updated sources manifest (with new hashes & timestamps)
        self._save_sources()
        self._save_summary()
        self._log_summary()

        return results

    def _save_scraped_text(self, result: dict):
        """Save individual scraped text to output directory."""
        source_id = result["source"]["id"]
        output_file = self.output_dir / f"{source_id}.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result["text"])

        # Also save metadata alongside
        meta_file = self.output_dir / f"{source_id}.meta.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(result["source"], f, indent=2)

        logger.info(f"  Saved: {output_file} ({len(result['text'])} chars)")

    def _save_sources(self):
        """Persist updated source metadata back to JSON."""
        with open(self.sources_path, "w", encoding="utf-8") as f:
            json.dump({"sources": self.sources}, f, indent=2, ensure_ascii=False)
        logger.info(f"Updated source manifest: {self.sources_path}")

    def _save_summary(self):
        """Save scraping run summary to output directory."""
        duration = time.time() - self._start_time
        now_utc = datetime.now(timezone.utc)

        summary = {
            "run_timestamp": now_utc.isoformat(),
            "run_timestamp_ist": now_utc.strftime("%Y-%m-%dT%H:%M:%S+05:30"),
            "total_sources": len(self.sources),
            "scraped": len(self.results["scraped"]),
            "skipped_unchanged": len(self.results["skipped"]),
            "failed": len(self.results["failed"]),
            "duration_seconds": round(duration, 2),
            "force_mode": self.force,
            "scraped_sources": self.results["scraped"],
            "failed_sources": self.results["failed"],
        }

        summary_file = self.output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Saved run summary: {summary_file}")

    def _log_summary(self):
        """Log scraping run summary."""
        duration = time.time() - self._start_time
        logger.info("=" * 60)
        logger.info("SCRAPING SUMMARY")
        logger.info(f"  Scraped (new/updated): {len(self.results['scraped'])}")
        logger.info(f"  Skipped (unchanged):   {len(self.results['skipped'])}")
        logger.info(f"  Failed:                {len(self.results['failed'])}")
        logger.info(f"  Duration:              {duration:.1f}s")
        logger.info(f"  Force mode:            {self.force}")
        logger.info("=" * 60)
        if self.results["failed"]:
            for failure in self.results["failed"]:
                logger.error(f"  FAILED: [{failure['id']}] - {failure['reason']}")


def main():
    """CLI entry point for the scraper service."""
    parser = argparse.ArgumentParser(
        description="Mutual Fund FAQ Scraper Service"
    )
    parser.add_argument(
        "--sources",
        default="data/sources.json",
        help="Path to sources.json manifest (default: data/sources.json)"
    )
    parser.add_argument(
        "--output",
        default="data/scraped/",
        help="Output directory for scraped text (default: data/scraped/)"
    )
    parser.add_argument(
        "--force",
        default="false",
        choices=["true", "false"],
        help="Force re-scrape all URLs ignoring content hash (default: false)"
    )
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    force = args.force.lower() == "true"
    logger.info(f"Starting scraper (sources={args.sources}, "
                f"output={args.output}, force={force})")

    scraper = ScraperService(
        sources_path=args.sources,
        output_dir=args.output,
        force=force
    )
    results = scraper.scrape_all()

    logger.info(f"Scraping complete: {len(results)} sources with new content")

    # Exit with error if any sources failed
    if scraper.results["failed"]:
        logger.warning(f"{len(scraper.results['failed'])} sources failed — "
                       "check logs for details")
        sys.exit(1 if len(scraper.results["failed"]) == len(scraper.sources) else 0)


if __name__ == "__main__":
    main()
