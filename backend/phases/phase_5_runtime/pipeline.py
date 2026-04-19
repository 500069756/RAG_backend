"""
RAG Pipeline Orchestrator — Phase 5.2
Ties together all components: guardrails → embedding → retrieval → generation → validation.

Responsibilities:
    - Orchestrate complete query pipeline
    - Handle errors and fallbacks
    - Manage context assembly
    - Integrate with Groq API for generation
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
    """
    Orchestrates the complete RAG query pipeline.
    
    Flow:
        1. Input Guardrail (validate query)
        2. Query Embedding (HuggingFace API)
        3. Vector Retrieval (Chroma Cloud)
        4. Context Assembly (merge chunks)
        5. LLM Generation (Groq API)
        6. Output Guardrail (validate response)
    """

    # Groq model configuration
    PRIMARY_MODEL = "llama-3.3-70b-versatile"
    FALLBACK_MODEL = "llama-3.3-8b-instant"
    TEMPERATURE = 0.1  # Deterministic responses
    MAX_TOKENS = 300
    TOP_P = 0.9

    # Retrieval configuration
    TOP_K = 5
    SIMILARITY_THRESHOLD = 0.65

    def __init__(
        self,
        embedding_service,
        retriever,
        groq_api_key: Optional[str] = None,
    ):
        """
        Args:
            embedding_service: EmbeddingService instance
            retriever: Retriever instance
            groq_api_key: Groq API key
        """
        self.embedding_service = embedding_service
        self.retriever = retriever
        self.groq_client = Groq(api_key=groq_api_key or os.environ["GROQ_API_KEY"])
        
        # Initialize guardrails
        self.input_guardrail = InputGuardrail()
        self.output_guardrail = OutputGuardrail()

        logger.info(f"RAG Pipeline initialized (model: {self.PRIMARY_MODEL})")

    def query(
        self,
        user_query: str,
        scheme_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
    ) -> QueryResult:
        """
        Execute complete RAG pipeline for a user query.

        Args:
            user_query: User's question
            scheme_filter: Optional scheme name filter
            category_filter: Optional category filter

        Returns:
            QueryResult with response and metadata
        """
        start_time = time.time()
        logger.info(f"Processing query: \"{user_query[:80]}...\"")

        try:
            # Step 1: Input Guardrail
            guardrail_result = self.input_guardrail.classify(user_query)
            if not guardrail_result.is_safe:
                logger.info(f"Query blocked by guardrail: {guardrail_result.classification}")
                return QueryResult(
                    response=guardrail_result.message,
                    source_url="",
                    last_updated="",
                    is_refusal=True,
                    processing_time_ms=(time.time() - start_time) * 1000
                )

            # Step 2 & 3: Retrieval (embedding + search)
            logger.info("Step 2-3: Retrieving relevant chunks...")
            chunks = self.retriever.retrieve(
                query=user_query,
                scheme_filter=scheme_filter,
                category_filter=category_filter,
                top_k=self.TOP_K
            )

            if not chunks:
                logger.warning("No relevant chunks found")
                return QueryResult(
                    response=(
                        "I don't have enough information to answer this question based on "
                        "official mutual fund sources. Please try rephrasing your question "
                        "or ask about a specific fund scheme."
                    ),
                    source_url="",
                    last_updated="",
                    is_refusal=True,
                    confidence_score=0.0,
                    processing_time_ms=(time.time() - start_time) * 1000
                )

            # Step 4: Context Assembly
            logger.info(f"Step 4: Assembling context from {len(chunks)} chunks...")
            context, source_urls, scraped_date = self._assemble_context(chunks)

            # Step 5: LLM Generation
            logger.info("Step 5: Generating response with Groq...")
            raw_response = self._generate_response(
                user_query=user_query,
                context=context,
                source_urls=source_urls
            )

            # Step 6: Output Guardrail
            logger.info("Step 6: Validating output...")
            validation = self.output_guardrail.validate(
                response=raw_response,
                source_url=source_urls[0] if source_urls else "",
                scraped_date=scraped_date
            )

            # Calculate confidence (based on top chunk similarity)
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
                guardrail_issues=validation["issues_fixed"]
            )

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            logger.error(f"Pipeline error: {e}", exc_info=True)
            return QueryResult(
                response=(
                    "I'm experiencing technical difficulties. Please try again in a moment."
                ),
                source_url="",
                last_updated="",
                is_refusal=True,
                processing_time_ms=processing_time
            )

    def _assemble_context(self, chunks: list[dict]) -> tuple[str, list[str], str]:
        """
        Merge retrieved chunks into prompt context.

        Args:
            chunks: List of retrieved chunk dicts

        Returns:
            Tuple of (context_text, source_urls, latest_scraped_date)
        """
        context_parts = []
        source_urls = []
        scraped_dates = []

        for i, chunk in enumerate(chunks, 1):
            # Add chunk with metadata
            context_parts.append(
                f"[Chunk {i}] (Source: {chunk['source_url']})\n"
                f"{chunk['text']}\n"
            )
            source_urls.append(chunk["source_url"])
            if chunk.get("scraped_at"):
                scraped_dates.append(chunk["scraped_at"])

        # Deduplicate URLs
        source_urls = list(dict.fromkeys(source_urls))

        # Get latest scraped date
        latest_date = sorted(scraped_dates)[-1][:10] if scraped_dates else ""

        context = "\n".join(context_parts)
        logger.debug(f"Context assembled: {len(context)} chars, {len(source_urls)} sources")

        return context, source_urls, latest_date

    def _generate_response(
        self,
        user_query: str,
        context: str,
        source_urls: list[str],
        model: Optional[str] = None,
    ) -> str:
        """
        Generate response using Groq API.

        Args:
            user_query: User's question
            context: Assembled context from chunks
            source_urls: List of source URLs
            model: Groq model to use (default: PRIMARY_MODEL)

        Returns:
            Generated response text
        """
        model = model or self.PRIMARY_MODEL
        system_prompt = self._build_system_prompt(context, source_urls)

        try:
            response = self.groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=self.TEMPERATURE,
                max_tokens=self.MAX_TOKENS,
                top_p=self.TOP_P,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            # Fallback to smaller model if primary fails
            if model == self.PRIMARY_MODEL:
                logger.warning(f"Primary model failed, trying fallback: {e}")
                return self._generate_response(
                    user_query, context, source_urls,
                    model=self.FALLBACK_MODEL
                )
            raise

    def _build_system_prompt(self, context: str, source_urls: list[str]) -> str:
        """
        Build system prompt for LLM.

        Args:
            context: Retrieved context
            source_urls: Source URLs for citation

        Returns:
            Formatted system prompt
        """
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
