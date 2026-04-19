"""
Phase 8 — Compliance Manager
Enhanced guardrails with audit logging, analytics, and compliance reporting.

Builds upon Phase 5.1 (basic guardrails) to provide:
    - Audit trail for all queries
    - PII detection and masking
    - Query analytics
    - Rate limiting
    - Compliance reporting
"""

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from phases.phase_5_runtime.guardrails import InputGuardrail, OutputGuardrail, GuardrailResult

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """Single audit log entry for compliance tracking."""
    timestamp: str
    query: str
    classification: str  # FACTUAL, ADVISORY, PII_DETECTED
    is_safe: bool
    response_provided: bool
    processing_time_ms: float
    confidence_score: float
    source_url: Optional[str] = None
    user_session: Optional[str] = None
    ip_address: Optional[str] = None


@dataclass
class QueryAnalytics:
    """Analytics summary for query patterns."""
    total_queries: int = 0
    factual_queries: int = 0
    advisory_blocked: int = 0
    pii_blocked: int = 0
    avg_confidence: float = 0.0
    avg_processing_time_ms: float = 0.0
    top_schemes: dict = field(default_factory=dict)
    hourly_distribution: dict = field(default_factory=dict)


class ComplianceManager:
    """
    Enhanced compliance manager with audit logging and analytics.
    
    Wraps Phase 5.1 guardrails and adds:
    - Audit trail
    - Analytics
    - Rate limiting
    - Compliance reporting
    """

    # Rate limiting
    MAX_QUERIES_PER_MINUTE = 30
    MAX_QUERIES_PER_HOUR = 500

    def __init__(self, audit_log_dir: str = "data/audit_logs/"):
        """
        Initialize compliance manager.
        
        Args:
            audit_log_dir: Directory to store audit logs
        """
        # Initialize Phase 5.1 guardrails
        self.input_guardrail = InputGuardrail()
        self.output_guardrail = OutputGuardrail()

        # Audit logging
        self.audit_log_dir = Path(audit_log_dir)
        self.audit_log_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log: list[AuditEntry] = []

        # Rate limiting (in-memory)
        self.query_timestamps: dict[str, list[float]] = defaultdict(list)

        # Analytics
        self.analytics = QueryAnalytics()

        logger.info("Phase 8 Compliance Manager initialized")
        logger.info(f"Audit log directory: {self.audit_log_dir}")

    def validate_query(
        self,
        query: str,
        user_session: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> dict:
        """
        Validate user query with full compliance tracking.
        
        Args:
            query: User's question
            user_session: Session ID for tracking
            ip_address: User IP for rate limiting
            
        Returns:
            Dict with validation result and metadata
        """
        start_time = time.time()

        # Check rate limit
        if not self._check_rate_limit(user_session or ip_address or "anonymous"):
            return {
                "is_safe": False,
                "classification": "RATE_LIMITED",
                "message": "Rate limit exceeded. Please try again later.",
                "retry_after": 60
            }

        # Run Phase 5.1 input guardrail
        guardrail_result = self.input_guardrail.classify(query)

        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000

        # Create audit entry
        audit_entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            query=query[:200],  # Truncate for storage
            classification=guardrail_result.classification,
            is_safe=guardrail_result.is_safe,
            response_provided=False,  # Will be updated later
            processing_time_ms=processing_time,
            confidence_score=0.0,
            user_session=user_session,
            ip_address=ip_address
        )

        # Log audit entry
        self.audit_log.append(audit_entry)
        self._update_analytics(audit_entry)

        # Log to file if unsafe
        if not guardrail_result.is_safe:
            self._log_violation(audit_entry)

        return {
            "is_safe": guardrail_result.is_safe,
            "classification": guardrail_result.classification,
            "message": guardrail_result.message,
            "processing_time_ms": processing_time
        }

    def validate_response(
        self,
        response: str,
        source_url: Optional[str] = None,
        scraped_date: Optional[str] = None
    ) -> dict:
        """
        Validate LLM response with compliance checks.
        
        Args:
            response: Raw LLM response
            source_url: Source citation URL
            scraped_date: Data freshness date
            
        Returns:
            Validated response with compliance metadata
        """
        # Run Phase 5.1 output guardrail
        validation = self.output_guardrail.validate(response, source_url, scraped_date)

        # Check for PII in response
        input_guardrail = InputGuardrail()
        pii_type = input_guardrail._check_pii(validation["response"])
        
        if pii_type:
            logger.warning(f"PII detected in LLM response: {pii_type}")
            validation["response"] = input_guardrail._mask_pii(validation["response"])
            validation["pii_masked"] = True
            validation["pii_type"] = pii_type

        return validation

    def record_response(
        self,
        query: str,
        response: str,
        confidence: float,
        source_url: str,
        processing_time_ms: float,
        user_session: Optional[str] = None
    ):
        """
        Record successful response in audit log.
        
        Args:
            query: Original user query
            response: Generated response
            confidence: Confidence score
            source_url: Source citation
            processing_time_ms: Total processing time
            user_session: Session ID
        """
        audit_entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            query=query[:200],
            classification="FACTUAL",
            is_safe=True,
            response_provided=True,
            processing_time_ms=processing_time_ms,
            confidence_score=confidence,
            source_url=source_url,
            user_session=user_session
        )

        self.audit_log.append(audit_entry)
        self._update_analytics(audit_entry)

    def _check_rate_limit(self, identifier: str) -> bool:
        """
        Check if user/session has exceeded rate limit.
        
        Args:
            identifier: User session or IP address
            
        Returns:
            True if within limits, False if rate limited
        """
        now = time.time()
        timestamps = self.query_timestamps[identifier]

        # Remove timestamps older than 1 hour
        cutoff = now - 3600
        self.query_timestamps[identifier] = [
            ts for ts in timestamps if ts > cutoff
        ]
        timestamps = self.query_timestamps[identifier]

        # Check per-minute limit
        minute_cutoff = now - 60
        recent_queries = sum(1 for ts in timestamps if ts > minute_cutoff)
        if recent_queries >= self.MAX_QUERIES_PER_MINUTE:
            logger.warning(f"Rate limit exceeded for {identifier} (per minute)")
            return False

        # Check per-hour limit
        if len(timestamps) >= self.MAX_QUERIES_PER_HOUR:
            logger.warning(f"Rate limit exceeded for {identifier} (per hour)")
            return False

        # Record this query
        timestamps.append(now)
        return True

    def _update_analytics(self, entry: AuditEntry):
        """Update query analytics with new entry."""
        self.analytics.total_queries += 1

        if entry.classification == "FACTUAL":
            self.analytics.factual_queries += 1
        elif entry.classification == "ADVISORY":
            self.analytics.advisory_blocked += 1
        elif entry.classification == "PII_DETECTED":
            self.analytics.pii_blocked += 1

        # Update averages
        total = self.analytics.total_queries
        self.analytics.avg_confidence = (
            (self.analytics.avg_confidence * (total - 1) + entry.confidence_score) / total
            if total > 0 else 0.0
        )
        self.analytics.avg_processing_time_ms = (
            (self.analytics.avg_processing_time_ms * (total - 1) + entry.processing_time_ms) / total
            if total > 0 else 0.0
        )

        # Update hourly distribution
        hour = datetime.fromisoformat(entry.timestamp).hour
        hour_key = f"{hour:02d}:00"
        self.analytics.hourly_distribution[hour_key] = (
            self.analytics.hourly_distribution.get(hour_key, 0) + 1
        )

    def _log_violation(self, entry: AuditEntry):
        """Log compliance violation to separate file."""
        violation_file = self.audit_log_dir / f"violations_{datetime.now().strftime('%Y%m%d')}.jsonl"

        violation_data = {
            "timestamp": entry.timestamp,
            "classification": entry.classification,
            "query": entry.query,
            "user_session": entry.user_session,
            "ip_address": entry.ip_address
        }

        with open(violation_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(violation_data) + "\n")

        logger.info(f"Violation logged: {entry.classification}")

    def save_audit_log(self):
        """Save audit log to disk."""
        if not self.audit_log:
            return

        log_file = self.audit_log_dir / f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        audit_data = [
            {
                "timestamp": entry.timestamp,
                "query": entry.query,
                "classification": entry.classification,
                "is_safe": entry.is_safe,
                "response_provided": entry.response_provided,
                "processing_time_ms": entry.processing_time_ms,
                "confidence_score": entry.confidence_score,
                "source_url": entry.source_url,
                "user_session": entry.user_session,
                "ip_address": entry.ip_address
            }
            for entry in self.audit_log
        ]

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(audit_data, f, indent=2)

        logger.info(f"Audit log saved: {log_file} ({len(audit_data)} entries)")

    def get_analytics(self) -> dict:
        """Get current query analytics."""
        return {
            "total_queries": self.analytics.total_queries,
            "factual_queries": self.analytics.factual_queries,
            "advisory_blocked": self.analytics.advisory_blocked,
            "pii_blocked": self.analytics.pii_blocked,
            "block_rate": (
                (self.analytics.advisory_blocked + self.analytics.pii_blocked) /
                self.analytics.total_queries * 100
                if self.analytics.total_queries > 0 else 0.0
            ),
            "avg_confidence": round(self.analytics.avg_confidence, 3),
            "avg_processing_time_ms": round(self.analytics.avg_processing_time_ms, 2),
            "hourly_distribution": self.analytics.hourly_distribution
        }

    def get_compliance_report(self) -> dict:
        """Generate comprehensive compliance report."""
        return {
            "report_generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": self.get_analytics(),
            "audit_log_size": len(self.audit_log),
            "rate_limits": {
                "max_per_minute": self.MAX_QUERIES_PER_MINUTE,
                "max_per_hour": self.MAX_QUERIES_PER_HOUR
            },
            "guardrail_rules": {
                "advisory_patterns": len(self.input_guardrail.ADVISORY_PATTERNS),
                "pii_patterns": len(self.input_guardrail.PII_PATTERNS),
                "max_response_sentences": self.output_guardrail.MAX_SENTENCES
            }
        }

    def clear_audit_log(self):
        """Clear in-memory audit log (saves to disk first)."""
        self.save_audit_log()
        self.audit_log.clear()
        logger.info("Audit log cleared (saved to disk)")
