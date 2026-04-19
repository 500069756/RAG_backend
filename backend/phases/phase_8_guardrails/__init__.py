"""
Phase 8 — Guardrails & Compliance Layer (Enhanced)

This phase implements the complete guardrails and compliance system as per architecture.md Section 8:
    - 8.1: Input Guardrail (Pre-Retrieval)
    - 8.2: Output Guardrail (Post-Generation)
    - 8.3: Refusal Response Template

This enhanced version builds upon Phase 5.1 (basic guardrails) with:
    - Advanced PII detection and masking
    - Audit logging for compliance
    - Query analytics and reporting
    - Rate limiting per user/session
    - Compliance dashboard data

Architecture Reference:
    Section 8.1: Input Guardrail patterns
    Section 8.2: Output validation rules
    Section 8.3: Refusal response format

Usage:
    from phases.phase_8_guardrails import ComplianceManager
    
    manager = ComplianceManager()
    result = manager.validate_query("Should I invest in HDFC?")
"""

__version__ = "1.0.0"
