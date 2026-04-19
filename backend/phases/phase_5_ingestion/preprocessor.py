"""
Preprocessor Service — Phase 4.3.5
Cleans and normalizes raw scraped text before chunking.

Responsibilities:
    - Strip residual HTML tags
    - Normalize whitespace and encoding
    - Fix mojibake and smart quotes
    - Validate content quality

Usage:
    python -m ingestion.preprocessor --input data/scraped/ --output data/chunks/
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

try:
    import ftfy
except ImportError:
    ftfy = None

logger = logging.getLogger(__name__)


class PreprocessorService:
    """Cleans and normalizes raw scraped text before chunking."""

    def __init__(self, input_dir: str = "data/scraped/",
                 output_dir: str = "data/preprocessed/"):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {"processed": 0, "skipped": 0}

    def _fix_encoding(self, text: str) -> str:
        """Fix mojibake, smart quotes, and other encoding issues."""
        if ftfy:
            text = ftfy.fix_text(text)

        # Manual fixes for common issues
        replacements = {
            "\u2018": "'",   # Left single quote
            "\u2019": "'",   # Right single quote
            "\u201c": '"',   # Left double quote
            "\u201d": '"',   # Right double quote
            "\u2013": "-",   # En dash
            "\u2014": " - ", # Em dash
            "\u2026": "...", # Ellipsis
            "\u00a0": " ",   # Non-breaking space
            "\u200b": "",    # Zero-width space
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    def _normalize_whitespace(self, text: str) -> str:
        """Collapse multiple spaces/newlines into single separators."""
        # Collapse multiple blank lines into max 2
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Collapse multiple spaces into single
        text = re.sub(r'[ \t]{2,}', ' ', text)
        # Strip trailing whitespace per line
        lines = [line.rstrip() for line in text.splitlines()]
        return '\n'.join(lines)

    def _strip_html_remnants(self, text: str) -> str:
        """Remove any residual HTML tags that survived extraction."""
        text = re.sub(r'<[^>]+>', '', text)
        # Remove HTML entities
        text = re.sub(r'&[a-zA-Z]+;', ' ', text)
        text = re.sub(r'&#\d+;', ' ', text)
        return text

    def _validate_content(self, text: str, source_id: str) -> bool:
        """Check if content meets minimum quality threshold."""
        stripped = text.strip()
        if len(stripped) < 50:
            logger.warning(f"[{source_id}] Content too short: {len(stripped)} chars")
            return False
        # Check for meaningful alphabetic content
        alpha_ratio = sum(c.isalpha() for c in stripped) / max(len(stripped), 1)
        if alpha_ratio < 0.3:
            logger.warning(f"[{source_id}] Low alpha ratio: {alpha_ratio:.2f}")
            return False
        return True

    def preprocess(self, text: str, source_id: str) -> str | None:
        """
        Apply full preprocessing pipeline to raw text.
        Returns cleaned text or None if content fails validation.
        """
        # Step 1: Fix encoding issues
        text = self._fix_encoding(text)

        # Step 2: Strip residual HTML
        text = self._strip_html_remnants(text)

        # Step 3: Normalize whitespace
        text = self._normalize_whitespace(text)

        # Step 4: Final strip
        text = text.strip()

        # Step 5: Validate
        if not self._validate_content(text, source_id):
            return None

        return text

    def process_all(self) -> list[dict]:
        """
        Process all scraped text files in the input directory.
        Returns list of {source, text} dicts.
        """
        results = []

        # Find all .txt files in scraped dir (each is a scraped source)
        txt_files = sorted(self.input_dir.glob("*.txt"))
        logger.info(f"Found {len(txt_files)} scraped files to preprocess")

        for txt_file in txt_files:
            source_id = txt_file.stem  # e.g., "hdfc-top100-factsheet"
            meta_file = self.input_dir / f"{source_id}.meta.json"

            # Load raw text
            with open(txt_file, "r", encoding="utf-8") as f:
                raw_text = f.read()

            # Load metadata
            source_meta = {}
            if meta_file.exists():
                with open(meta_file, "r", encoding="utf-8") as f:
                    source_meta = json.load(f)

            # Preprocess
            clean_text = self.preprocess(raw_text, source_id)
            if clean_text is None:
                self.stats["skipped"] += 1
                logger.warning(f"Skipped [{source_id}]: failed validation")
                continue

            # Save preprocessed text
            output_file = self.output_dir / f"{source_id}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(clean_text)

            results.append({
                "source": source_meta,
                "text": clean_text
            })
            self.stats["processed"] += 1

        self._log_summary()
        return results

    def _log_summary(self):
        """Log preprocessing summary."""
        logger.info("=" * 50)
        logger.info("PREPROCESSING SUMMARY")
        logger.info(f"  Processed: {self.stats['processed']}")
        logger.info(f"  Skipped:   {self.stats['skipped']}")
        logger.info("=" * 50)


def main():
    """CLI entry point for the preprocessor."""
    parser = argparse.ArgumentParser(
        description="Mutual Fund FAQ Preprocessor"
    )
    parser.add_argument(
        "--input",
        default="data/scraped/",
        help="Input directory with scraped text files"
    )
    parser.add_argument(
        "--output",
        default="data/preprocessed/",
        help="Output directory for preprocessed text"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    preprocessor = PreprocessorService(
        input_dir=args.input,
        output_dir=args.output
    )
    results = preprocessor.process_all()
    logger.info(f"Preprocessing complete: {len(results)} files")


if __name__ == "__main__":
    main()
