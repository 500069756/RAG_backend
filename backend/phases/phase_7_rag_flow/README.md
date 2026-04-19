# Phase 7 — Retrieval & Generation Flow

Complete end-to-end RAG query pipeline as per architecture.md Section 7.

---

## 📋 Overview

Phase 7 implements the **complete Retrieval & Generation Flow** that powers the Mutual Fund FAQ Assistant. This is the master orchestration layer that brings together all components into a unified pipeline.

### Architecture Reference

This phase implements **architecture.md Section 7**:
- **7.1**: End-to-End Query Pipeline
- **7.2**: System Prompt Template
- **7.3**: Groq API Integration
- **7.4**: Model Selection Strategy

---

## 🔄 Pipeline Flow (Section 7.1)

```
User Query
    │
    ▼
┌──────────────────────┐
│  1. INPUT GUARDRAIL   │  ← Classify: factual vs. advisory vs. PII
│     (Pre-Retrieval)   │     If advisory → return refusal response
│                       │     If PII detected → reject immediately
└──────────┬───────────┘
           │ (factual query passes)
           ▼
┌──────────────────────┐
│  2. QUERY EMBEDDING   │  ← HuggingFace Inference API
│                       │     Same model as indexing (BGE-small-en-v1.5)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  3. VECTOR RETRIEVAL  │  ← Chroma Cloud similarity search
│     Top-K = 5         │     Filter by metadata if scheme specified
│     Threshold ≥ 0.65  │     Returns ranked chunks + metadata
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  4. CONTEXT ASSEMBLY  │  ← Merge top chunks into prompt context
│                       │     Deduplicate overlapping chunks
│                       │     Attach source URLs
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  5. LLM GENERATION    │  ← Groq API (Llama 3.3 70B)
│     (Prompted)        │     System prompt enforces constraints
│                       │     Temperature = 0.1 (deterministic)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  6. OUTPUT GUARDRAIL  │  ← Validate: ≤3 sentences, has citation
│     (Post-Generation) │     Strip any accidental advice
│                       │     Append "Last updated" footer
└──────────┬───────────┘
           │
           ▼
     Final Response
```

---

## 🧩 Component Integration

Phase 7 orchestrates these existing components:

| Step | Component | Source | Purpose |
|------|-----------|--------|---------|
| 1 | Input Guardrail | `phases/phase_5_runtime/guardrails.py` | Query validation |
| 2 | Query Embedding | `phases/phase_4_2_embedding/embedder.py` | Embed user query |
| 3 | Vector Retrieval | `core/retriever.py` | Chroma Cloud search |
| 4 | Context Assembly | `phases/phase_5_runtime/pipeline.py` | Merge chunks |
| 5 | LLM Generation | `phases/phase_5_runtime/pipeline.py` | **Groq API** |
| 6 | Output Guardrail | `phases/phase_5_runtime/guardrails.py` | Response validation |

---

## 🎯 Groq LLM Integration (Section 7.3)

### Configuration

**Primary Model**: `llama-3.3-70b-versatile`
- Best accuracy for factual responses
- Production default

**Fallback Model**: `llama-3.3-8b-instant`
- 3x faster than 70B
- Automatic fallback on rate limit (429) or timeout
- Suitable for simple lookups

### Groq API Settings

```python
from groq import Groq

client = Groq(api_key=GROQ_API_KEY)

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query}
    ],
    temperature=0.1,      # Deterministic responses
    max_tokens=300,       # Max response length
    top_p=0.9,            # Nucleus sampling
)
```

### Model Selection Strategy (Section 7.4)

| Scenario | Model | Rationale |
|---|---|---|
| **Default (Production)** | `llama-3.3-70b-versatile` | Best accuracy for factual responses |
| **High Traffic / Cost Saving** | `llama-3.3-8b-instant` | 3x faster, suitable for simple lookups |
| **Fallback** | Auto-switch 70B → 8B | On Groq rate-limit (429) or timeout |

---

## 📝 System Prompt Template (Section 7.2)

```text
You are a facts-only Mutual Fund FAQ assistant. Follow these rules STRICTLY:

1. Answer ONLY factual, verifiable questions about mutual fund schemes.
2. Use ONLY the provided context to answer. Do NOT use external knowledge.
3. Keep responses to a MAXIMUM of 3 sentences.
4. Include EXACTLY ONE source citation URL from the context.
5. End every response with: "Last updated from sources: {last_scraped_date}"
6. NEVER provide investment advice, opinions, performance comparisons, or recommendations.
7. If the question asks for advice or comparison, respond with a polite refusal.
8. NEVER ask for or acknowledge PII (PAN, Aadhaar, account numbers, email, phone, OTP).

CONTEXT:
{retrieved_chunks}

SOURCE URLS:
{source_urls}

USER QUESTION:
{user_query}
```

---

## 🚀 Quick Start

### 1. Initialize Phase 7

```bash
cd backend
python phases/phase_7_rag_flow/main.py --mode init
```

