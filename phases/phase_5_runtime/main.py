"""
Phase 5 — Main Entry Point
Initializes and runs the complete RAG query pipeline.

Usage:
    python -m phases.phase_5_runtime.main --mode test
    python -m phases.phase_5_runtime.main --mode serve
"""

import argparse
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from phases.phase_5_runtime.guardrails import InputGuardrail, OutputGuardrail
from phases.phase_5_runtime.pipeline import RAGPipeline
from phases.phase_5_runtime.session_manager import SessionManager

logger = logging.getLogger(__name__)


def initialize_pipeline():
    """
    Initialize all Phase 5 components.
    
    Returns:
        Tuple of (RAGPipeline, SessionManager)
    """
    logger.info("Initializing Phase 5 components...")

    # Import dependencies
    try:
        from core.retriever import Retriever
        from phases.phase_4_2_embedding.embedder import EmbeddingService
    except ImportError as e:
        logger.error(f"Failed to import dependencies: {e}")
        raise

    # Initialize embedding service
    logger.info("Loading embedding service...")
    embedding_service = EmbeddingService()

    # Initialize retriever
    logger.info("Loading retriever...")
    retriever = Retriever(embedding_service=embedding_service)

    # Initialize RAG pipeline
    logger.info("Loading RAG pipeline...")
    pipeline = RAGPipeline(
        embedding_service=embedding_service,
        retriever=retriever
    )

    # Initialize session manager
    session_mgr = SessionManager()

    logger.info("✅ Phase 5 initialization complete")
    return pipeline, session_mgr


def run_test_queries(pipeline: RAGPipeline):
    """Run test queries to verify pipeline works."""
    test_queries = [
        "What is the NAV of HDFC Mid Cap Fund?",
        "What is the minimum SIP amount?",
        "What is the expense ratio?",
        "What is the fund size?",
        "Should I invest in HDFC Equity Fund?",  # Should trigger advisory refusal
    ]

    print("\n" + "="*70)
    print("🧪 Running Test Queries")
    print("="*70 + "\n")

    for i, query in enumerate(test_queries, 1):
        print(f"\nQuery {i}: {query}")
        print("-" * 70)

        result = pipeline.query(query)

        if result.is_refusal:
            print(f"🚫 REFUSAL ({result.confidence_score:.2f})")
        else:
            print(f"✅ Response (confidence: {result.confidence_score:.3f})")

        print(f"\n{result.response}")

        if result.source_url:
            print(f"\n📎 Source: {result.source_url}")
        if result.last_updated:
            print(f"📅 Last updated: {result.last_updated}")
        print(f"⏱️  Time: {result.processing_time_ms:.0f}ms")
        print("="*70)


def main():
    """CLI entry point for Phase 5."""
    parser = argparse.ArgumentParser(description="Phase 5: RAG Query Pipeline")
    parser.add_argument(
        "--mode",
        choices=["test", "serve", "init"],
        default="test",
        help="Mode: test (run queries), serve (start Flask), init (just initialize)"
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Single query to test (instead of running all test queries)"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    try:
        # Initialize pipeline
        pipeline, session_mgr = initialize_pipeline()

        if args.mode == "init":
            print("✅ Phase 5 initialized successfully!")
            return

        elif args.mode == "test":
            if args.query:
                # Run single query
                print(f"\n🔍 Testing query: {args.query}\n")
                result = pipeline.query(args.query)

                if result.is_refusal:
                    print(f"🚫 Refusal: {result.response}")
                else:
                    print(f"✅ Response (confidence: {result.confidence_score:.3f})")
                    print(f"\n{result.response}")

                    if result.source_url:
                        print(f"\n📎 Source: {result.source_url}")
                    if result.last_updated:
                        print(f"📅 Last updated: {result.last_updated}")
                    print(f"⏱️  Processing time: {result.processing_time_ms:.0f}ms")
            else:
                # Run all test queries
                run_test_queries(pipeline)

        elif args.mode == "serve":
            # Start Flask server
            print("\n🚀 Starting Flask server...")
            print("Use: python app.py (from backend directory)\n")
            print("Phase 5 components are ready to be integrated with Flask app.")

    except Exception as e:
        logger.error(f"Phase 5 initialization failed: {e}", exc_info=True)
        print(f"\n❌ Failed to initialize Phase 5: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
