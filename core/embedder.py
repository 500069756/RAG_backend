"""
Local Embedder — TF-IDF + TruncatedSVD
Produces dense vector embeddings without any external API.
"""

import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)

INDEX_DIR = Path(__file__).parent.parent / "data" / "index"


class Embedder:
    """TF-IDF + SVD embedder that runs entirely locally."""

    DIMENSIONS = 128
    MAX_FEATURES = 5000

    def __init__(self, index_dir: Optional[Path] = None):
        self.index_dir = index_dir or INDEX_DIR
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.svd: Optional[TruncatedSVD] = None
        self._fitted = False

        # Try loading existing model
        if self._model_exists():
            self.load()

    def _model_exists(self) -> bool:
        return (self.index_dir / "vectorizer.pkl").exists() and (
            self.index_dir / "svd.pkl"
        ).exists()

    def fit(self, texts: list[str]):
        """Fit TF-IDF + SVD on a corpus of texts."""
        n_components = min(self.DIMENSIONS, len(texts) - 1, self.MAX_FEATURES)
        self.vectorizer = TfidfVectorizer(
            max_features=self.MAX_FEATURES,
            stop_words="english",
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        tfidf_matrix = self.vectorizer.fit_transform(texts)

        self.svd = TruncatedSVD(n_components=n_components, random_state=42)
        self.svd.fit(tfidf_matrix)
        self._fitted = True
        logger.info(
            f"Embedder fitted on {len(texts)} texts → {n_components}-dim vectors"
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts into dense vectors (L2-normalized)."""
        if not self._fitted:
            raise RuntimeError("Embedder not fitted. Call fit() or load() first.")
        tfidf = self.vectorizer.transform(texts)
        dense = self.svd.transform(tfidf)
        return normalize(dense, norm="l2").astype("float32")

    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        return self.embed([text])[0]

    def save(self):
        """Persist fitted model to disk."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        with open(self.index_dir / "vectorizer.pkl", "wb") as f:
            pickle.dump(self.vectorizer, f)
        with open(self.index_dir / "svd.pkl", "wb") as f:
            pickle.dump(self.svd, f)
        logger.info(f"Embedder saved to {self.index_dir}")

    def load(self):
        """Load fitted model from disk."""
        with open(self.index_dir / "vectorizer.pkl", "rb") as f:
            self.vectorizer = pickle.load(f)
        with open(self.index_dir / "svd.pkl", "rb") as f:
            self.svd = pickle.load(f)
        self._fitted = True
        logger.info(f"Embedder loaded from {self.index_dir}")
