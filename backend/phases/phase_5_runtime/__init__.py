"""
Phase 5 — Runtime Query Pipeline & Chat API

This phase implements the complete RAG query-time pipeline:
    - Phase 5.1: Guardrails (Input/Output validation)
    - Phase 5.2: RAG Pipeline Orchestrator
    - Phase 5.3: Chat API Endpoints (Flask)
    - Phase 5.4: Session & Thread Management

Components:
    - guardrails.py: Input/output validation and compliance
    - pipeline.py: RAG orchestrator (retrieval → generation)
    - routes.py: Flask API endpoints
    - session_manager.py: Chat thread management
"""

__version__ = "1.0.0"
