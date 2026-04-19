# Phase 5 — Runtime Query Pipeline & Chat API

Complete RAG query-time pipeline with guardrails, retrieval, generation, and Flask API.

---

## 📋 Overview

Phase 5 implements the **user-facing query pipeline** that powers the chat assistant. When a user asks a question, this phase orchestrates the complete flow from input validation to response generation.

### Pipeline Flow

```
User Query
    ↓
┌──────────────────────┐
│ 1. INPUT GUARDRAIL    │  ← Validate: factual vs advisory vs PII
└──────────┬───────────┘
           ↓ (passes)
┌──────────────────────┐
│ 2. QUERY EMBEDDING    │  ← HuggingFace API (BGE model)
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ 3. VECTOR RETRIEVAL   │  ← Chroma Cloud similarity search
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ 4. CONTEXT ASSEMBLY   │  ← Merge chunks, deduplicate
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ 5. LLM GENERATION     │  ← Groq API (Llama 3.3 70B)
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ 6. OUTPUT GUARDRAIL   │  ← Validate: ≤3 sentences, citation
└──────────┬───────────┘
           ↓
     Final Response
```

---

## 🗂️ Components

### Phase 5.1: Guardrails (`guardrails.py`)

**Purpose**: Ensure compliance and safety

**Input Guardrail:**
- Detects advisory requests ("Should I invest?", "Which fund is better?")
- Detects PII (PAN, Aadhaar, phone, email, OTP)
- Returns polite refusal messages

**Output Guardrail:**
- Truncates responses to max 3 sentences
- Ensures source citation URL is present
- Appends "Last updated from sources" footer
- Removes advisory language from LLM response

**Example:**
```python
from phases.phase_5_runtime.guardrails import validate_input

result = validate_input("Should I invest in HDFC Top 100?")
print(result.classification)  # "ADVISORY"
print(result.is_safe)         # False
print(result.message)         # "I can only answer factual questions..."
```

---

### Phase 5.2: RAG Pipeline Orchestrator (`pipeline.py`)

**Purpose**: Tie all components together

**Features:**
- Complete query orchestration
- Context assembly from retrieved chunks
- Groq API integration with fallback (70B → 8B)
- Error handling and timeout management
- Performance metrics (processing time, confidence)

**Usage:**
```python
from phases.phase_5_runtime.pipeline import RAGPipeline

pipeline = RAGPipeline(
    embedding_service=embedding_service,
    retriever=retriever
)

result = pipeline.query(
    user_query="What is the expense ratio of HDFC Mid Cap Fund?",
    scheme_filter="HDFC Mid Cap Fund"
)

print(result.response)           # "The expense ratio is..."
print(result.source_url)         # "https://..."
print(result.confidence_score)   # 0.87
print(result.processing_time_ms) # 1250
```

---

### Phase 5.3: Chat API Routes (`routes.py`)

**Purpose**: Flask REST API endpoints

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send a message (with thread support) |
| GET | `/api/threads` | List all chat threads |
| GET | `/api/threads/<id>/messages` | Get thread message history |
| DELETE | `/api/threads/<id>` | Delete a thread |
| GET | `/api/health` | Health check |

**Example Request:**
```bash
curl http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the minimum SIP for HDFC Mid Cap Fund?",
    "scheme_filter": "HDFC Mid Cap Fund"
  }'
```

**Example Response:**
```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": "The minimum SIP amount for HDFC Mid Cap Fund is ₹500 per month.",
  "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
  "last_updated": "2026-04-19",
  "is_refusal": false,
  "confidence_score": 0.87,
  "processing_time_ms": 1250
}
```

---

### Phase 5.4: Session Manager (`session_manager.py`)

**Purpose**: Manage chat threads and message history

**Features:**
- Create/delete chat threads
- Store message history per thread
- Thread metadata (title, created_at, message_count)
- In-memory storage (upgradable to Redis)

**Usage:**
```python
from phases.phase_5_runtime.session_manager import SessionManager

session_mgr = SessionManager()

# Create thread
thread = session_mgr.create_thread("What is NAV?")

# Add messages
session_mgr.add_message(
    thread_id=thread.thread_id,
    role="user",
    content="What is NAV?"
)

session_mgr.add_message(
    thread_id=thread.thread_id,
    role="assistant",
    content="NAV stands for Net Asset Value...",
    source_url="https://..."
)

# Get thread history
messages = session_mgr.get_thread_messages(thread.thread_id)
```

---

## 🚀 Quick Start

### 1. Initialize Phase 5

```bash
cd backend
python phases/phase_5_runtime/main.py --mode init
```

### 2. Run Test Queries

```bash
# Run all test queries
python phases/phase_5_runtime/main.py --mode test

# Run single query
python phases/phase_5_runtime/main.py --mode test --query "What is the expense ratio?"
```

### 3. Start Flask Server

```bash
python app.py
```

Server will start at: http://localhost:5000

---

## 📊 API Examples

### Chat with Thread