### 2. Run Demo Queries

```bash
python phases/phase_7_rag_flow/main.py --mode demo
```

This runs 6 predefined queries showcasing:
- Factual queries (NAV, SIP, expense ratio, fund size)
- Advisory queries (blocked by guardrails)
- Comparison queries (blocked by guardrails)

### 3. Interactive Testing

```bash
python phases/phase_7_rag_flow/main.py --mode interactive
```

Type your own questions and see real-time responses!

### 4. Single Query Test

```bash
python phases/phase_7_rag_flow/main.py --mode test --query "What is the expense ratio?"
```

### 5. Start Flask Server

```bash
python app.py
```

Server runs at: http://localhost:5000

---

## 📊 Expected Performance

| Component | Duration | Notes |
|---|---|---|
| Input Guardrail | <10ms | Pattern matching |
| Query Embedding | 200-500ms | HuggingFace API |
| Vector Retrieval | 50-150ms | Chroma Cloud search |
| Context Assembly | <10ms | String concatenation |
| LLM Generation (70B) | 800-1,500ms | **Groq API** |
| Output Guardrail | <10ms | Validation |
| **Total** | **1,000-2,200ms** | End-to-end |

---

## 🔒 Guardrail Examples

### ✅ Factual Query (Allowed)

**Input**: "What is the expense ratio of HDFC Mid Cap Fund?"

**Response**:
```
The expense ratio of HDFC Mid Cap Fund (Direct Plan) is 0.95% as of April 2026. 
Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth

Last updated from sources: 2026-04-19
```

**Metadata**:
- Confidence: 0.87
- Processing Time: 1,250ms
- Chunks Used: 3

---

### 🚫 Advisory Query (Blocked)

**Input**: "Should I invest in HDFC Mid Cap Fund?"

**Response**:
```
I can only answer factual questions about mutual fund schemes, such as NAV, 
expense ratio, fund size, or minimum investment. I cannot provide investment 
advice or recommendations. Please consult a SEBI-registered financial advisor 
for personalized guidance.
```

**Metadata**:
- is_refusal: true
- Confidence: 0.0
- Classification: ADVISORY

---

### 🚫 PII Query (Blocked)

**Input**: "My PAN is ABCDE1234F, check my investments"

**Response**:
```
I cannot process personal information. Please remove sensitive details like 
PAN, Aadhaar, phone numbers, or email addresses and try again.
```

**Metadata**:
- is_refusal: true
- Classification: PII_DETECTED

---

## 💡 Usage Examples

### Python API

```python
from phases.phase_7_rag_flow.main import initialize_phase7

# Initialize pipeline
pipeline, session_manager = initialize_phase7()

# Execute query
result = pipeline.query(
    user_query="What is the NAV of HDFC Mid Cap Fund?",
    scheme_filter="HDFC Mid Cap Fund"  # Optional
)

# Access results
print(result.response)            # "The NAV is..."
print(result.source_url)          # "https://..."
print(result.confidence_score)    # 0.87
print(result.processing_time_ms)  # 1250
print(result.is_refusal)          # False
```

### REST API

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the minimum SIP for HDFC Mid Cap Fund?",
    "scheme_filter": "HDFC Mid Cap Fund"
  }'
```

**Response**:
```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": "The minimum SIP amount for HDFC Mid Cap Fund is ₹500 per month. Source: https://groww.in/...",
  "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
  "last_updated": "2026-04-19",
  "is_refusal": false,
  "confidence_score": 0.87,
  "processing_time_ms": 1250
}
```

---

## 🔧 Configuration

### Adjust Retrieval Settings

Edit `backend/phases/phase_5_runtime/pipeline.py`:

```python
TOP_K = 5                          # Number of chunks to retrieve
SIMILARITY_THRESHOLD = 0.65        # Minimum similarity score
```

### Change Groq Model Settings

```python
PRIMARY_MODEL = "llama-3.3-70b-versatile"   # Best accuracy
FALLBACK_MODEL = "llama-3.3-8b-instant"     # Faster, cheaper
TEMPERATURE = 0.1                           # Deterministic (0.0-1.0)
MAX_TOKENS = 300                            # Response length
TOP_P = 0.9                                 # Nucleus sampling
```

### Modify System Prompt

Edit `backend/phases/phase_5_runtime/pipeline.py` → `_build_system_prompt()` method:

```python
def _build_system_prompt(self, context: str, source_urls: list[str]) -> str:
    return f"""You are a facts-only Mutual Fund FAQ assistant. Follow these rules STRICTLY:

1. Answer ONLY factual, verifiable questions about mutual fund schemes.
2. Use ONLY the provided context to answer. Do NOT use external knowledge.
3. Keep responses to a MAXIMUM of 3 sentences.
# Add/modify rules as needed...
"""
```

---

## 🐛 Troubleshooting

### No Relevant Results

**Symptoms**: Low confidence scores or "no information" responses

**Fix**:
1. **Check Chroma Cloud has data**:
   ```bash
   python phases/phase_4_3_indexing/main.py --mode status
   ```

2. **Run full ingestion pipeline** (if empty):
   ```bash
   python phases/phase_4_scheduler/main.py --mode full
   python phases/phase_4_1_chunking/main.py --mode full
   python phases/phase_4_2_embedding/main.py --mode embed
   python phases/phase_4_3_indexing/main.py --mode upsert
   ```

3. **Verify embedding model matches**:
   - Index time: `BAAI/bge-small-en-v1.5`
   - Query time: `BAAI/bge-small-en-v1.5`
   - **Must be identical!**

### Groq API Errors

**Symptoms**: 429 (rate limit) or timeout

**Fix**:
1. **Automatic fallback** to 8B model will trigger
2. **Check Groq API key** is valid: `https://console.groq.com/keys`
3. **Wait for rate limit** to reset (typically 1 minute)
4. **Upgrade Groq plan** for higher limits

