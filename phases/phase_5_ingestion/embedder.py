"""
Embedding Service — Phase 4.1
Generates and caches vector embeddings using HuggingFace Inference API.

Responsibilities:
    - Batch embedding at INDEX TIME (daily sync via GitHub Actions)
    - Single embedding at QUERY TIME (user requests via Flask)
    - SHA-256+model-keyed disk cache to avoid re-embedding unchanged chunks
    - Retry with exponential backoff for rate limits and model loading
    - Model consistency enforcement (same model for index + query)

Usage:
    python -m ingestion.embedder --input data/chunks/ --cache data/embeddings_cache/
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates and caches embeddings using HuggingFace Inference API."""

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    HF_API_BASE = "https://api-inference.huggingface.co/pipeline/feature-extraction"

    BATCH_SIZE = 32              # Max texts per API request
    RATE_LIMIT_DELAY = 1.0       # Seconds between batches (free tier)
    MAX_RETRIES = 3              # Retry count per batch
    RETRY_BACKOFF = [2, 5, 15]   # Backoff seconds
    REQUEST_TIMEOUT = 60         # Timeout per API call

    def __init__(
        self,
        api_token: str | None = None,
        model: str | None = None,
        cache_dir: str = "data/embeddings_cache/"
    ):
        self.api_token = api_token or os.environ.get("HF_API_TOKEN")
        self.model = model or os.environ.get("HF_EMBEDDING_MODEL", self.DEFAULT_MODEL)
        self.api_url = f"{self.HF_API_BASE}/{self.model}"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_cache()
        self.stats = {"total": 0, "cache_hits": 0, "api_calls": 0, "failures": 0}

        if not self.api_token:
            raise ValueError(
                "HF_API_TOKEN is required. Set it as an environment variable "
                "or pass it to EmbeddingService(api_token=...)"
            )

        logger.info(f"EmbeddingService initialized: model={self.model}")

    # ── Cache Management ─────────────────────────────────────

    def _cache_key(self, text: str) -> str:
        """Generate deterministic cache key from model + text content."""
        return hashlib.sha256(
            f"{self.model}:{text}".encode("utf-8")
        ).hexdigest()[:24]

    def _load_cache(self) -> dict:
        """Load embedding cache index from disk."""
        cache_file = self.cache_dir / "cache_index.json"
        if cache_file.exists():
            with open(cache_file, "r") as f:
                cache = json.load(f)
            logger.info(f"Loaded embedding cache: {len(cache)} entries")
            return cache
        return {}

    def _save_cache(self):
        """Persist embedding cache index to disk."""
        cache_file = self.cache_dir / "cache_index.json"
        with open(cache_file, "w") as f:
            json.dump(self.cache, f)
        logger.info(f"Saved embedding cache: {len(self.cache)} entries")

    def _get_cached(self, text: str) -> list[float] | None:
        """Look up embedding from local cache."""
        key = self._cache_key(text)
        if key in self.cache:
            # Load the actual vector from disk
            vector_file = self.cache_dir / f"{key}.json"
            if vector_file.exists():
                with open(vector_file, "r") as f:
                    return json.load(f)
        return None

    def _set_cached(self, text: str, embedding: list[float]):
        """Store embedding in local cache (model-aware key)."""
        key = self._cache_key(text)
        # Save vector to individual file
        vector_file = self.cache_dir / f"{key}.json"
        with open(vector_file, "w") as f:
            json.dump(embedding, f)
        # Update cache index
        self.cache[key] = {
            "model": self.model,
            "dimensions": len(embedding),
            "text_preview": text[:80]
        }

    # ── HuggingFace API Calls ────────────────────────────────

    def _call_hf_api(self, texts: list[str]) -> list[list[float]]:
        """
        Call HuggingFace Inference API with retry logic.

        Args:
            texts: List of strings to embed (max BATCH_SIZE)

        Returns:
            List of embedding vectors
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
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.REQUEST_TIMEOUT
                )

                if response.status_code == 200:
                    result = response.json()
                    self.stats["api_calls"] += 1
                    return result

                elif response.status_code == 429:
                    # Rate limited — back off
                    wait = self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)]
                    logger.warning(f"HF API rate limited, waiting {wait}s "
                                   f"(attempt {attempt+1})")
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
                        self.stats["failures"] += 1
                        raise Exception(
                            f"HF API failed after {self.MAX_RETRIES} retries: "
                            f"HTTP {response.status_code}"
                        )
                    time.sleep(self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)])

            except requests.exceptions.Timeout:
                logger.error(f"HF API timeout (attempt {attempt+1})")
                if attempt == self.MAX_RETRIES - 1:
                    self.stats["failures"] += 1
                    raise
                time.sleep(self.RETRY_BACKOFF[min(attempt, len(self.RETRY_BACKOFF) - 1)])

            except requests.exceptions.ConnectionError as e:
                logger.error(f"HF API connection error (attempt {attempt+1}): {e}")
                if attempt == self.MAX_RETRIES - 1:
                    self.stats["failures"] += 1
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
        """
        self.stats["total"] += 1

        # Check cache first (even for queries, they might repeat)
        cached = self._get_cached(text)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        # Call API for single text
        embeddings = self._call_hf_api([text])
        if embeddings:
            self._set_cached(text, embeddings[0])
            return embeddings[0]

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

        # Separate cached vs. uncached chunks
        to_embed = []       # (index, text) tuples for uncached chunks
        results = [None] * total

        for i, chunk in enumerate(chunks):
            self.stats["total"] += 1
            cached = self._get_cached(chunk["text"])
            if cached:
                self.stats["cache_hits"] += 1
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
            embeddings = self._call_hf_api(batch_texts)

            if not embeddings:
                logger.error(f"  Batch {batch_num} returned empty — skipping")
                self.stats["failures"] += len(batch)
                continue

            # Store results and cache
            for (orig_idx, text), embedding in zip(batch, embeddings):
                results[orig_idx] = embedding
                self._set_cached(text, embedding)

            # Rate limiting between batches
            if batch_start + self.BATCH_SIZE < len(to_embed):
                time.sleep(self.RATE_LIMIT_DELAY)

        # Save cache to disk
        self._save_cache()

        # Enrich chunks with embeddings
        enriched_chunks = []
        for chunk, embedding in zip(chunks, results):
            enriched = chunk.copy()
            enriched["embedding"] = embedding
            enriched_chunks.append(enriched)

        self._log_summary()
        return enriched_chunks

    def _log_summary(self):
        """Log embedding run summary."""
        logger.info("=" * 60)
        logger.info("EMBEDDING SUMMARY")
        logger.info(f"  Total texts:    {self.stats['total']}")
        logger.info(f"  Cache hits:     {self.stats['cache_hits']}")
        logger.info(f"  API calls:      {self.stats['api_calls']}")
        logger.info(f"  Failures:       {self.stats['failures']}")
        cache_rate = (self.stats['cache_hits'] / max(self.stats['total'], 1)) * 100
        logger.info(f"  Cache hit rate: {cache_rate:.1f}%")
        logger.info("=" * 60)


# ── CLI Entry Point ───────────────────────────────────────────


def main():
    """CLI entry point for the embedding service."""
    parser = argparse.ArgumentParser(
        description="Mutual Fund FAQ Embedding Service"
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

    # Embed
    embedder = EmbeddingService(cache_dir=args.cache)
    enriched = embedder.embed_chunks(chunks)

    # Save embedded chunks
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "embedded_chunks.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(enriched)} embedded chunks to {output_file}")


if __name__ == "__main__":
    main()
