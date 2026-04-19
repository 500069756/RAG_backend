"""
Guardrails Service — Phase 5.1
Input and output validation for compliance and safety.

Responsibilities:
    - Input Guardrail: Classify queries (factual vs advisory vs PII)
    - Output Guardrail: Validate LLM responses (length, citations, tone)
    - Refusal handling: Generate polite refusal messages
    - PII detection and masking
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GuardrailResult:
    """Result from guardrail classification."""
    classification: str  # "FACTUAL", "ADVISORY", "PII_DETECTED"
    is_safe: bool
    message: Optional[str] = None  # Refusal message if unsafe


class InputGuardrail:
    """
    Classifies user input before retrieval.
    Ensures queries are factual and contain no PII.
    """

    # Advisory patterns (investment advice, recommendations)
    ADVISORY_PATTERNS = [
        r"should I (invest|buy|sell|redeem|hold)",
        r"which (fund|scheme) is better",
        r"which (fund|scheme) should I",
        r"recommend.* (fund|scheme|investment)",
        r"best (fund|scheme|investment|option)",
        r"will .* (go up|grow|increase|fall|drop|rise)",
        r"compare .* (returns|performance)",
        r"how much (return|profit|loss) will",
        r"is .* (good|safe|better|best) to invest",
        r"where should I invest",
        r"what should I buy",
    ]

    # PII patterns (personal identifiable information)
    PII_PATTERNS = [
        (r"\b[A-Z]{5}\d{4}[A-Z]\b", "PAN card number"),
        (r"\b\d{4}\s?\d{4}\s?\d{4}\b", "Aadhaar number"),
        (r"\b\d{9,18}\b", "Account number"),
        (r"\b\d{6}\b", "OTP"),
        (r"\b[\w.-]+@[\w.-]+\.\w+\b", "Email address"),
        (r"\b(\+91|91|0)?[6-9]\d{9}\b", "Phone number"),
    ]

    def __init__(self):
        # Compile regex patterns for performance
        self.advisory_regex = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.ADVISORY_PATTERNS
        ]
        self.pii_regex = [
            (re.compile(pattern, re.IGNORECASE), name)
            for pattern, name in self.PII_PATTERNS
        ]

    def classify(self, query: str) -> GuardrailResult:
        """
        Classify user query and determine if it's safe to process.

        Args:
            query: User's question

        Returns:
            GuardrailResult with classification and safety status
        """
        # Check PII first (highest priority)
        pii_type = self._check_pii(query)
        if pii_type:
            logger.warning(f"PII detected in query: {pii_type}")
            return GuardrailResult(
                classification="PII_DETECTED",
                is_safe=False,
                message=(
                    "I cannot process personal information. "
                    "Please remove sensitive details like PAN, Aadhaar, "
                    "phone numbers, or email addresses and try again."
                )
            )

        # Check for advisory requests
        if self._check_advisory(query):
            logger.info(f"Advisory query detected: {query[:60]}...")
            return GuardrailResult(
                classification="ADVISORY",
                is_safe=False,
                message=(
                    "I can only answer factual questions about mutual fund schemes, "
                    "such as NAV, expense ratio, fund size, or minimum investment. "
                    "I cannot provide investment advice or recommendations. "
                    "Please consult a SEBI-registered financial advisor for personalized guidance."
                )
            )

        # Query is factual and safe
        logger.debug(f"Factual query approved: {query[:60]}...")
        return GuardrailResult(
            classification="FACTUAL",
            is_safe=True
        )

    def _check_pii(self, query: str) -> Optional[str]:
        """Check if query contains PII. Returns PII type if found."""
        for pattern, pii_type in self.pii_regex:
            if pattern.search(query):
                return pii_type
        return None

    def _check_advisory(self, query: str) -> bool:
        """Check if query is asking for advice."""
        return any(pattern.search(query) for pattern in self.advisory_regex)


class OutputGuardrail:
    """
    Validates LLM responses before returning to user.
    Ensures compliance with response guidelines.
    """

    MAX_SENTENCES = 3
    REQUIRED_FOOTER_PATTERN = r"Last updated from sources:"

    def __init__(self):
        # Sentence boundary pattern
        self.sentence_pattern = re.compile(r'[.!?]+\s+')

    def validate(
        self,
        response: str,
        source_url: Optional[str] = None,
        scraped_date: Optional[str] = None
    ) -> dict:
        """
        Validate and fix LLM response.

        Args:
            response: Raw LLM response
            source_url: Source citation URL
            scraped_date: Date when source was last scraped

        Returns:
            Dict with validated response and metadata
        """
        issues = []

        # Check 1: Truncate to max 3 sentences
        if self._count_sentences(response) > self.MAX_SENTENCES:
            response = self._truncate_sentences(response, self.MAX_SENTENCES)
            issues.append("truncated_to_3_sentences")

        # Check 2: Ensure citation URL is present
        if source_url and source_url not in response:
            # Append source URL if not already in response
            if not response.endswith('.'):
                response += '.'
            response += f" Source: {source_url}"
            issues.append("added_citation")

        # Check 3: Append "Last updated" footer if missing
        if scraped_date and self.REQUIRED_FOOTER_PATTERN not in response:
            response += f"\n\nLast updated from sources: {scraped_date}"
            issues.append("added_footer")

        # Check 4: Remove advisory language if present
        advisory_words = ["recommend", "suggest", "should invest", "best option"]
        for word in advisory_words:
            if word.lower() in response.lower():
                response = re.sub(re.escape(word), "[removed]", response, flags=re.IGNORECASE)
                issues.append(f"removed_advisory_word:{word}")

        # Check 5: Verify no PII in response
        input_guardrail = InputGuardrail()
        if input_guardrail._check_pii(response):
            response = self._mask_pii(response)
            issues.append("masked_pii_in_response")

        is_valid = len(issues) == 0
        logger.info(
            f"Output guardrail: {'PASS' if is_valid else 'FIXED'} "
            f"(issues: {', '.join(issues) if issues else 'none'})"
        )

        return {
            "response": response.strip(),
            "is_valid": is_valid,
            "issues_fixed": issues,
            "sentence_count": self._count_sentences(response),
        }

    def _count_sentences(self, text: str) -> int:
        """Count sentences in text."""
        if not text.strip():
            return 0
        sentences = self.sentence_pattern.split(text.strip())
        return len([s for s in sentences if s.strip()])

    def _truncate_sentences(self, text: str, max_sentences: int) -> str:
        """Truncate text to specified number of sentences."""
        sentences = self.sentence_pattern.split(text.strip())
        valid_sentences = [s for s in sentences if s.strip()]

        if len(valid_sentences) <= max_sentences:
            return text

        # Take first N sentences
        truncated = '. '.join(valid_sentences[:max_sentences])
        if not truncated.endswith('.'):
            truncated += '.'
        return truncated

    def _mask_pii(self, text: str) -> str:
        """Mask PII in text."""
        input_guardrail = InputGuardrail()
        for pattern, pii_type in input_guardrail.pii_regex:
            text = pattern.sub(f"[{pii_type} REDACTED]", text)
        return text


# Convenience functions for quick validation
def validate_input(query: str) -> GuardrailResult:
    """Validate user input query."""
    guardrail = InputGuardrail()
    return guardrail.classify(query)


def validate_output(
    response: str,
    source_url: Optional[str] = None,
    scraped_date: Optional[str] = None
) -> dict:
    """Validate LLM output response."""
    guardrail = OutputGuardrail()
    return guardrail.validate(response, source_url, scraped_date)
