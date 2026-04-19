"""
Chunking Service — Phase 4.1
Splits scraped text into semantically meaningful chunks with enriched metadata.

Responsibilities:
    - Document-type-aware splitting (factsheet, SID, FAQ, guide)
    - QA-pair detection for FAQ pages
    - Chunk validation (min/max length, content quality)
    - Metadata enrichment (source_url, scheme, category, etc.)
    - SHA-256 deduplication

Usage:
    python -m ingestion.chunker --input data/scraped/ --output data/chunks/
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────


@dataclass
class Chunk:
    """Represents a single text chunk with enriched metadata."""
    chunk_id: str
    text: str
    source_id: str
    source_url: str
    scheme_name: str
    document_type: str
    category: str
    scraped_at: str
    chunk_index: int
    total_chunks: int
    token_count: int
    content_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SplitterConfig:
    """Configuration for a document-type-specific splitter."""
    chunk_size: int
    chunk_overlap: int
    separators: list[str]
    is_qa_mode: bool = False    # If True, split on Q&A boundaries instead


# ── Chunking Service ──────────────────────────────────────────


class ChunkingService:
    """Splits scraped text into semantically meaningful chunks with metadata."""

    # ── Document-type-aware splitter configs ──────────────────
    SPLITTER_CONFIGS = {
        "factsheet": SplitterConfig(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ". ", " "]
        ),
        "factsheet_pdf": SplitterConfig(
            chunk_size=500,
            chunk_overlap=50,
            separators=["--- Page", "\n\n", "\n", ". "]
        ),
        "sid": SplitterConfig(
            chunk_size=800,
            chunk_overlap=100,
            separators=["--- Page", "\n\n", "\n", ". "]
        ),
        "kim": SplitterConfig(
            chunk_size=800,
            chunk_overlap=100,
            separators=["--- Page", "\n\n", "\n", ". "]
        ),
        "faq": SplitterConfig(
            chunk_size=500,
            chunk_overlap=0,
            separators=[],
            is_qa_mode=True
        ),
        "guide": SplitterConfig(
            chunk_size=400,
            chunk_overlap=40,
            separators=["\n\n", "\n", ". ", " "]
        ),
        "default": SplitterConfig(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ". ", " "]
        ),
    }

    # Minimum chunk length (characters) — discard tiny fragments
    MIN_CHUNK_LENGTH = 30
    # Maximum chunk length (characters) — flag oversized chunks
    MAX_CHUNK_LENGTH = 3000

    def __init__(self, output_dir: str = "data/chunks/"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {"total_sources": 0, "total_chunks": 0, "discarded": 0}

    def _estimate_tokens(self, text: str) -> int:
        """Rough token count estimate (1 token ~ 4 characters for English)."""
        return len(text) // 4

    def _compute_hash(self, text: str) -> str:
        """SHA-256 hash for chunk deduplication."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _get_splitter_config(self, document_type: str) -> SplitterConfig:
        """Select the splitting strategy based on document type."""
        return self.SPLITTER_CONFIGS.get(
            document_type,
            self.SPLITTER_CONFIGS["default"]
        )

    def _split_qa_content(self, text: str) -> list[str]:
        """
        Split FAQ content on question-answer boundaries.
        Detects patterns like:
          Q: ... / A: ...
          **Question:** ... / **Answer:** ...
          Lines starting with "?" or numbered questions
        """
        # Pattern: lines that look like a question header
        qa_pattern = re.compile(
            r'(?:^|\n)(?:Q[:.\s]|\d+[.)\s]|\*\*.*\?\*\*|.*\?\s*$)',
            re.MULTILINE | re.IGNORECASE
        )

        # Split on question boundaries
        parts = qa_pattern.split(text)
        matches = qa_pattern.findall(text)

        chunks = []
        for i, match in enumerate(matches):
            # Recombine question header with its answer body
            answer = parts[i + 1] if i + 1 < len(parts) else ""
            qa_chunk = f"{match.strip()}\n{answer.strip()}"
            if len(qa_chunk.strip()) > self.MIN_CHUNK_LENGTH:
                chunks.append(qa_chunk.strip())

        # Fallback: if QA detection failed, use standard splitting
        if not chunks:
            logger.warning("QA splitting failed, falling back to standard split")
            config = self.SPLITTER_CONFIGS["default"]
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=config.chunk_size * 4,
                chunk_overlap=config.chunk_overlap * 4,
                separators=config.separators
            )
            chunks = splitter.split_text(text)

        return chunks

    def _split_standard(self, text: str, config: SplitterConfig) -> list[str]:
        """Split text using LangChain RecursiveCharacterTextSplitter."""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size * 4,       # Convert tokens to chars (approx)
            chunk_overlap=config.chunk_overlap * 4,
            separators=config.separators,
            length_function=len,
            is_separator_regex=False
        )
        return splitter.split_text(text)

    def _validate_chunk(self, text: str) -> bool:
        """Validate chunk quality — discard fragments that are too small or empty."""
        stripped = text.strip()
        if len(stripped) < self.MIN_CHUNK_LENGTH:
            return False
        if re.match(r'^[-=\s]*Page\s*\d+[-=\s]*$', stripped, re.IGNORECASE):
            return False
        if not re.search(r'[a-zA-Z]{3,}', stripped):
            return False
        return True

    def chunk_source(self, source: dict, text: str) -> list[Chunk]:
        """
        Chunk a single source's text into enriched chunks.

        Args:
            source: Source metadata dict from sources.json
            text: Raw extracted text from scraper

        Returns:
            List of Chunk objects with full metadata
        """
        source_id = source["id"]
        document_type = source.get("type", "default")
        config = self._get_splitter_config(document_type)

        logger.info(f"Chunking [{source_id}] with strategy: {document_type} "
                    f"(size={config.chunk_size}, overlap={config.chunk_overlap})")

        # Split text using the appropriate strategy
        if config.is_qa_mode:
            raw_chunks = self._split_qa_content(text)
        else:
            raw_chunks = self._split_standard(text, config)

        # Validate and enrich chunks
        chunks = []
        seen_hashes = set()
        valid_index = 0
        for raw_chunk in raw_chunks:
            if not self._validate_chunk(raw_chunk):
                self.stats["discarded"] += 1
                continue

            # Deduplicate by content hash
            chunk_hash = self._compute_hash(raw_chunk)
            if chunk_hash in seen_hashes:
                self.stats["discarded"] += 1
                logger.debug(f"  Duplicate chunk skipped: {chunk_hash}")
                continue
            seen_hashes.add(chunk_hash)

            # Warn on oversized chunks
            if len(raw_chunk.strip()) > self.MAX_CHUNK_LENGTH:
                logger.warning(f"  Oversized chunk in [{source_id}]: "
                              f"{len(raw_chunk.strip())} chars "
                              f"(may indicate splitting issue)")

            chunk = Chunk(
                chunk_id=f"{source_id}-chunk-{valid_index:03d}",
                text=raw_chunk.strip(),
                source_id=source_id,
                source_url=source.get("url", ""),
                scheme_name=source.get("scheme", ""),
                document_type=document_type,
                category=source.get("category", ""),
                scraped_at=source.get("last_scraped",
                           datetime.now(timezone.utc).isoformat()),
                chunk_index=valid_index,
                total_chunks=0,   # Updated after all chunks processed
                token_count=self._estimate_tokens(raw_chunk),
                content_hash=chunk_hash
            )
            chunks.append(chunk)
            valid_index += 1

        # Backfill total_chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        logger.info(f"  [{source_id}] -> {len(chunks)} chunks "
                    f"(discarded {len(raw_chunks) - len(chunks)} fragments)")

        return chunks

    def chunk_all(self, scraped_results: list[dict]) -> list[Chunk]:
        """
        Chunk all scraped sources.

        Args:
            scraped_results: List of {"source": dict, "text": str}

        Returns:
            Complete list of Chunk objects across all sources
        """
        all_chunks = []

        for result in scraped_results:
            source = result["source"]
            text = result["text"]
            chunks = self.chunk_source(source, text)
            all_chunks.extend(chunks)
            self.stats["total_sources"] += 1

        self.stats["total_chunks"] = len(all_chunks)

        # Save chunks to disk
        self._save_chunks(all_chunks)
        self._log_summary()

        return all_chunks

    def chunk_from_files(self, input_dir: str) -> list[Chunk]:
        """
        Chunk all scraped text files in a directory.
        Reads .txt files and their corresponding .meta.json files.

        Args:
            input_dir: Path to directory with scraped .txt + .meta.json files

        Returns:
            Complete list of Chunk objects
        """
        input_path = Path(input_dir)
        scraped_results = []

        txt_files = sorted(input_path.glob("*.txt"))
        logger.info(f"Found {len(txt_files)} scraped files to chunk")

        for txt_file in txt_files:
            source_id = txt_file.stem
            meta_file = input_path / f"{source_id}.meta.json"

            # Load text
            with open(txt_file, "r", encoding="utf-8") as f:
                text = f.read()

            # Load metadata
            source_meta = {"id": source_id, "type": "default"}
            if meta_file.exists():
                with open(meta_file, "r", encoding="utf-8") as f:
                    source_meta = json.load(f)

            scraped_results.append({
                "source": source_meta,
                "text": text
            })

        return self.chunk_all(scraped_results)

    def _save_chunks(self, chunks: list[Chunk]):
        """Persist chunks to JSON for the embedding step."""
        output_file = self.output_dir / "chunks.json"
        data = [chunk.to_dict() for chunk in chunks]
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(chunks)} chunks to {output_file}")

    def _log_summary(self):
        """Log chunking run summary."""
        logger.info("=" * 60)
        logger.info("CHUNKING SUMMARY")
        logger.info(f"  Sources processed: {self.stats['total_sources']}")
        logger.info(f"  Total chunks:      {self.stats['total_chunks']}")
        logger.info(f"  Discarded:         {self.stats['discarded']}")
        logger.info("=" * 60)


# ── CLI Entry Point ───────────────────────────────────────────


def main():
    """CLI entry point for the chunking service."""
    parser = argparse.ArgumentParser(
        description="Mutual Fund FAQ Chunking Service"
    )
    parser.add_argument(
        "--input",
        default="data/scraped/",
        help="Input directory with scraped .txt + .meta.json files"
    )
    parser.add_argument(
        "--output",
        default="data/chunks/",
        help="Output directory for chunks JSON (default: data/chunks/)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    logger.info(f"Starting chunker (input={args.input}, output={args.output})")

    chunker = ChunkingService(output_dir=args.output)
    chunks = chunker.chunk_from_files(args.input)

    logger.info(f"Chunking complete: {len(chunks)} chunks generated")


if __name__ == "__main__":
    main()
