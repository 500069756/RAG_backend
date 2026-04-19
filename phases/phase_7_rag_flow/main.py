"""
Phase 7 — Main Orchestrator
Complete Retrieval & Generation Flow as per architecture.md Section 7.

This is the unified entry point that ties together:
    - Phase 5.1: Guardrails
    - Phase 5.2: RAG Pipeline
    - Phase 5.3: Chat API
    - Phase 5.4: Session Manager
    - core/retriever.py: Vector retrieval
    - Phase 4.2: Embedding service

Usage:
    python phases/phase_7_rag_flow/main.py --mode test
    python phases/phase_7_rag_flow/main.py --mode serve
"""

import argparse
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


def initialize_phase7():
    """
    Initialize complete Phase 7 pipeline.
    
    Returns:
        Tuple of (RAGPipeline, SessionManager)
    """
    logger.info("="*70)
    logger.info("Phase 7: Retrieval & Generation Flow - Initialization")
    logger.info("="*70)

    try:
        # Import all components
        from phases.phase_4_2_embedding.embedder import EmbeddingService
        from core.retriever import Retriever
        from phases.phase_5_runtime.guardrails import InputGuardrail, OutputGuardrail
        from phases.phase_5_runtime.pipeline import RAGPipeline
        from phases.phase_5_runtime.session_manager import SessionManager

        # Step 1: Initialize Embedding Service
        logger.info("\n[1/5] Initializing Embedding Service (Phase 4.2)...")
        embedding_service = EmbeddingService()
        logger.info(f"  ✅ Model: {embedding_service.model}")
        logger.info(f"  ✅ Dimensions: {embedding_service.EXPECTED_DIMENSIONS}")

        # Step 2: Initialize Retriever
        logger.info("\n[2/5] Initializing Retriever (core/retriever.py)...")
        retriever = Retriever(embedding_service=embedding_service)
        logger.info(f"  ✅ Top-K: {retriever.TOP_K}")
        logger.info(f"  ✅ Similarity Threshold: {retriever.SIMILARITY_THRESHOLD}")

        # Step 3: Initialize RAG Pipeline (with Groq)
        logger.info("\n[3/5] Initializing RAG Pipeline with Groq (Phase 5.2)...")
        pipeline = RAGPipeline(
            embedding_service=embedding_service,
            retriever=retriever
        )
        logger.info(f"  ✅ Primary Model: {pipeline.PRIMARY_MODEL}")
        logger.info(f"  ✅ Fallback Model: {pipeline.FALLBACK_MODEL}")
        logger.info(f"  ✅ Temperature: {pipeline.TEMPERATURE}")

        # Step 4: Initialize Guardrails
        logger.info("\n[4/5] Initializing Guardrails (Phase 5.1)...")
        input_guardrail = InputGuardrail()
        output_guardrail = OutputGuardrail()
        logger.info(f"  ✅ Input Guardrail: {len(input_guardrail.ADVISORY_PATTERNS)} patterns")
        logger.info(f"  ✅ Output Guardrail: Max {output_guardrail.MAX_SENTENCES} sentences")

        # Step 5: Initialize Session Manager
        logger.info("\n[5/5] Initializing Session Manager (Phase 5.4)...")
        session_manager = SessionManager()
        logger.info(f"  ✅ Max Threads: {session_manager.MAX_THREADS_PER_SESSION}")
        logger.info(f"  ✅ Max Messages/Thread: {session_manager.MAX_MESSAGES_PER_THREAD}")

        logger.info("\n" + "="*70)
        logger.info("✅ Phase 7 Initialization Complete!")
        logger.info("="*70)

        return pipeline, session_manager

    except Exception as e:
        logger.error(f"\n❌ Phase 7 initialization failed: {e}", exc_info=True)
        raise


