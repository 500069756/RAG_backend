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
    python -m phases.phase_4_1_chunking --input data/scraped/ --output data/chunks/
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
        """Convert chunk to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class SplitterConfig:
    """Configuration for a document-type-specific splitter."""
    chunk_size: int
    chunk_overlap: int
    separators: list[str]
    is_qa_mode: bool = False    # If True, split on Q&A boundaries instead


# ── Chunking Service ─────────────────────────────────────────


class ChunkingService:
    """Splits scraped text into semantically meaningful chunks with metadata."""

    # ── Document-type-aware splitter configs ──────────────────
    SPLITTER_CONFIGS: dict[str, SplitterConfig] = {
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
        """
        Args:
            output_dir: Directory to save chunks.json
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {
            "total_sources": 0,
            "total_chunks": 0,
            "discarded": 0
        }

    def _estimate_tokens(self, text: str) -> int:
        """
        Rough token count estimate.
        1 token ~ 4 characters for English text.
        """
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
        
        Args:
            text: Raw FAQ text
            
        Returns:
            List of Q&A chunks
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
        """
        Split text using LangChain RecursiveCharacterTextSplitter.
        
        Args:
            text: Raw text to split
            config: Splitter configuration
            
        Returns:
            List of text chunks
        """
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size * 4,       # Convert tokens to chars (approx)
            chunk_overlap=config.chunk_overlap * 4,
            separators=config.separators,
            length_function=len,
            is_separator_regex=False
        )
        return splitter.split_text(text)

    def _validate_chunk(self, text: str) -> bool:
        """
        Validate chunk quality — discard fragments that are too small or empty.
        
        Validation Rules:
        1. Minimum length >= 30 characters
        2. Not just a page marker (e.g., "--- Page 1 ---")
        3. Contains at least one word with 3+ letters
        
        Args:
            text: Chunk text to validate
            
        Returns:
            True if chunk passes validation, False otherwise
        """
        stripped = text.strip()
        
        # Rule 1: Minimum length
        if len(stripped) < self.MIN_CHUNK_LENGTH:
            return False
        
        # Rule 2: Page marker only
        if re.match(r'^[-=\s]*Page\s*\d+[-=\s]*$', stripped, re.IGNORECASE):
            return False
        
        # Rule 3: No alphabetic content
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
        valid_index = 0
        for raw_chunk in raw_chunks:
            if not self._validate_chunk(raw_chunk):
                self.stats["discarded"] += 1
                continue

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
                content_hash=self._compute_hash(raw_chunk)
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


# ── CLI Entry Point ─────────────────────────────────────────


def main():
    """CLI entry point for the chunking service."""
    parser = argparse.ArgumentParser(
        description="Phase 4.1 — Chunking Service"
    )
    parser.add_argument(
        "--input",
        default="data/scraped/",
        help="Input directory containing scraped text and metadata files"
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
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    input_dir = Path(args.input)
    sources_path = Path(args.sources)

    # Load sources metadata
    if not sources_path.exists():
        logger.error(f"Sources file not found: {sources_path}")
        sys.exit(1)

    with open(sources_path, 'r', encoding='utf-8') as f:
        sources_data = json.load(f)
    sources_map = {s["id"]: s for s in sources_data["sources"]}

    # Load scraped text files
    scraped_results = []
    txt_files = sorted(input_dir.glob("*.clean.txt"))
    
    if not txt_files:
        # Fallback to non-cleaned files
        txt_files = sorted(input_dir.glob("*.txt"))
        txt_files = [f for f in txt_files if not f.name.endswith('.meta.json')]

    if not txt_files:
        logger.error(f"No .txt files found in {input_dir}")
        sys.exit(1)

    logger.info(f"Loading {len(txt_files)} scraped files from {input_dir}")

    for txt_file in txt_files:
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

    logger.info(f"Loaded {len(scraped_results)} sources for chunking")

    # Chunk all sources
    chunker = ChunkingService(output_dir=args.output)
    chunks = chunker.chunk_all(scraped_results)

    logger.info(f"Chunking complete: {len(chunks)} chunks created")


if __name__ == "__main__":
    main()
