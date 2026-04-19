"""
RAG Pipeline Orchestrator — Simplified
Ties together: guardrails → retrieval (FAISS) → generation (Groq) → validation.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from groq import Groq

from phases.phase_5_runtime.guardrails import InputGuardrail, OutputGuardrail

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Complete result from RAG pipeline."""
    response: str
    source_url: str
    last_updated: str
    is_refusal: bool = False
    confidence_score: float = 0.0
    chunks_used: int = 0
    processing_time_ms: float = 0.0
    guardrail_issues: list = field(default_factory=list)


class RAGPipeline:
    """Orchestrates the RAG query pipeline using local FAISS index + Groq LLM."""

    PRIMARY_MODEL = "llama-3.3-70b-versatile"
    FALLBACK_MODEL = "llama-3.3-8b-instant"
    TEMPERATURE = 0.1
    MAX_TOKENS = 300
    TOP_P = 0.9
    TOP_K = 5

    def __init__(self, retriever, groq_api_key: Optional[str] = None):
        self.retriever = retriever
        self.groq_client = Groq(api_key=groq_api_key or os.environ["GROQ_API_KEY"])
        self.input_guardrail = InputGuardrail()
        self.output_guardrail = OutputGuardrail()
        logger.info(f"RAG Pipeline initialized (model: {self.PRIMARY_MODEL})")

    def query(
        self,
        user_query: str,
        scheme_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
    ) -> QueryResult:
        start_time = time.time()
        logger.info(f"Processing query: \"{user_query[:80]}\"")

        try:
            # Step 1: Input Guardrail
            guardrail_result = self.input_guardrail.classify(user_query)
            if not guardrail_result.is_safe:
                return QueryResult(
                    response=guardrail_result.message,
                    source_url="",
                    last_updated="",
                    is_refusal=True,
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

            # Step 2: Retrieval (FAISS)
            chunks = self.retriever.retrieve(
                query=user_query,
                scheme_filter=scheme_filter,
                category_filter=category_filter,
                top_k=self.TOP_K,
            )

            if not chunks:
                return QueryResult(
                    response=(
                        "I don't have enough information to answer this question "
                        "based on official mutual fund sources. Please try rephrasing "
                        "your question or ask about a specific fund scheme."
                    ),
                    source_url="",
                    last_updated="",
                    is_refusal=True,
                    confidence_score=0.0,
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

            # Step 3: Context Assembly
            context, source_urls, scraped_date = self._assemble_context(chunks)

            # Step 4: LLM Generation (Groq)
            raw_response = self._generate_response(user_query, context, source_urls)

            # Step 5: Output Guardrail
            validation = self.output_guardrail.validate(
                response=raw_response,
                source_url=source_urls[0] if source_urls else "",
                scraped_date=scraped_date,
            )

            confidence = chunks[0]["similarity_score"] if chunks else 0.0
            processing_time = (time.time() - start_time) * 1000

            logger.info(
                f"Query completed in {processing_time:.0f}ms "
                f"(confidence: {confidence:.3f}, chunks: {len(chunks)})"
            )

            return QueryResult(
                response=validation["response"],
                source_url=source_urls[0] if source_urls else "",
                last_updated=scraped_date or "",
                is_refusal=False,
                confidence_score=confidence,
                chunks_used=len(chunks),
                processing_time_ms=processing_time,
                guardrail_issues=validation["issues_fixed"],
            )

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            logger.error(f"Pipeline error: {e}", exc_info=True)
            return QueryResult(
                response="I'm experiencing technical difficulties. Please try again in a moment.",
                source_url="",
                last_updated="",
                is_refusal=True,
                processing_time_ms=processing_time,
            )

    def _assemble_context(self, chunks: list[dict]) -> tuple[str, list[str], str]:
        context_parts = []
        source_urls = []
        scraped_dates = []

        for i, chunk in enumerate(chunks, 1):
            context_parts.append(
                f"[Chunk {i}] (Source: {chunk['source_url']})\n{chunk['text']}\n"
            )
            source_urls.append(chunk["source_url"])
            if chunk.get("scraped_at"):
                scraped_dates.append(chunk["scraped_at"])

        source_urls = list(dict.fromkeys(source_urls))
        latest_date = sorted(scraped_dates)[-1][:10] if scraped_dates else ""
        return "\n".join(context_parts), source_urls, latest_date

    def _generate_response(
        self,
        user_query: str,
        context: str,
        source_urls: list[str],
        model: Optional[str] = None,
    ) -> str:
        model = model or self.PRIMARY_MODEL
        system_prompt = self._build_system_prompt(context, source_urls)

        try:
            response = self.groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query},
                ],
                temperature=self.TEMPERATURE,
                max_tokens=self.MAX_TOKENS,
                top_p=self.TOP_P,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            if model == self.PRIMARY_MODEL:
                logger.warning(f"Primary model failed, trying fallback: {e}")
                return self._generate_response(
                    user_query, context, source_urls, model=self.FALLBACK_MODEL
                )
            raise

    def _build_system_prompt(self, context: str, source_urls: list[str]) -> str:
        urls_text = "\n".join(f"- {url}" for url in source_urls)
        return f"""You are a facts-only Mutual Fund FAQ assistant. Follow these rules STRICTLY:

1. Answer ONLY factual, verifiable questions about mutual fund schemes.
2. Use ONLY the provided context to answer. Do NOT use external knowledge.
3. Keep responses to a MAXIMUM of 3 sentences.
4. Include EXACTLY ONE source citation URL from the context.
5. End every response with: "Last updated from sources: {{date}}" where {{date}} is from the context.
6. NEVER provide investment advice, opinions, performance comparisons, or recommendations.
7. If the question asks for advice or comparison, respond with a polite refusal.
8. NEVER ask for or acknowledge PII (PAN, Aadhaar, account numbers, email, phone, OTP).

CONTEXT:
{context}

SOURCE URLS:
{urls_text}

USER QUESTION:
{{user_query}}"""