def run_interactive_test(pipeline):
    """Run interactive query testing."""
    print("\n" + "="*70)
    print("🎯 Phase 7: Interactive Query Testing")
    print("="*70)
    print("\nType your questions (or 'quit' to exit)")
    print("Examples:")
    print("  - What is the NAV of HDFC Mid Cap Fund?")
    print("  - What is the minimum SIP amount?")
    print("  - What is the expense ratio?")
    print("  - Should I invest in HDFC Equity Fund? (advisory - will be blocked)")
    print("="*70 + "\n")

    while True:
        try:
            query = input("❓ You: ").strip()
            
            if not query:
                continue
            if query.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break

            print("\n⏳ Processing...\n")
            
            # Execute query
            result = pipeline.query(query)

            # Display result
            if result.is_refusal:
                print("🚫 REFUSAL RESPONSE:")
                print(f"   {result.response}")
            else:
                print("✅ RESPONSE:")
                print(f"   {result.response}")
                print(f"\n📊 Metadata:")
                print(f"   • Confidence: {result.confidence_score:.3f}")
                print(f"   • Chunks Used: {result.chunks_used}")
                print(f"   • Processing Time: {result.processing_time_ms:.0f}ms")
                
                if result.source_url:
                    print(f"   • Source: {result.source_url}")
                if result.last_updated:
                    print(f"   • Last Updated: {result.last_updated}")

            print("\n" + "-"*70 + "\n")

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            logger.error(f"Query error: {e}", exc_info=True)


def run_demo_queries(pipeline):
    """Run predefined demo queries to showcase Phase 7 capabilities."""
    demo_queries = [
        {
            "query": "What is the NAV of HDFC Mid Cap Fund?",
            "description": "Factual query - should return NAV data"
        },
        {
            "query": "What is the minimum SIP amount?",
            "description": "Factual query - should return SIP minimum"
        },
        {
            "query": "What is the expense ratio?",
            "description": "Factual query - should return expense ratio"
        },
        {
            "query": "What is the fund size?",
            "description": "Factual query - should return AUM"
        },
        {
            "query": "Should I invest in HDFC Equity Fund?",
            "description": "Advisory query - should be BLOCKED by guardrail"
        },
        {
            "query": "Which fund is better, HDFC or Axis?",
            "description": "Comparison query - should be BLOCKED by guardrail"
        },
    ]

    print("\n" + "="*70)
    print("🎬 Phase 7: Demo Queries")
    print("="*70)

    for i, demo in enumerate(demo_queries, 1):
        print(f"\n{'='*70}")
        print(f"Demo {i}/{len(demo_queries)}")
        print(f"Query: {demo['query']}")
        print(f"Expected: {demo['description']}")
        print(f"{'='*70}")

        result = pipeline.query(demo['query'])

        if result.is_refusal:
            print(f"\n🚫 REFUSAL (confidence: {result.confidence_score:.3f})")
        else:
            print(f"\n✅ RESPONSE (confidence: {result.confidence_score:.3f})")
            print(f"\n{result.response}")

        print(f"\n⏱️  Processing Time: {result.processing_time_ms:.0f}ms")
        if result.source_url:
            print(f"📎 Source: {result.source_url}")
        if result.last_updated:
            print(f"📅 Last Updated: {result.last_updated}")

        print()


def main():
    """CLI entry point for Phase 7."""
    parser = argparse.ArgumentParser(
        description="Phase 7: Retrieval & Generation Flow (Complete RAG Pipeline)"
    )
    parser.add_argument(
        "--mode",
        choices=["test", "serve", "init", "demo", "interactive"],
        default="test",
        help="Mode: test (run queries), serve (start Flask), init (initialize), demo (run demos), interactive (chat)"
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Single query to test"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    try:
        # Initialize Phase 7
        pipeline, session_manager = initialize_phase7()

        if args.mode == "init":
            print("\n✅ Phase 7 initialized successfully!")
            print("\nComponents ready:")
            print("  • Embedding Service (HuggingFace BGE)")
            print("  • Retriever (Chroma Cloud)")
            print("  • RAG Pipeline (Groq LLM)")
            print("  • Guardrails (Input/Output)")
            print("  • Session Manager (Threads)")
            return

        elif args.mode == "test":
            if args.query:
                # Single query test
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
                # Run demo queries
                run_demo_queries(pipeline)

        elif args.mode == "demo":
            run_demo_queries(pipeline)

        elif args.mode == "interactive":
            run_interactive_test(pipeline)

        elif args.mode == "serve":
            print("\n🚀 Starting Flask server with Phase 7...")
            print("\nRun: python app.py (from backend directory)")
            print("\nPhase 7 is integrated into the Flask app via Phase 5 components.")
            print("The app.py has been updated to use the Phase 5/7 pipeline.\n")

    except Exception as e:
        logger.error(f"Phase 7 failed: {e}", exc_info=True)
        print(f"\n❌ Phase 7 execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