```bash
# First message (creates thread)
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the NAV of HDFC Mid Cap Fund?"}'

# Response includes thread_id
{
  "thread_id": "abc-123-def",
  "response": "...",
  ...
}

# Continue conversation in same thread
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "abc-123-def",
    "message": "What about the expense ratio?"
  }'
```

### List All Threads

```bash
curl http://localhost:5000/api/threads
```

### Get Thread Messages

```bash
curl http://localhost:5000/api/threads/abc-123-def/messages
```

### Delete Thread

```bash
curl -X DELETE http://localhost:5000/api/threads/abc-123-def
```

### Health Check

```bash
curl http://localhost:5000/api/health
```

---

## 🔒 Guardrail Examples

### Advisory Query (Blocked)

**Input**: "Should I invest in HDFC Mid Cap Fund?"

**Response**:
```
I can only answer factual questions about mutual fund schemes, such as NAV, 
expense ratio, fund size, or minimum investment. I cannot provide investment 
advice or recommendations. Please consult a SEBI-registered financial advisor 
for personalized guidance.
```

### PII Detection (Blocked)

**Input**: "My PAN is ABCDE1234F, check my investments"

**Response**:
```
I cannot process personal information. Please remove sensitive details like 
PAN, Aadhaar, phone numbers, or email addresses and try again.
```

### Factual Query (Allowed)

**Input**: "What is the expense ratio of HDFC Mid Cap Fund?"

**Response**:
```
The expense ratio of HDFC Mid Cap Fund (Direct Plan) is 0.95% as of April 2026. 
Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth

Last updated from sources: 2026-04-19
```

---

## 🎯 Configuration

### Adjust Retrieval Settings

Edit `backend/phases/phase_5_runtime/pipeline.py`:

```python
TOP_K = 5                          # Number of chunks to retrieve
SIMILARITY_THRESHOLD = 0.65        # Minimum similarity score
```

### Change LLM Model

```python
PRIMARY_MODEL = "llama-3.3-70b-versatile"   # Best accuracy
FALLBACK_MODEL = "llama-3.3-8b-instant"     # Faster, cheaper
TEMPERATURE = 0.1                           # Deterministic
MAX_TOKENS = 300                            # Response length
```

### Modify Guardrail Rules

Edit `backend/phases/phase_5_runtime/guardrails.py`:

```python
# Add new advisory patterns
ADVISORY_PATTERNS = [
    r"should I invest",
    r"which fund is better",
    # Add more patterns...
]

# Adjust output constraints
MAX_SENTENCES = 3  # Max response length
```

---

## 🐛 Troubleshooting

### No Relevant Results

**Symptoms**: Low confidence scores or "no information" responses  
**Fix**:
1. Check if Chroma Cloud has data: `python phases/phase_4_3_indexing/main.py --mode status`
2. Verify embedding model matches indexing model
3. Try different query phrasing

### Groq API Errors

**Symptoms**: 429 (rate limit) or timeout  
**Fix**:
1. Automatic fallback to 8B model will trigger
2. Check Groq API key is valid
3. Wait for rate limit to reset

### Guardrail Blocking Valid Queries

**Symptoms**: False positives on advisory detection  
**Fix**:
1. Review `ADVISORY_PATTERNS` in guardrails.py
2. Remove overly broad patterns
3. Add exceptions for specific phrasing

---

## 📈 Performance

### Expected Response Times

| Component | Duration |
|-----------|----------|
| Input Guardrail | <10ms |
| Query Embedding | 200-500ms |
| Vector Retrieval | 50-150ms |
| Context Assembly | <10ms |
| LLM Generation (70B) | 800-1500ms |
| Output Guardrail | <10ms |
| **Total** | **1000-2200ms** |

### Optimization Tips

1. **Use 8B model for simple queries** (3x faster)
2. **Enable embedding cache** (skip repeated queries)
3. **Reduce TOP_K** (fewer chunks = less context)
4. **Use scheme filters** (narrower search = faster)

---

## 🔗 Dependencies

- **Phase 4.2**: EmbeddingService (for query embedding)
- **Core/Retriever**: Chroma Cloud retrieval
- **Groq API**: LLM generation
- **HuggingFace API**: Embedding generation

---

## 📚 Related Documentation

- **Architecture**: `docs/architecture.md` (Sections 7, 8, 9)
- **Chunking & Embedding**: `docs/chunking-embedding-architecture.md`
- **Guardrails Design**: `docs/architecture.md#8-guardrails--compliance-layer`
- **API Design**: `docs/architecture.md#9-backend-api-design-flask`

---

## ✅ Testing Checklist

Before deploying Phase 5:

- [ ] Input guardrail blocks advisory queries
- [ ] Input guardrail detects PII patterns
- [ ] Retrieval returns relevant chunks
- [ ] LLM generates factual responses
- [ ] Output guardrail enforces 3-sentence limit
- [ ] Responses include source citations
- [ ] Thread creation works
- [ ] Message history persists
- [ ] Health check endpoint responds
- [ ] Error handling works gracefully

---

**Version**: 1.0.0  
**Last Updated**: 2026-04-19  
**Status**: Production Ready
