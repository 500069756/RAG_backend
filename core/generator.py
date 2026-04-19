"""
Generator — Phase 7.3
Groq LLM integration for generating factual responses.

Responsibilities:
    - Build system prompt with retrieved context and constraints
    - Call Groq API (Llama 3.3 70B primary / 8B fallback)
    - Handle rate limits and errors with model fallback
"""

import logging
import os

from groq import Groq

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_TEMPLATE = """You are a facts-only Mutual Fund FAQ assistant. Follow these rules STRICTLY:

1. Answer ONLY factual, verifiable questions about mutual fund schemes.
2. Use ONLY the provided context to answer. Do NOT use external knowledge.
3. Keep responses to a MAXIMUM of 3 sentences.
4. Include EXACTLY ONE source citation URL from the context.
5. End every response with: "Last updated from sources: {last_scraped_date}"
6. NEVER provide investment advice, opinions, performance comparisons, or recommendations.
7. If the question asks for advice or comparison, respond with a polite refusal.
8. NEVER ask for or acknowledge PII (PAN, Aadhaar, account numbers, email, phone, OTP).
9. If the context does not contain enough information to answer, say so honestly.

CONTEXT:
{retrieved_chunks}

SOURCE URLS:
{source_urls}
"""


class Generator:
    """Generates LLM responses using Groq API with Llama 3.3."""

    PRIMARY_MODEL = "llama-3.3-70b-versatile"
    FALLBACK_MODEL = "llama-3.3-8b-instant"
    TEMPERATURE = 0.1
    MAX_TOKENS = 300
    TOP_P = 0.9

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY is required. Set it as an environment variable."
            )
        self.client = Groq(api_key=self.api_key)
        logger.info("Generator initialized (Groq API)")

    def generate(
        self,
        query: str,
        retrieved_chunks: list[dict],
        conversation_history: list[dict] | None = None
    ) -> dict:
        """
        Generate a response using Groq LLM with retrieved context.

        Args:
            query: User's question
            retrieved_chunks: List of chunk dicts from Retriever
            conversation_history: Optional previous messages for context

        Returns:
            {
                "response": str,
                "source_url": str,
                "scraped_at": str,
                "model_used": str,
                "is_fallback": bool
            }
        """
        # Build system prompt
        system_prompt = self._build_system_prompt(retrieved_chunks)

        # Build messages array
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 5 messages for follow-ups)
        if conversation_history:
            recent = conversation_history[-5:]
            for msg in recent:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        # Add current query
        messages.append({"role": "user", "content": query})

        # Try primary model, fallback on failure
        response_text, model_used, is_fallback = self._call_with_fallback(messages)

        # Extract best source URL and scraped_at
        source_url = ""
        scraped_at = ""
        if retrieved_chunks:
            source_url = retrieved_chunks[0].get("source_url", "")
            scraped_at = retrieved_chunks[0].get("scraped_at", "")

        return {
            "response": response_text,
            "source_url": source_url,
            "scraped_at": scraped_at,
            "model_used": model_used,
            "is_fallback": is_fallback,
        }

    def _build_system_prompt(self, chunks: list[dict]) -> str:
        """Assemble system prompt with retrieved context."""
        # Format chunks as numbered context blocks
        chunk_texts = []
        source_urls = set()
        last_scraped = ""

        for i, chunk in enumerate(chunks, 1):
            scheme = chunk.get("scheme_name", "")
            doc_type = chunk.get("document_type", "")
            text = chunk.get("text", "")
            url = chunk.get("source_url", "")

            chunk_texts.append(
                f"[{i}] [{scheme} - {doc_type}]\n{text}"
            )
            if url:
                source_urls.add(url)
            scraped = chunk.get("scraped_at", "")
            if scraped > last_scraped:
                last_scraped = scraped

        # Format date
        if last_scraped:
            date_str = last_scraped[:10]
        else:
            from datetime import datetime, timezone
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return SYSTEM_PROMPT_TEMPLATE.format(
            retrieved_chunks="\n\n".join(chunk_texts) if chunk_texts else "(No context available)",
            source_urls="\n".join(source_urls) if source_urls else "(No sources)",
            last_scraped_date=date_str
        )

    def _call_with_fallback(
        self,
        messages: list[dict]
    ) -> tuple[str, str, bool]:
        """
        Call Groq API with primary model, fallback to 8B on failure.

        Returns:
            (response_text, model_used, is_fallback)
        """
        # Try primary model (70B)
        try:
            response = self.client.chat.completions.create(
                model=self.PRIMARY_MODEL,
                messages=messages,
                temperature=self.TEMPERATURE,
                max_tokens=self.MAX_TOKENS,
                top_p=self.TOP_P,
            )
            text = response.choices[0].message.content
            logger.info(f"Generated response with {self.PRIMARY_MODEL} "
                        f"({len(text)} chars)")
            return text, self.PRIMARY_MODEL, False

        except Exception as e:
            logger.warning(f"Primary model ({self.PRIMARY_MODEL}) failed: {e}. "
                           f"Falling back to {self.FALLBACK_MODEL}")

        # Fallback to 8B
        try:
            response = self.client.chat.completions.create(
                model=self.FALLBACK_MODEL,
                messages=messages,
                temperature=self.TEMPERATURE,
                max_tokens=self.MAX_TOKENS,
                top_p=self.TOP_P,
            )
            text = response.choices[0].message.content
            logger.info(f"Generated response with {self.FALLBACK_MODEL} "
                        f"(fallback, {len(text)} chars)")
            return text, self.FALLBACK_MODEL, True

        except Exception as e:
            logger.error(f"Both models failed: {e}")
            raise RuntimeError(
                "Unable to generate response. Both LLM models are unavailable."
            ) from e
