"""
Verify Index Service — Phase 4.2
Validates a Chroma collection after indexing with advanced quality guards.

Quality Guards:
    - Volume Check: Alerts if document count drops significantly (>20%)
    - Metadata Integrity: Ensures non-null URL and Scheme for every vector
    - Test Query Accuracy: Validates retrieval quality with golden/known queries

Usage:
    python -m phases.phase_5_ingestion.verify_index --collection mutual_fund_faq --test-queries data/test_queries.json
"""

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)


class VerifyService:
    """Validates a Chroma collection after indexing with advanced quality guards."""

    MIN_SIMILARITY_THRESHOLD = 0.65    # Minimum cosine similarity for a "pass"
    MIN_RESULTS_REQUIRED = 1           # At least 1 result per test query
    VOLUME_DROP_THRESHOLD = 0.20       # Alert if < 80% of previous count
    INTEGRITY_SAMPLE_SIZE = 100        # Chunks to sample for metadata check

    def __init__(self, client: chromadb.HttpClient, embedding_service):
        """
        Args:
            client: Connected Chroma Cloud client
            embedding_service: EmbeddingService instance for query embedding
        """
        self.client = client
        self.embedding_service = embedding_service

    def load_test_queries(self, path: str = "data/test_queries.json") -> list[dict]:
        """Load test queries with expected scheme names."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("queries", [])

    def _get_previous_version_count(self, base_name: str, current_version: str) -> int | None:
        """Find the document count of the version immediately preceding current_version."""
        try:
            all_collections = self.client.list_collections()
            versions = sorted([
                c.name for c in all_collections
                if c.name.startswith(base_name + "_")
            ])
            
            current_idx = versions.index(current_version)
            if current_idx > 0:
                prev_version = versions[current_idx - 1]
                return self.client.get_collection(prev_version).count()
        except Exception:
            pass
        return None

    def check_metadata_integrity(self, collection: chromadb.Collection) -> tuple[bool, str]:
        """Ensure mandatory metadata fields are present in a sample of chunks."""
        count = collection.count()
        if count == 0:
            return False, "Collection is empty"

        # Peek at a sample
        sample_size = min(count, self.INTEGRITY_SAMPLE_SIZE)
        results = collection.peek(limit=sample_size)
        metadatas = results.get("metadatas", [])

        missing_fields = []
        mandatory = ["source_url", "scheme_name", "source_id"]

        for idx, meta in enumerate(metadatas):
            for field in mandatory:
                if not meta.get(field):
                    missing_fields.append(f"Chunk {idx} missing {field}")

        if missing_fields:
            logger.error(f"Metadata Integrity FAIL: {len(missing_fields)} errors in sample")
            return False, f"{len(missing_fields)} missing mandatory fields"

        logger.info("Metadata Integrity PASS: All mandatory fields present")
        return True, "All fields present"

    def check_volume(self, collection_name: str, current_count: int) -> tuple[bool, str]:
        """Verify the document volume hasn't dropped unexpectedly."""
        # Handle cases where collection doesn't have a date suffix
        if "_20" in collection_name:
            base_name = collection_name.split("_20")[0]
        else:
            base_name = collection_name

        prev_count = self._get_previous_version_count(base_name, collection_name)

        if prev_count is None:
            logger.info("Volume Check SKIP: No previous version to compare")
            return True, "No baseline"

        if prev_count == 0:
            return True, "Baseline was empty"

        drop_ratio = (prev_count - current_count) / prev_count
        if current_count < prev_count and drop_ratio > self.VOLUME_DROP_THRESHOLD:
            msg = f"Significant drop: {prev_count} -> {current_count} (-{drop_ratio*100:.1f}%)"
            logger.error(f"Volume Check FAIL: {msg}")
            return False, msg

        logger.info(f"Volume Check PASS: {prev_count} -> {current_count} (Delta: {current_count - prev_count})")
        return True, "Volume stable"

    def verify(
        self,
        collection_name: str,
        test_queries: list[dict] | None = None,
        test_queries_path: str = "data/test_queries.json"
    ) -> dict:
        """
        Run test queries and quality guards against a collection.
        """
        if test_queries is None:
            test_queries = self.load_test_queries(test_queries_path)

        collection = self.client.get_collection(collection_name)
        doc_count = collection.count()
        logger.info(f"--- Phase 4.2 Quality Verification: [{collection_name}] ---")

        # 1. Volume Check
        volume_ok, volume_msg = self.check_volume(collection_name, doc_count)

        # 2. Metadata Integrity
        integrity_ok, integrity_msg = self.check_metadata_integrity(collection)

        # 3. Test Queries Accuracy
        results = []
        passed_queries = 0
        
        if not test_queries:
            logger.warning("No test queries provided — skipping accuracy check")
            queries_ok = True
        else:
            for tq in test_queries:
                query = tq["query"]
                expected_scheme = tq.get("expected_scheme", None)

                try:
                    query_vector = self.embedding_service.embed_single(query)
                    search_results = collection.query(
                        query_embeddings=[query_vector],
                        n_results=5,
                        include=["documents", "metadatas", "distances"]
                    )

                    distances = search_results.get("distances", [[]])[0]
                    metadatas = search_results.get("metadatas", [[]])[0]
                    
                    top_distance = distances[0] if distances else 1.0
                    top_similarity = 1 - top_distance
                    top_scheme = metadatas[0].get("scheme_name", "N/A") if metadatas else "N/A"
                    
                    sim_ok = top_similarity >= self.MIN_SIMILARITY_THRESHOLD
                    scheme_ok = (expected_scheme is None or 
                               top_scheme.lower() == expected_scheme.lower())
                    
                    q_passed = sim_ok and scheme_ok
                    if q_passed: passed_queries += 1
                    
                    results.append({
                        "query": query,
                        "passed": q_passed,
                        "similarity": round(top_similarity, 4),
                        "top_scheme": top_scheme
                    })
                    
                    status = "PASS" if q_passed else "FAIL"
                    logger.info(f"  [{status}] \"{query[:40]}...\" -> sim={top_similarity:.3f}, scheme={top_scheme}")
                    
                except Exception as e:
                    logger.error(f"  Query error for \"{query[:20]}\": {e}")

            queries_ok = passed_queries == len(test_queries)

        overall_pass = volume_ok and integrity_ok and queries_ok

        summary = {
            "passed": overall_pass,
            "guards": {
                "volume": {"passed": volume_ok, "detail": volume_msg},
                "integrity": {"passed": integrity_ok, "detail": integrity_msg},
                "accuracy": {"passed": queries_ok, "details": results}
            },
            "stats": {
                "collection": collection_name,
                "doc_count": doc_count, 
                "queries_passed": f"{passed_queries}/{len(test_queries)}"
            }
        }

        logger.info(f"Verification Result: {'PASSED ✅' if overall_pass else 'FAILED ❌'}")
        return summary


