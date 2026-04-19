"""
Retriever — FAISS local vector search
Retrieves relevant chunks at query time using a local FAISS index.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import faiss
import numpy as np

from core.embedder import Embedder

logger = logging.getLogger(__name__)

INDEX_DIR = Path(__file__).parent.parent / "data" / "index"


class Retriever:
    """Retrieves relevant chunks from a local FAISS index."""

    TOP_K = 5
    SIMILARITY_THRESHOLD = 0.15

    def __init__(self, embedder: Embedder, index_dir: Optional[Path] = None):
        self.embedder = embedder
        self.index_dir = index_dir or INDEX_DIR
        self.index: Optional[faiss.IndexFlatIP] = None
        self.chunks: list[dict] = []

        if self._index_exists():
            self.load()

    def _index_exists(self) -> bool:
        return (self.index_dir / "faiss.index").exists() and (
            self.index_dir / "chunks.json"
        ).exists()

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    def build_index(self, chunks: list[dict], vectors: np.ndarray):
        """Build FAISS index from chunks and their embedding vectors."""
        dim = vectors.shape[1]
        self.index = faiss.IndexFlatIP(dim)  # inner product on L2-normed = cosine
        self.index.add(vectors)
        self.chunks = chunks
        logger.info(f"FAISS index built: {len(chunks)} chunks, {dim}-dim")

    def save(self):
        """Persist index and chunk metadata to disk."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.index_dir / "faiss.index"))
        with open(self.index_dir / "chunks.json", "w", encoding="utf-8") as f:
            json.dump(self.chunks, f, ensure_ascii=False, indent=2)
        logger.info(f"Index saved to {self.index_dir}")

    def load(self):
        """Load index and chunk metadata from disk."""
        self.index = faiss.read_index(str(self.index_dir / "faiss.index"))
        with open(self.index_dir / "chunks.json", "r", encoding="utf-8") as f:
            self.chunks = json.load(f)
        logger.info(f"Index loaded: {len(self.chunks)} chunks")

    def retrieve(
        self,
        query: str,
        scheme_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """
        Retrieve relevant chunks for a user query.

        Returns list of dicts with keys:
            text, source_url, scheme_name, document_type,
            category, scraped_at, similarity_score, chunk_id
        """
        if self.index is None or not self.chunks:
            logger.warning("No index loaded")
            return []

        k = min(top_k or self.TOP_K, len(self.chunks))
        query_vec = self.embedder.embed_single(query).reshape(1, -1)

        # Search more than needed to allow for post-filtering
        search_k = min(k * 3, len(self.chunks))
        scores, indices = self.index.search(query_vec, search_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            if score < self.SIMILARITY_THRESHOLD:
                continue

            chunk = self.chunks[idx]

            # Apply metadata filters
            if scheme_filter and chunk.get("scheme_name", "").lower() != scheme_filter.lower():
                continue
            if category_filter and chunk.get("category", "").lower() != category_filter.lower():
                continue

            results.append({
                "chunk_id": chunk.get("chunk_id", str(idx)),
                "text": chunk["text"],
                "source_url": chunk.get("source_url", ""),
                "scheme_name": chunk.get("scheme_name", ""),
                "document_type": chunk.get("document_type", ""),
                "category": chunk.get("category", ""),
                "scraped_at": chunk.get("scraped_at", ""),
                "similarity_score": round(float(score), 4),
            })

            if len(results) >= k:
                break

        logger.info(f"Retrieved {len(results)}/{k} chunks for: \"{query[:60]}\"")
        return results
