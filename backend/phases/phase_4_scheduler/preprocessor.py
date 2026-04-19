"""
Preprocessor Service — Phase 4.0
Cleans and normalizes raw scraped text before chunking.

Responsibilities:
    - Remove residual HTML tags and entities
    - Normalize whitespace and line breaks
    - Fix encoding issues (mojibake, smart quotes)
    - Remove navigation, footer, and boilerplate content
    - Validate minimum content quality
    - Prepare clean text for Phase 5 (Chunking)

Usage:
    python -m phases.phase_4_scheduler.preprocessor --input data/scraped/ --output data/scraped/
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
    """Cleans and normalizes raw scraped text."""

    # Regex patterns for cleaning
    HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
    HTML_ENTITY_PATTERN = re.compile(r'&[a-z0-9#]+;', re.IGNORECASE)
    MULTIPLE_SPACES = re.compile(r' {2,}')
    MULTIPLE_NEWLINES = re.compile(r'\n{3,}')
    LEADING_TRAILING_WHITESPACE = re.compile(r'^\s+|\s+$', re.MULTILINE)

    # Common boilerplate patterns to remove
    BOILERPLATE_PATTERNS = [
        re.compile(r'^(Skip to content|Skip to main content|Jump to navigation)', re.IGNORECASE | re.MULTILINE),
        re.compile(r'^(Copyright|©)\s+\d{4}', re.IGNORECASE | re.MULTILINE),
        re.compile(r'All rights reserved', re.IGNORECASE),
        re.compile(r'Privacy Policy|Terms of Service|Cookie Policy', re.IGNORECASE),
    ]

    MIN_CONTENT_LENGTH = 100  # Minimum characters after cleaning

    def __init__(self, min_content_length: int = MIN_CONTENT_LENGTH):
        """
        Args:
            min_content_length: Minimum acceptable content length after cleaning
        """
        self.min_content_length = min_content_length
        self.stats = {
            "processed": 0,
            "rejected": 0,
            "total_chars_before": 0,
            "total_chars_after": 0
        }

    def clean_text(self, text: str) -> str:
        """
        Apply all cleaning steps to raw text.

        Args:
            text: Raw scraped text (may contain HTML, encoding issues, etc.)

        Returns:
            Cleaned and normalized text
        """
        if not text:
            return ""

        # Step 1: Fix encoding issues (mojibake, smart quotes)
        if ftfy:
            text = ftfy.fix_text(text)

        # Step 2: Remove residual HTML tags
        text = self.HTML_TAG_PATTERN.sub('', text)

        # Step 3: Decode HTML entities
        text = self._decode_html_entities(text)

        # Step 4: Remove boilerplate content
        text = self._remove_boilerplate(text)

        # Step 5: Normalize whitespace
        text = self._normalize_whitespace(text)

        # Step 6: Remove empty lines and trim
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = '\n'.join(lines)

        return text.strip()

    def _decode_html_entities(self, text: str) -> str:
        """Decode common HTML entities to Unicode characters."""
        entity_map = {
            '&amp;': '&',
            '&lt;': '<',
            '&gt;': '>',
            '&quot;': '"',
            '&#39;': "'",
            '&nbsp;': ' ',
            '&mdash;': '—',
            '&ndash;': '–',
            '&laquo;': '«',
            '&raquo;': '»',
            '&bull;': '•',
            '&hellip;': '…',
            '&rsquo;': ''',
            '&lsquo;': ''',
            '&rdquo;': '"',
            '&ldquo;': '"',
            '&apos;': "'",
        }

        for entity, char in entity_map.items():
            text = text.replace(entity, char)

        # Remove any remaining numeric entities
        text = re.sub(r'&#\d+;', '', text)
        text = re.sub(r'&#x[0-9a-f]+;', '', text, flags=re.IGNORECASE)

        return text

    def _remove_boilerplate(self, text: str) -> str:
        """Remove common boilerplate patterns."""
        lines = text.splitlines()
        filtered_lines = []

        for line in lines:
            # Skip lines matching boilerplate patterns
            is_boilerplate = False
            for pattern in self.BOILERPLATE_PATTERNS:
                if pattern.search(line):
                    is_boilerplate = True
                    break

            if not is_boilerplate:
                filtered_lines.append(line)

        return '\n'.join(filtered_lines)

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace throughout text."""
        # Replace multiple spaces with single space
        text = self.MULTIPLE_SPACES.sub(' ', text)

        # Replace multiple newlines with double newline
        text = self.MULTIPLE_NEWLINES.sub('\n\n', text)

        # Remove leading/trailing whitespace on each line
        text = self.LEADING_TRAILING_WHITESPACE.sub('', text)

        return text

    def validate_content(self, text: str, source_id: str = "") -> bool:
        """
        Validate that cleaned text meets minimum quality standards.

        Args:
            text: Cleaned text to validate
            source_id: Source identifier for logging

        Returns:
            True if content passes validation, False otherwise
        """
        if not text:
            logger.warning(f"[{source_id}] Empty content after cleaning")
            return False

        if len(text) < self.min_content_length:
            logger.warning(f"[{source_id}] Content too short after cleaning: "
                          f"{len(text)} chars (min: {self.min_content_length})")
            return False

        # Check for meaningful content (not just numbers or symbols)
        alpha_chars = sum(1 for c in text if c.isalpha())
        alpha_ratio = alpha_chars / len(text) if text else 0

        if alpha_ratio < 0.3:
            logger.warning(f"[{source_id}] Low alphanumeric ratio: "
                          f"{alpha_ratio:.2f} (may be table/image-only content)")
            return False

        return True

    def preprocess_file(self, input_file: Path, output_file: Path) -> bool:
        """
        Preprocess a single scraped text file.

        Args:
            input_file: Path to raw scraped text file
            output_file: Path to save cleaned text

        Returns:
            True if preprocessing succeeded, False if rejected
        """
        source_id = input_file.stem.replace('.txt', '').replace('.meta', '')

        # Read raw text
        with open(input_file, 'r', encoding='utf-8') as f:
            raw_text = f.read()

        self.stats["processed"] += 1
        self.stats["total_chars_before"] += len(raw_text)

        logger.info(f"Preprocessing [{source_id}]: {len(raw_text)} chars")

        # Clean text
        clean_text = self.clean_text(raw_text)

        # Validate
        if not self.validate_content(clean_text, source_id):
            self.stats["rejected"] += 1
            logger.warning(f"Rejected [{source_id}] - failed validation")
            return False

        # Save cleaned text
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(clean_text)

        self.stats["total_chars_after"] += len(clean_text)

        reduction = ((len(raw_text) - len(clean_text)) / len(raw_text) * 100) if raw_text else 0
        logger.info(f"  Saved: {output_file} ({len(clean_text)} chars, "
                    f"reduced by {reduction:.1f}%)")

        return True

    def preprocess_directory(self, input_dir: Path, output_dir: Path) -> list[Path]:
        """
        Preprocess all text files in a directory.

        Args:
            input_dir: Directory containing raw scraped .txt files
            output_dir: Directory to save cleaned .txt files

        Returns:
            List of successfully preprocessed file paths
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        successful_files = []
        txt_files = sorted(input_dir.glob("*.txt"))

        if not txt_files:
            logger.warning(f"No .txt files found in {input_dir}")
            return []

        logger.info(f"Preprocessing {len(txt_files)} files from {input_dir}")

        for input_file in txt_files:
            source_id = input_file.stem
            output_file = output_dir / f"{source_id}.clean.txt"

            try:
                if self.preprocess_file(input_file, output_file):
                    successful_files.append(output_file)
            except Exception as e:
                logger.error(f"Failed to preprocess [{source_id}]: {e}")
                self.stats["rejected"] += 1

        self._log_summary()
        return successful_files

    def _log_summary(self):
        """Log preprocessing summary."""
        logger.info("=" * 60)
        logger.info("PREPROCESSING SUMMARY")
        logger.info(f"  Files processed:     {self.stats['processed']}")
        logger.info(f"  Files rejected:      {self.stats['rejected']}")
        logger.info(f"  Total chars before:  {self.stats['total_chars_before']:,}")
        logger.info(f"  Total chars after:   {self.stats['total_chars_after']:,}")

        if self.stats['total_chars_before'] > 0:
            reduction = ((self.stats['total_chars_before'] - self.stats['total_chars_after']) /
                        self.stats['total_chars_before'] * 100)
            logger.info(f"  Overall reduction:   {reduction:.1f}%")

        logger.info("=" * 60)


def main():
    """CLI entry point for the preprocessor service."""
    parser = argparse.ArgumentParser(
        description="Mutual Fund FAQ Preprocessor Service"
    )
    parser.add_argument(
        "--input",
        default="data/scraped/",
        help="Input directory containing raw scraped .txt files"
    )
    parser.add_argument(
        "--output",
        default="data/scraped/",
        help="Output directory for cleaned .txt files"
    )
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.exists():
        logger.error(f"Input directory not found: {input_dir}")
        sys.exit(1)

    preprocessor = PreprocessorService()
    successful = preprocessor.preprocess_directory(input_dir, output_dir)

    logger.info(f"Preprocessing complete: {len(successful)} files cleaned")

    if not successful:
        logger.warning("No files were successfully preprocessed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