### Guardrail False Positives

**Symptoms**: Valid queries blocked as advisory

**Fix**:
1. Review `ADVISORY_PATTERNS` in `backend/phases/phase_5_runtime/guardrails.py`
2. Remove overly broad patterns
3. Add exceptions for specific phrasing

---

## 📈 Monitoring

### Key Metrics to Track

| Metric | Target | Alert Threshold |
|---|---|---|
| Response Time | <2,000ms | >3,000ms |
| Confidence Score | >0.70 | <0.60 |
| Guardrail Blocks | <10% of queries | >20% |
| Groq API Errors | <1% | >5% |
| Chroma Retrieval | <200ms | >500ms |

### Logging

Phase 7 logs all pipeline steps:

```
2026-04-19 10:30:45 [phase_7_rag_flow.main] INFO: Phase 7: Retrieval & Generation Flow - Initialization
2026-04-19 10:30:45 [phase_7_rag_flow.main] INFO: [1/5] Initializing Embedding Service (Phase 4.2)...
2026-04-19 10:30:45 [phase_7_rag_flow.main] INFO:   ✅ Model: BAAI/bge-small-en-v1.5
2026-04-19 10:30:45 [phase_7_rag_flow.main] INFO:   ✅ Dimensions: 384
...
2026-04-19 10:30:46 [phase_5_runtime.pipeline] INFO: Processing query: "What is the expense ratio..."
2026-04-19 10:30:46 [phase_5_runtime.pipeline] INFO: Step 2-3: Retrieving relevant chunks...
2026-04-19 10:30:47 [phase_5_runtime.pipeline] INFO: Step 5: Generating response with Groq...
2026-04-19 10:30:48 [phase_5_runtime.pipeline] INFO: Query completed in 1250ms (confidence: 0.870, chunks: 3)
```

---

## 🔗 Related Documentation

- **Architecture**: `docs/architecture.md` (Section 7)
- **Phase 5 Runtime**: `backend/phases/phase_5_runtime/README.md`
- **Phase 4 Embedding**: `backend/phases/phase_4_2_embedding/README.md`
- **Guardrails**: `docs/architecture.md#8-guardrails--compliance-layer`
- **Groq API**: `https://console.groq.com/docs`

---

## ✅ Implementation Checklist

- [x] Input Guardrail (advisory + PII detection)
- [x] Query Embedding (HuggingFace BGE model)
- [x] Vector Retrieval (Chroma Cloud similarity search)
- [x] Context Assembly (merge chunks, deduplicate)
- [x] LLM Generation (Groq API with Llama 3.3 70B)
- [x] Output Guardrail (3-sentence limit, citations)
- [x] Fallback mechanism (70B → 8B)
- [x] Performance metrics (time, confidence)
- [x] Error handling (graceful degradation)
- [x] Interactive testing mode
- [x] Demo queries
- [x] Comprehensive documentation

---

## 🎉 Production Deployment

### Environment Variables Required

```bash
# Groq API (LLM Generation)
GROQ_API_KEY=gsk_your_key_here

# Chroma Cloud (Vector Storage)
CHROMA_API_KEY=ck_your_key_here
CHROMA_TENANT=your-tenant-id
CHROMA_DATABASE=your-database-name

# HuggingFace (Embeddings)
HF_API_TOKEN=hf_your_token_here
```

### Start Production Server

```bash
# Using Gunicorn (production WSGI server)
gunicorn "app:create_app()" -w 2 -b 0.0.0.0:$PORT
```

### Health Check

```bash
curl http://your-app.onrender.com/api/health
```

**Expected Response**:
```json
{
  "status": "healthy",
  "chroma": "connected",
  "groq": "reachable",
  "hf": "reachable",
  "version": "1.0.0"
}
```

---

**Version**: 1.0.0  
**Last Updated**: 2026-04-19  
**Status**: ✅ Production Ready  
**Architecture**: Section 7 (Retrieval & Generation Flow)
