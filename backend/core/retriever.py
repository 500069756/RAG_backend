"""
Retriever — Phase 7.3
Chroma Cloud vector search for retrieving relevant chunks at query time.

Responsibilities:
    - Resolve the active (latest) versioned collection
    - Embed user query using the same model as index time
    - Execute similarity search with metadata filtering
    - Return ranked chunks with scores and metadata
"""

import logging
import os

import chromadb

logger = logging.getLogger(__name__)


class Retriever:
    """Retrieves relevant chunks from Chroma Cloud via similarity search."""

    TOP_K = 5                          # Number of top results to return
    SIMILARITY_THRESHOLD = 0.65        # Minimum cosine similarity to include
    BASE_COLLECTION = "mutual_fund_faq"

    def __init__(
        self,
        embedding_service,
        api_key: str | None = None,
        tenant: str | None = None,
        database: str | None = None,
    ):
        """
        Args:
            embedding_service: EmbeddingService instance (for query embedding)
            api_key: Chroma Cloud API key
            tenant: Chroma Cloud tenant
            database: Chroma Cloud database
        """
        self.embedding_service = embedding_service
        self.api_key = api_key or os.environ.get("CHROMA_API_KEY", "")
        self.tenant = tenant or os.environ.get("CHROMA_TENANT", "")
        self.database = database or os.environ.get("CHROMA_DATABASE", "")
        self.base_collection = os.environ.get(
            "CHROMA_COLLECTION_BASE",
            self.BASE_COLLECTION
        )

        # Connect to Chroma Cloud
        self.client = chromadb.HttpClient(
            host="api.trychroma.com",
            port=443,
            ssl=True,
            headers={"Authorization": f"Bearer {self.api_key}"},
            tenant=self.tenant,
            database=self.database
        )

        self._collection = None
        logger.info("Retriever initialized (Chroma Cloud)")

    def _get_collection(self) -> chromadb.Collection:
        """Resolve the active (latest) versioned collection."""
        if self._collection is not None:
            return self._collection

        all_collections = self.client.list_collections()
        versions = sorted([
            c.name for c in all_collections
            if c.name.startswith(self.base_collection + "_")
        ])

        if not versions:
            raise RuntimeError(
                f"No indexed collections found (prefix: {self.base_collection}_)"
            )

        latest = versions[-1]
        self._collection = self.client.get_collection(latest)
        logger.info(f"Using collection: {latest} "
                    f"({self._collection.count()} documents)")
        return self._collection

    def refresh_collection(self):
        """Force refresh to pick up newly indexed collection."""
        self._collection = None
        logger.info("Collection cache cleared — will re-resolve on next query")

    def retrieve(
        self,
        query: str,
        scheme_filter: str | None = None,
        category_filter: str | None = None,
        top_k: int | None = None
    ) -> list[dict]:
        """
        Retrieve relevant chunks for a user query.

        Args:
            query: User's question text
            scheme_filter: Optional scheme name filter (e.g., "HDFC Top 100 Fund")
            category_filter: Optional category filter (e.g., "large-cap")
            top_k: Override default TOP_K

        Returns:
            List of dicts with keys:
                text, source_url, scheme_name, document_type,
                category, scraped_at, similarity_score, chunk_id
        """
        k = top_k or self.TOP_K
        collection = self._get_collection()

        # Embed the query using the SAME model as index time
        query_vector = self.embedding_service.embed_single(query)

        # Build metadata filter
        where_filter = self._build_filter(scheme_filter, category_filter)

        # Execute similarity search
        search_kwargs = {
            "query_embeddings": [query_vector],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"]
        }
        if where_filter:
            search_kwargs["where"] = where_filter

        results = collection.query(**search_kwargs)

        # Parse and filter results
        chunks = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, (chunk_id, doc, meta, dist) in enumerate(
            zip(ids, documents, metadatas, distances)
        ):
            similarity = 1 - dist  # Chroma cosine distance → similarity

            # Apply similarity threshold
            if similarity < self.SIMILARITY_THRESHOLD:
                logger.debug(f"  Skipping chunk {chunk_id}: "
                            f"sim={similarity:.3f} < {self.SIMILARITY_THRESHOLD}")
                continue

            chunks.append({
                "chunk_id": chunk_id,
                "text": doc,
                "source_url": meta.get("source_url", ""),
                "scheme_name": meta.get("scheme_name", ""),
                "document_type": meta.get("document_type", ""),
                "category": meta.get("category", ""),
                "scraped_at": meta.get("scraped_at", ""),
                "similarity_score": round(similarity, 4),
                "chunk_index": meta.get("chunk_index", 0),
                "token_count": meta.get("token_count", 0),
            })

        logger.info(f"Retrieved {len(chunks)}/{k} chunks for query: "
                    f"\"{query[:60]}...\"")
        if chunks:
            logger.info(f"  Top similarity: {chunks[0]['similarity_score']:.3f} "
                        f"({chunks[0]['scheme_name']})")

        return chunks

    def _build_filter(
        self,
        scheme_filter: str | None,
        category_filter: str | None
    ) -> dict | None:
        """Build Chroma metadata filter from optional parameters."""
        conditions = []

        if scheme_filter:
            conditions.append({"scheme_name": {"$eq": scheme_filter}})
        if category_filter:
            conditions.append({"category": {"$eq": category_filter}})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}
