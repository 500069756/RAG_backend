"""
Guardrails — Phase 8
Input and output compliance layer for the Mutual Fund FAQ Assistant.

Responsibilities:
    - Pre-retrieval: Classify queries as FACTUAL / ADVISORY / PII_DETECTED
    - Post-generation: Validate response (sentence count, citations, PII leak)
    - Refusal response generation for advisory/PII queries
"""

import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class InputGuardrail:
    """Classifies user input before retrieval to enforce facts-only policy."""

    ADVISORY_PATTERNS = [
        r"should I (invest|buy|sell|redeem|switch|hold)",
        r"which (fund|scheme|plan) is better",
        r"recommend",
        r"suggest",
        r"best (fund|scheme|investment|option|choice)",
        r"will .* (go up|grow|increase|fall|crash|drop)",
        r"compare .* (returns|performance|nav|growth)",
        r"how much (return|profit|loss|gain)",
        r"is it (safe|risky|good|bad) to invest",
        r"where should I (put|park|invest) my money",
        r"what should I do with",
        r"(buy|sell|redeem) (this|the|my)",
        r"good time to (invest|buy|sell)",
    ]

    PII_PATTERNS = [
        r"\b[A-Z]{5}\d{4}[A-Z]\b",           # PAN (e.g., ABCDE1234F)
        r"\b\d{4}\s?\d{4}\s?\d{4}\b",         # Aadhaar (12 digits)
        r"\b\d{9,18}\b",                       # Bank account numbers
        r"\b\d{6}\b",                          # OTP (6 digits)
        r"\b[\w.-]+@[\w.-]+\.\w+\b",           # Email
        r"\b(\+91|91|0)?[6-9]\d{9}\b",         # Indian phone
    ]

    REFUSAL_ADVISORY = (
        "I appreciate your question, but I can only provide factual information "
        "about mutual fund schemes such as expense ratios, exit loads, and fund "
        "details. For investment guidance, please consult a SEBI-registered "
        "financial advisor."
    )

    REFUSAL_PII = (
        "I cannot process personal information such as PAN numbers, Aadhaar, "
        "phone numbers, or email addresses. Please ask factual questions about "
        "mutual fund schemes without including any personal data."
    )

    REFUSAL_SOURCE_URL = "https://www.amfiindia.com/investor-corner/knowledge-center.html"

    def classify(self, query: str) -> tuple[str, str | None]:
        """
        Classify user query.

        Returns:
            (classification, refusal_message)
            classification: "FACTUAL" | "ADVISORY" | "PII_DETECTED"
            refusal_message: None if factual, otherwise the refusal text
        """
        # Check PII first (highest priority)
        if self._matches_pii(query):
            logger.warning(f"PII detected in query: {query[:50]}...")
            return "PII_DETECTED", self.REFUSAL_PII

        # Check advisory patterns
        if self._matches_advisory(query):
            logger.info(f"Advisory query detected: {query[:50]}...")
            return "ADVISORY", self.REFUSAL_ADVISORY

        return "FACTUAL", None

    def _matches_pii(self, query: str) -> bool:
        """Check if query contains PII patterns."""
        for pattern in self.PII_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return True
        return False

    def _matches_advisory(self, query: str) -> bool:
        """Check if query asks for investment advice."""
        query_lower = query.lower()
        for pattern in self.ADVISORY_PATTERNS:
            if re.search(pattern, query_lower):
                return True
        return False


class OutputGuardrail:
    """Validates LLM-generated responses before returning to the user."""

    MAX_SENTENCES = 3

    ADVISORY_LEAK_PATTERNS = [
        r"I (recommend|suggest|advise)",
        r"you should (invest|buy|sell|redeem)",
        r"(good|great|excellent) investment",
        r"guaranteed returns",
        r"risk-free",
    ]

    PII_PATTERNS = InputGuardrail.PII_PATTERNS  # Reuse input PII patterns

    def validate(
        self,
        response: str,
        source_url: str | None = None,
        scraped_at: str | None = None
    ) -> str:
        """
        Apply all output guardrails to the LLM response.

        Args:
            response: Raw LLM response text
            source_url: Citation URL from retrieved chunks
            scraped_at: ISO timestamp of last scrape

        Returns:
            Cleaned and validated response string
        """
        # Step 1: Strip advisory language leaks
        response = self._strip_advisory_leaks(response)

        # Step 2: Mask any PII in response
        response = self._mask_pii(response)

        # Step 3: Truncate to max sentences
        response = self._truncate_sentences(response)

        # Step 4: Ensure "Last updated" footer
        response = self._ensure_footer(response, scraped_at)

        return response

    def _truncate_sentences(self, text: str) -> str:
        """Truncate response to MAX_SENTENCES."""
        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        # Filter out the "Last updated" footer from sentence count
        content_sentences = [
            s for s in sentences
            if not s.startswith("Last updated")
        ]
        if len(content_sentences) > self.MAX_SENTENCES:
            logger.info(f"Truncating response from {len(content_sentences)} "
                        f"to {self.MAX_SENTENCES} sentences")
            return " ".join(content_sentences[:self.MAX_SENTENCES])
        return text

    def _strip_advisory_leaks(self, text: str) -> str:
        """Remove any advisory language that leaked through the LLM."""
        for pattern in self.ADVISORY_LEAK_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Advisory leak detected in response — stripping")
                text = re.sub(
                    pattern + r"[^.]*\.",
                    "",
                    text,
                    flags=re.IGNORECASE
                )
        return text.strip()

    def _mask_pii(self, text: str) -> str:
        """Mask any PII that appears in the LLM response."""
        for pattern in self.PII_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                logger.warning("PII detected in LLM response — masking")
                text = re.sub(pattern, "[REDACTED]", text)
        return text

    def _ensure_footer(self, text: str, scraped_at: str | None = None) -> str:
        """Ensure the response has the 'Last updated' footer."""
        if "Last updated" in text:
            return text

        if scraped_at:
            try:
                dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                date_str = scraped_at[:10] if scraped_at else "N/A"
        else:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return f"{text}\n\nLast updated from sources: {date_str}"