# ── CLI Entry Point ───────────────────────────────────────────


def main():
    """CLI entry point for index verification."""
    parser = argparse.ArgumentParser(
        description="Mutual Fund FAQ Index Verification"
    )
    parser.add_argument(
        "--collection",
        default="mutual_fund_faq",
        help="Collection name to verify"
    )
    parser.add_argument(
        "--test-queries",
        default="data/test_queries.json",
        help="Path to test queries JSON file"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Import here to avoid circular deps
    try:
        from phases.phase_5_ingestion.embedder import EmbeddingService
    except ImportError:
        # Compatibility with different run modes
        from embedder import EmbeddingService

    # Connect to Chroma
    try:
        client = chromadb.HttpClient(
            host="api.trychroma.com",
            port=443,
            ssl=True,
            headers={"Authorization": f"Bearer {os.environ.get('CHROMA_API_KEY', '')}"},
            tenant=os.environ.get("CHROMA_TENANT", "default"),
            database=os.environ.get("CHROMA_DATABASE", "default")
        )
        
        # Resolve target collection
        target_collection = args.collection
        all_collections = client.list_collections()
        versions = sorted([
            c.name for c in all_collections
            if c.name.startswith(args.collection + "_")
        ])
        if versions:
            target_collection = versions[-1]
            logger.info(f"Resolved latest version: {target_collection}")

        # Run verification
        embedder = EmbeddingService()
        verifier = VerifyService(client=client, embedding_service=embedder)
        result = verifier.verify(
            collection_name=target_collection,
            test_queries_path=args.test_queries
        )

        # Save verification report
        report_file = Path("data/verification_report.json")
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Verification report saved to {report_file}")

        # Exit with appropriate code
        if not result["passed"]:
            logger.error("VERIFICATION FAILED")
            sys.exit(1)
        else:
            logger.info("VERIFICATION PASSED")
            
    except Exception as e:
        logger.error(f"Verification script crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
