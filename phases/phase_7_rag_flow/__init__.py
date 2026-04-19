"""
Phase 7 — Retrieval & Generation Flow (Complete RAG Pipeline)

This phase implements the end-to-end query pipeline as per architecture.md Section 7:
    - 7.1: End-to-End Query Pipeline
    - 7.2: System Prompt Template
    - 7.3: Groq API Integration
    - 7.4: Model Selection Strategy

This module orchestrates all components from Phase 5 (Runtime) into a unified pipeline:
    1. Input Guardrail (Phase 5.1)
    2. Query Embedding (Phase 4.2)
    3. Vector Retrieval (core/retriever.py)
    4. Context Assembly (Phase 5.2)
    5. LLM Generation with Groq (Phase 5.2)
    6. Output Guardrail (Phase 5.1)

Usage:
    python -m phases.phase_7_rag_flow.main --mode test
    python -m phases.phase_7_rag_flow.main --mode serve
"""

__version__ = "1.0.0"
