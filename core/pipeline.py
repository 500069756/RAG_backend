"""
RAG Pipeline — Phase 7
Orchestrates the full query pipeline: Guardrail → Embed → Retrieve → Generate → Validate.

This is the single entry point for processing user queries.
"""

import logging
import time
import uuid
from datetime import datetime, timezone

from core.guardrails import InputGuardrail, OutputGuardrail
from core.retriever import Retriever
from core.generator import Generator

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    End-to-end RAG orchestrator.

    Flow:
        1. Input Guardrail  → classify query (FACTUAL / ADVISORY / PII)
        2. Query Embedding  → embed via HuggingFace (same model as index)
        3. Vector Retrieval → Chroma Cloud similarity search
        4. Context Assembly → merge top chunks into prompt
        5. LLM Generation   → Groq API (Llama 3.3 70B/8B)
        6. Output Guardrail → validate response
    """

    def __init__(self, retriever: Retriever, generator: Generator):
        self.retriever = retriever
        self.generator = generator
        self.input_guardrail = InputGuardrail()
        self.output_guardrail = OutputGuardrail()
        logger.info("RAGPipeline initialized")

    def process_query(
        self,
        query: str,
        thread_id: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """
        Process a user query through the full RAG pipeline.

        Args:
            query: User's question text
            thread_id: Optional thread ID for multi-thread context
            conversation_history: Previous messages in the thread

        Returns:
            {
                "thread_id": str,
                "response": str,
                "source_url": str,
                "last_updated": str,
                "is_refusal": bool,
                "confidence_score": float,
                "model_used": str,
                "latency_ms": int
            }
        """
        start_time = time.time()
        request_id = str(uuid.uuid4())[:8]
        thread_id = thread_id or str(uuid.uuid4())

        logger.info(f"[{request_id}] Processing query: \"{query[:80]}...\"")

        # ── Step 1: Input Guardrail ──────────────────────────
        classification, refusal_message = self.input_guardrail.classify(query)

        if classification != "FACTUAL":
            latency = int((time.time() - start_time) * 1000)
            logger.info(f"[{request_id}] Blocked ({classification}) in {latency}ms")
            return {
                "thread_id": thread_id,
                "response": refusal_message,
                "source_url": self.input_guardrail.REFUSAL_SOURCE_URL,
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "is_refusal": True,
                "confidence_score": 1.0,
                "model_used": "guardrail",
                "latency_ms": latency,
            }

        # ── Step 2 & 3: Retrieve (embedding happens inside retriever) ─
        try:
            chunks = self.retriever.retrieve(query)
        except Exception as e:
            logger.error(f"[{request_id}] Retrieval failed: {e}")
            latency = int((time.time() - start_time) * 1000)
            return {
                "thread_id": thread_id,
                "response": "I'm sorry, I'm unable to search the knowledge base right now. Please try again shortly.",
                "source_url": "",
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "is_refusal": False,
                "confidence_score": 0.0,
                "model_used": "error",
                "latency_ms": latency,
            }

        # Handle no results
        if not chunks:
            latency = int((time.time() - start_time) * 1000)
            logger.info(f"[{request_id}] No relevant chunks found")
            return {
                "thread_id": thread_id,
                "response": "I don't have enough information in my knowledge base to answer that question accurately. Please try rephrasing or ask about specific mutual fund scheme details.",
                "source_url": "",
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "is_refusal": False,
                "confidence_score": 0.0,
                "model_used": "none",
                "latency_ms": latency,
            }

        # Confidence = top chunk's similarity score
        confidence = chunks[0]["similarity_score"]

        # ── Step 4 & 5: Generate ─────────────────────────────
        try:
            gen_result = self.generator.generate(
                query=query,
                retrieved_chunks=chunks,
                conversation_history=conversation_history
            )
        except RuntimeError as e:
            logger.error(f"[{request_id}] Generation failed: {e}")
            latency = int((time.time() - start_time) * 1000)
            return {
                "thread_id": thread_id,
                "response": "I'm sorry, I'm temporarily unable to generate a response. Please try again in a moment.",
                "source_url": chunks[0].get("source_url", "") if chunks else "",
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "is_refusal": False,
                "confidence_score": confidence,
                "model_used": "error",
                "latency_ms": latency,
            }

        # ── Step 6: Output Guardrail ─────────────────────────
        validated_response = self.output_guardrail.validate(
            response=gen_result["response"],
            source_url=gen_result["source_url"],
            scraped_at=gen_result["scraped_at"]
        )

        latency = int((time.time() - start_time) * 1000)
        logger.info(f"[{request_id}] Response generated in {latency}ms "
                    f"(model={gen_result['model_used']}, "
                    f"confidence={confidence:.3f})")

        return {
            "thread_id": thread_id,
            "response": validated_response,
            "source_url": gen_result["source_url"],
            "last_updated": gen_result["scraped_at"][:10] if gen_result["scraped_at"] else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "is_refusal": False,
            "confidence_score": confidence,
            "model_used": gen_result["model_used"],
            "latency_ms": latency,
        }
