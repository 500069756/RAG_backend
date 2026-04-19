"""
Embedding Service — Phase 4.2
Generates and caches vector embeddings using HuggingFace Inference API.

Responsibilities:
    - Batch embedding at INDEX TIME (daily sync via GitHub Actions)
    - Single embedding at QUERY TIME (user requests via Flask)
    - SHA-256+model-keyed disk cache to avoid re-embedding unchanged chunks
    - Retry with exponential backoff for rate limits and model loading
    - Model consistency enforcement (same model for index + query)
    - Quality validation (dimension check, NaN detection)

Usage:
    python -m phases.phase_4_2_embedding --input data/chunks/ --output data/embedded/
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────


@dataclass
class EmbeddingStats:
    """Tracks embedding run statistics."""
    total: int = 0
    cache_hits: int = 0
    api_calls: int = 0
    failures: int = 0
    total_time_seconds: float = 0.0

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        return (self.cache_hits / max(self.total, 1)) * 100

    @property
    def avg_time_per_embedding(self) -> float:
        """Calculate average time per embedding in milliseconds."""
        if self.total == 0:
            return 0.0
        return (self.total_time_seconds / self.total) * 1000

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "total": self.total,
            "cache_hits": self.cache_hits,
            "api_calls": self.api_calls,
            "failures": self.failures,
            "cache_hit_rate": round(self.cache_hit_rate, 2),
            "avg_time_per_embedding_ms": round(self.avg_time_per_embedding, 2),
            "total_time_seconds": round(self.total_time_seconds, 2)
        }


# ── Embedding Service ─────────────────────────────────────────


class EmbeddingService:
    """Generates and caches embeddings using HuggingFace Inference API."""

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    EXPECTED_DIMENSIONS = 384  # For BAAI/bge-small-en-v1.5
    HF_API_BASE = "https://api-inference.huggingface.co/pipeline/feature-extraction"

    BATCH_SIZE = 32              # Max texts per API request
    RATE_LIMIT_DELAY = 1.0       # Seconds between batches (free tier)
    MAX_RETRIES = 3              # Retry count per batch
    RETRY_BACKOFF = [2, 5, 15]   # Backoff seconds
    REQUEST_TIMEOUT = 60         # Timeout per API call

    def __init__(
        self,
        api_token: Optional[str] = None,
        model: Optional[str] = None,
        cache_dir: str = "data/embeddings_cache/"
    ):
        """
        Initialize Embedding Service.

        Args:
            api_token: HuggingFace API token (or set HF_API_TOKEN env var)
            model: Model name (or set HF_EMBEDDING_MODEL env var)
            cache_dir: Directory for embedding cache
        """
        self.api_token = api_token or os.environ.get("HF_API_TOKEN")
        self.model = model or os.environ.get("HF_EMBEDDING_MODEL", self.DEFAULT_MODEL)
        self.api_url = f"{self.HF_API_BASE}/{self.model}"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_cache()
        self.stats = EmbeddingStats()

        if not self.api_token:
            raise ValueError(
                "HF_API_TOKEN is required. Set it as an environment variable "
                "or pass it to EmbeddingService(api_token=...)"
            )

        logger.info(f"EmbeddingService initialized: model={self.model}")
        logger.info(f"API endpoint: {self.api_url}")
        logger.info(f"Expected dimensions: {self.EXPECTED_DIMENSIONS}")

    # ── Cache Management ─────────────────────────────────────

    def _cache_key(self, text: str) -> str:
        """
        Generate deterministic cache key from model + text content.
        Uses SHA-256 hash to ensure uniqueness.

        Args:
            text: Text to generate cache key for

        Returns:
            24-character hex cache key
        """
        return hashlib.sha256(
            f"{self.model}:{text}".encode("utf-8")
        ).hexdigest()[:24]

    def _load_cache(self) -> dict:
        """Load embedding cache index from disk."""
        cache_file = self.cache_dir / "cache_index.json"
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            logger.info(f"Loaded embedding cache: {len(cache)} entries")
            return cache
        logger.info("No existing cache found — starting fresh")
        return {}

    def _save_cache(self):
        """Persist embedding cache index to disk."""
        cache_file = self.cache_dir / "cache_index.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, indent=2)
        logger.info(f"Saved embedding cache: {len(self.cache)} entries")

    def _get_cached(self, text: str) -> Optional[list[float]]:
        """
        Look up embedding from local cache.

        Args:
            text: Text to find cached embedding for

        Returns:
            Cached embedding vector or None
        """
        key = self._cache_key(text)
        if key in self.cache:
            # Load the actual vector from disk
            vector_file = self.cache_dir / f"{key}.json"
            if vector_file.exists():
                with open(vector_file, "r", encoding="utf-8") as f:
                    embedding = json.load(f)
                # Validate cached embedding
                if self._validate_embedding(embedding):
                    return embedding
                else:
                    logger.warning(f"Invalid cached embedding for key {key} — removing")
                    del self.cache[key]
                    vector_file.unlink(missing_ok=True)
        return None

    def _set_cached(self, text: str, embedding: list[float]):
        """
        Store embedding in local cache (model-aware key).

        Args:
            text: Original text
            embedding: Embedding vector to cache
        """
        key = self._cache_key(text)
        # Save vector to individual file
        vector_file = self.cache_dir / f"{key}.json"
        with open(vector_file, "w", encoding="utf-8") as f:
            json.dump(embedding, f)
        # Update cache index
        self.cache[key] = {
            "model": self.model,
            "dimensions": len(embedding),
            "text_preview": text[:80],
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    def clear_cache(self):
        """Clear all cached embeddings."""
        for key in list(self.cache.keys()):
            vector_file = self.cache_dir / f"{key}.json"
            if vector_file.exists():
                vector_file.unlink()
        self.cache.clear()
        self._save_cache()
        logger.info("Embedding cache cleared")

    # ── Embedding Validation ─────────────────────────────────

    def _validate_embedding(self, embedding: list[float]) -> bool:
        """
        Validate embedding vector quality.

        Checks:
            - Correct dimensions
            - No NaN values
            - No infinity values
            - Non-zero magnitude

        Args:
            embedding: Embedding vector to validate

        Returns:
            True if embedding is valid
        """
        if not embedding:
            return False

        # Check dimensions
        if len(embedding) != self.EXPECTED_DIMENSIONS:
            logger.error(f"Dimension mismatch: expected {self.EXPECTED_DIMENSIONS}, "
                        f"got {len(embedding)}")
            return False

        # Check for NaN or infinity
        import math
        for i, val in enumerate(embedding):
            if math.isnan(val) or math.isinf(val):
                logger.error(f"Invalid value at index {i}: {val}")
                return False

        # Check magnitude (should not be zero vector)
        magnitude = sum(x * x for x in embedding) ** 0.5
        if magnitude < 1e-6:
            logger.error("Near-zero magnitude embedding detected")
            return False

        return True

    # ── HuggingFace API Calls ────────────────────────────────

    def _call_hf_api(self, texts: list[str]) -> list[list[float]]:
        """
        Call HuggingFace Inference API with retry logic.

        Handles:
            - Rate limiting (HTTP 429)
            - Model loading (HTTP 503)
            - Timeouts and connection errors
            - Exponential backoff

        Args:
            texts: List of strings to embed (max BATCH_SIZE)

        Returns:
            List of embedding vectors

        Raises:
            Exception: If API fails after max retries
        """
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": texts,
            "options": {
                "wait_for_model": True      # Wait if model is cold-starting
            }
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                start_time = time.time()
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.REQUEST_TIMEOUT
                )
                elapsed = time.time() - start_time

                if response.status_code == 200:
                    result = response.json()
                    self.stats.api_calls += 1
                    logger.debug(f"API call successful: {elapsed:.2f}s")

                    # Validate all embeddings
                    if not isinstance(result, list):
                        logger.error(f"Invalid API response: {result}")
                        raise Exception("API returned non-list response")

                    for i, emb in enumerate(result):
                        if not self._validate_embedding(emb):
                            logger.error(f"Invalid embedding at index {i}")
                            raise Exception(f"Invalid embedding at index {i}")

                    return result

                elif response.status_code == 429:
                    # Rate limited — back off
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    logger.warning(f"HF API rate limited, waiting {wait}s "
                                   f"(attempt {attempt+1}/{self.MAX_RETRIES})")
                    time.sleep(wait)

                elif response.status_code == 503:
                    # Model loading — wait and retry
                    try:
                        wait = response.json().get("estimated_time", 20)
                    except Exception:
                        wait = 20
                    logger.info(f"Model loading, waiting {wait:.0f}s...")
                    time.sleep(min(wait, 30))

                else:
                    logger.error(f"HF API error {response.status_code}: "
                                 f"{response.text[:200]}")
                    if attempt == self.MAX_RETRIES - 1:
                        self.stats.failures += 1
                        raise Exception(
                            f"HF API failed after {self.MAX_RETRIES} retries: "
                            f"HTTP {response.status_code}"
                        )
                    time.sleep(self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)])

            except requests.exceptions.Timeout:
                logger.error(f"HF API timeout (attempt {attempt+1}/{self.MAX_RETRIES})")
                if attempt == self.MAX_RETRIES - 1:
                    self.stats.failures += 1
                    raise
                time.sleep(self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)])

            except requests.exceptions.ConnectionError as e:
                logger.error(f"HF API connection error (attempt {attempt+1}): {e}")
                if attempt == self.MAX_RETRIES - 1:
                    self.stats.failures += 1
                    raise
                time.sleep(self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)])

        return []

    # ── Public Methods ───────────────────────────────────────

    def embed_single(self, text: str) -> list[float]:
        """
        Embed a single text string.
        Used at QUERY TIME for user queries.

        Args:
            text: The query string to embed

        Returns:
            Embedding vector (list of floats, 384 dimensions)

        Raises:
            Exception: If embedding fails
        """
        self.stats.total += 1
        start_time = time.time()

        # Check cache first (even for queries, they might repeat)
        cached = self._get_cached(text)
        if cached:
            self.stats.cache_hits += 1
            self.stats.total_time_seconds += time.time() - start_time
            return cached

        # Call API for single text
        embeddings = self._call_hf_api([text])
        if embeddings:
            self._set_cached(text, embeddings[0])
            self.stats.total_time_seconds += time.time() - start_time
            return embeddings[0]

        self.stats.failures += 1
        raise Exception(f"Failed to embed query: {text[:50]}...")

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        """
        Embed all chunks in batches.
        Used at INDEX TIME during daily sync.

        Args:
            chunks: List of chunk dicts (must have 'text' key)

        Returns:
            List of chunk dicts enriched with 'embedding' key
        """
        total = len(chunks)
        logger.info(f"Embedding {total} chunks (batch_size={self.BATCH_SIZE})")
        start_time = time.time()

        # Separate cached vs. uncached chunks
        to_embed = []       # (index, text) tuples for uncached chunks
        results = [None] * total

        for i, chunk in enumerate(chunks):
            self.stats.total += 1
            cached = self._get_cached(chunk["text"])
            if cached:
                self.stats.cache_hits += 1
                results[i] = cached
            else:
                to_embed.append((i, chunk["text"]))

        logger.info(f"  Cache hits: {total - len(to_embed)}/{total}")
        logger.info(f"  To embed:   {len(to_embed)} chunks")

        # Process uncached chunks in batches
        for batch_start in range(0, len(to_embed), self.BATCH_SIZE):
            batch = to_embed[batch_start:batch_start + self.BATCH_SIZE]
            batch_texts = [text for _, text in batch]

            batch_num = batch_start // self.BATCH_SIZE + 1
            total_batches = (len(to_embed) + self.BATCH_SIZE - 1) // self.BATCH_SIZE
            logger.info(f"  Batch {batch_num}/{total_batches}: "
                        f"embedding {len(batch_texts)} texts...")

            # Call HuggingFace API
            try:
                embeddings = self._call_hf_api(batch_texts)
            except Exception as e:
                logger.error(f"  Batch {batch_num} failed: {e}")
                self.stats.failures += len(batch)
                continue

            if not embeddings:
                logger.error(f"  Batch {batch_num} returned empty — skipping")
                self.stats.failures += len(batch)
                continue

            # Store results and cache
            for (orig_idx, text), embedding in zip(batch, embeddings):
                results[orig_idx] = embedding
                self._set_cached(text, embedding)

            # Rate limiting between batches
            if batch_start + self.BATCH_SIZE < len(to_embed):
                time.sleep(self.RATE_LIMIT_DELAY)

        self.stats.total_time_seconds = time.time() - start_time

        # Save cache to disk
        self._save_cache()

        # Enrich chunks with embeddings
        enriched_chunks = []
        for chunk, embedding in zip(chunks, results):
            if embedding is None:
                logger.warning(f"  Skipping chunk {chunk.get('chunk_index', '?')} — no embedding")
                continue

            enriched = chunk.copy()
            enriched["embedding"] = embedding
            enriched_chunks.append(enriched)

        self._log_summary()
        return enriched_chunks

    def _log_summary(self):
        """Log embedding run summary."""
        logger.info("=" * 60)
        logger.info("EMBEDDING SUMMARY")
        logger.info(f"  Total texts:    {self.stats.total}")
        logger.info(f"  Cache hits:     {self.stats.cache_hits}")
        logger.info(f"  API calls:      {self.stats.api_calls}")
        logger.info(f"  Failures:       {self.stats.failures}")
        logger.info(f"  Cache hit rate: {self.stats.cache_hit_rate:.1f}%")
        logger.info(f"  Total time:     {self.stats.total_time_seconds:.2f}s")
        logger.info(f"  Avg per embed:  {self.stats.avg_time_per_embedding:.0f}ms")
        logger.info("=" * 60)


# ── CLI Entry Point ───────────────────────────────────────────


def main():
    """CLI entry point for the embedding service."""
    parser = argparse.ArgumentParser(
        description="Phase 4.2 — Mutual Fund FAQ Embedding Service"
    )
    parser.add_argument(
        "--input",
        default="data/chunks/",
        help="Input directory containing chunks.json"
    )
    parser.add_argument(
        "--cache",
        default="data/embeddings_cache/",
        help="Directory for embedding cache"
    )
    parser.add_argument(
        "--output",
        default="data/embedded/",
        help="Output directory for embedded chunks JSON"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Embedding model name (default: BAAI/bge-small-en-v1.5)"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear embedding cache before processing"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Load chunks
    chunks_file = Path(args.input) / "chunks.json"
    if not chunks_file.exists():
        logger.error(f"Chunks file not found: {chunks_file}")
        sys.exit(1)

    with open(chunks_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    logger.info(f"Loaded {len(chunks)} chunks from {chunks_file}")

    # Initialize embedder
    try:
        embedder = EmbeddingService(
            cache_dir=args.cache,
            model=args.model
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Clear cache if requested
    if args.clear_cache:
        embedder.clear_cache()

    # Embed
    enriched = embedder.embed_chunks(chunks)

    if not enriched:
        logger.error("No embedded chunks produced — aborting")
        sys.exit(1)

    # Save embedded chunks
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "embedded_chunks.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(enriched)} embedded chunks to {output_file}")

    # Save stats
    stats_file = output_dir / "embedding_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": embedder.model,
            "stats": embedder.stats.to_dict()
        }, f, indent=2)

    logger.info(f"Embedding stats saved to {stats_file}")


if __name__ == "__main__":
    main()
