"""
Core package — RAG pipeline services for query-time operations.

Components:
    - Guardrails:  Input/Output compliance (PII, advisory detection)
    - Retriever:   Chroma Cloud vector search
    - Generator:   Groq LLM response generation
    - Pipeline:    RAG orchestrator (ties it all together)
"""
