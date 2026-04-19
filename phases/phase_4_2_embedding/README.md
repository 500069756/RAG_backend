# Phase 4.2 — Embedding Service

Converts text chunks into dense vector representations using HuggingFace Inference API for semantic search.

---

## Overview

Phase 4.2 is the **semantic layer** of the RAG pipeline. It transforms text chunks from Phase 4.1 into 384-dimensional vectors that capture semantic meaning, enabling similarity search in Chroma Cloud.

### Why Embeddings Matter

Embeddings are the foundation of semantic search. Good embeddings:
- ✅ Capture semantic meaning (not just keyword matching)
- ✅ Enable similarity search ("high risk" ≈ "volatile")
- ✅ Power filtered retrieval in Chroma Cloud
- ✅ Support both index-time (batch) and query-time (single) use cases

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 4.2 EMBEDDING                          │
│                                                                 │
│  ┌──────────────┐     ┌───────────────┐     ┌──────────────┐  │
│  │  Chunks from │────▶│  Check Cache  │────▶│  Cache HIT?  │  │
│  │  Phase 4.1   │     │  (by hash)    │     └──────┬───────┘  │
│  └──────────────┘     └───────────────┘       Yes │    │ No   │
│                                   ┌─────────────▼┐   │        │
│                                   │  Return      │   │        │
│                                   │  cached      │   │        │
│                                   │  embedding   │   │        │
│                                   └──────────────┘   │        │
│                                                      ▼        │
│                                              ┌─────────────┐  │
│                                              │  Batch (32) │  │
│                                              │  & call HF  │  │
│                                              │  Inference  │  │
│                                              │  API        │  │
│                                              └──────┬──────┘  │
│                                                     │         │
│                                              ┌──────▼──────┐  │
│                                              │  Validate   │  │
│                                              │  dimensions │  │
│                                              │  & quality  │  │
│                                              └──────┬──────┘  │
│                                                     │         │
│                                              ┌──────▼──────┐  │
│                                              │  Save to    │  │
│                                              │  local cache│  │
│                                              └──────┬──────┘  │
│                                                     │         │
│                                    ┌────────────────┘         │
│                                    ▼                          │
│                        ┌───────────────────────┐              │
│                        │  Embedded Chunks JSON │              │
│                        │  (to Phase 5/Indexer) │              │
│                        └───────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### 1. Dual-Mode Operation

| Mode | Use Case | Method | Batch Size |
|---|---|---|---|
| **Index Time** | Daily sync (GitHub Actions) | `embed_chunks()` | 32 chunks per API call |
| **Query Time** | User questions (Flask API) | `embed_single()` | 1 query per call |

### 2. Intelligent Caching

**Why cache?**
- Saves API calls (free tier has rate limits)
- Speeds up daily sync (only new/changed chunks need embedding)
- Reduces costs (no re-embedding identical content)

**How it works:**
```python
# Cache key = SHA-256(model + text)
key = hashlib.sha256(f"{model}:{text}".encode()).hexdigest()[:24]

# Cache structure:
data/embeddings_cache/
├── cache_index.json          # Index of all cached embeddings
├── abc123def456.json         # Individual embedding vector
├── ghi789jkl012.json         # (one file per unique chunk)
└── ...
```

**Cache hit example:**
```
INFO  Embedding 500 chunks (batch_size=32)
INFO    Cache hits: 450/500
INFO    To embed:   50 chunks
INFO  Batch 1/2: embedding 32 texts...
INFO  Batch 2/2: embedding 18 texts...
INFO  EMBEDDING SUMMARY
INFO    Total texts:    500
INFO    Cache hits:     450
INFO    API calls:      2
INFO    Cache hit rate: 90.0%
```

### 3. Batch Processing

**Optimized for HuggingFace free tier:**
- **Batch size**: 32 texts per API call
- **Rate limit delay**: 1 second between batches
- **Timeout**: 60 seconds per request
- **Concurrent**: No (sequential to avoid rate limits)

**Why 32?**
- HuggingFace free tier allows ~100 requests/minute
- 32 texts/batch × 2 batches/minute = 640 texts/minute
- Optimal balance between speed and reliability

### 4. Retry Logic with Exponential Backoff

**Handles common failures:**

| Error Code | Cause | Retry Strategy |
|---|---|---|
| **429** | Rate limited | Wait 2s → 5s → 15s (exponential backoff) |
| **503** | Model loading | Wait estimated_time (max 30s) |
| **Timeout** | Slow response | Retry up to 3 times |
| **ConnectionError** | Network issue | Retry up to 3 times |

**Retry flow:**
```python
Attempt 1 → Fail (429) → Wait 2s
Attempt 2 → Fail (429) → Wait 5s
Attempt 3 → Fail (429) → Wait 15s → Raise Exception
```

### 5. Embedding Quality Validation

**Every embedding is validated before use:**

```python
def _validate_embedding(self, embedding: list[float]) -> bool:
    # 1. Correct dimensions (384 for BAAI/bge-small-en-v1.5)
    if len(embedding) != 384:
        return False
    
    # 2. No NaN values
    if any(math.isnan(x) for x in embedding):
        return False
    
    # 3. No infinity values
    if any(math.isinf(x) for x in embedding):
        return False
    
    # 4. Non-zero magnitude (not a zero vector)
    magnitude = sum(x * x for x in embedding) ** 0.5
    if magnitude < 1e-6:
        return False
    
    return True
```

**Why validate?**
- Prevents corrupted embeddings from entering Chroma Cloud
- Catches API bugs or model issues early
- Ensures retrieval quality

---

## Model Selection

### Primary Model: `BAAI/bge-small-en-v1.5`

| Property | Value |
|---|---|
| **Dimensions** | 384 |
| **Max Tokens** | 512 |
| **Speed** | Fast (~100ms per batch) |
| **Quality** | Excellent for FAQ-style retrieval |
| **Storage** | 1.5 KB per vector |
| **HF API** | `BAAI/bge-small-en-v1.5` |

**Why this model?**
- ✅ 384 dimensions = lower storage cost in Chroma Cloud
- ✅ Fast inference on HF free tier
- ✅ **Open-source** — no proprietary vendor lock-in
- ✅ Excellent quality for short factual content (FAQs)
- ✅ Top-ranked on MTEB leaderboard for English retrieval
- ✅ Self-hostable for future deployment flexibility
- ✅ Small footprint = faster model loading

### Alternative Models

| Model | Dimensions | Speed | Quality | Use Case |
|---|---|---|---|---|
| `BAAI/bge-base-en-v1.5` | 768 | Medium | Better | Higher accuracy needs |
| `all-mpnet-base-v2` | 768 | Slower | Best | Premium tier (future upgrade) |

**To switch models:**
```bash
python -m phases.phase_4_2_embedding --model BAAI/bge-base-en-v1.5
```

⚠️ **Warning:** Changing models invalidates all cached embeddings!

---

## Usage

### Basic Usage

```bash
# Embed all chunks from default location
python -m phases.phase_4_2_embedding --mode embed

# Embed with custom paths
python -m phases.phase_4_2_embedding \
    --input data/chunks/ \
    --output data/embedded/ \
    --cache data/embeddings_cache/

# Clear cache and re-embed everything
python -m phases.phase_4_2_embedding --mode embed --clear-cache

# Use a different model
python -m phases.phase_4_2_embedding --model BAAI/bge-base-en-v1.5
```

### Programmatic Usage

```python
from phases.phase_4_2_embedding import EmbeddingService

# Initialize embedder
embedder = EmbeddingService(
    api_token="hf_xxx",  # or set HF_API_TOKEN env var
    model="BAAI/bge-small-en-v1.5",
    cache_dir="data/embeddings_cache/"
)

# Index time: Embed batch of chunks
chunks = [
    {"text": "What is NAV?", "chunk_index": 0},
    {"text": "NAV = Net Asset Value...", "chunk_index": 1}
]
enriched = embedder.embed_chunks(chunks)

# Query time: Embed single query
query_vector = embedder.embed_single("What does NAV mean?")
```

---

## API Integration

### Index Time (Daily Sync via GitHub Actions)

```yaml
# .github/workflows/daily-sync.yml
- name: Run Embedding Service
  run: python -m phases.phase_4_2_embedding --mode embed
  env:
    HF_API_TOKEN: ${{ secrets.HF_API_TOKEN }}
```

### Query Time (Flask API)

```python
# backend/core/retriever.py
from phases.phase_4_2_embedding import EmbeddingService

embedder = EmbeddingService()

def search(query: str) -> list:
    # Embed query
    query_vector = embedder.embed_single(query)
    
    # Search Chroma Cloud
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=5
    )
    
    return results
```

---

## Output Format

### Embedded Chunks JSON

```json
[
  {
    "text": "What is NAV? NAV stands for Net Asset Value...",
    "chunk_index": 0,
    "metadata": {
      "source_url": "https://www.hdfcfund.com/en/knowledge-center/mutual-funds/basics-of-mutual-funds/what-is-nav-in-mutual-fund",
      "scheme_name": "General",
      "category": "FAQ",
      "document_type": "faq"
    },
    "embedding": [0.0234, -0.0456, 0.0789, ...]  // 384 dimensions
  },
  ...
]
```

### Pipeline Stats JSON

```json
{
  "status": "success",
  "timestamp": "2026-04-19T09:30:00+00:00",
  "model": "BAAI/bge-small-en-v1.5",
  "chunks_processed": 485,
  "chunks_failed": 15,
  "elapsed_seconds": 127.45,
  "embedding_stats": {
    "total": 500,
    "cache_hits": 450,
    "api_calls": 2,
    "failures": 15,
    "cache_hit_rate": 90.0,
    "avg_time_per_embedding_ms": 254.9,
    "total_time_seconds": 127.45
  }
}
```

---

## Performance Metrics

### Expected Performance (HuggingFace Free Tier)

| Metric | Value | Notes |
|---|---|---|
| **Batch embedding (32 chunks)** | 2-5 seconds | Depends on model load state |
| **Single query embedding** | 100-300ms | Cached: <10ms |
| **Cache hit rate (daily sync)** | 80-95% | Only new/changed chunks miss |
| **500 chunks (no cache)** | ~120 seconds | 16 batches × 7.5s avg |
| **500 chunks (90% cache)** | ~15 seconds | Only 50 chunks need API calls |

### Optimization Tips

1. **Keep cache between runs** → 90%+ hit rate on daily sync
2. **Use batch mode** → 32× faster than single embeddings
3. **Monitor rate limits** → Add delays if hitting 429 errors
4. **Validate embeddings** → Catch quality issues early

---

## Troubleshooting

### Common Issues

#### 1. HF_API_TOKEN not set

```
ERROR  Configuration error: HF_API_TOKEN is required
```

**Solution:**
```bash
export HF_API_TOKEN=hf_your_token_here
# or add to .env file
```

#### 2. Rate Limited (HTTP 429)

```
WARNING  HF API rate limited, waiting 2s (attempt 1/3)
```

**Solution:**
- Automatic retry with backoff is built-in
- Increase `RATE_LIMIT_DELAY` in code if persistent
- Consider upgrading to HuggingFace Pro tier

#### 3. Model Loading (HTTP 503)

```
INFO  Model loading, waiting 20s...
```

**Solution:**
- Wait for model to load (automatic)
- First run takes longer (cold start)
- Subsequent runs are faster (model cached by HF)

#### 4. Invalid Embedding Dimensions

```
ERROR  Dimension mismatch: expected 384, got 768
```

**Solution:**
- Check `HF_EMBEDDING_MODEL` matches expected dimensions
- Clear cache if switching models: `--clear-cache`

#### 5. Empty Embeddings Returned

```
ERROR  Batch 3 returned empty — skipping
```

**Solution:**
- Check HuggingFace API status: https://status.huggingface.co
- Verify API token is valid
- Check chunk text is not empty

---

## Best Practices

### 1. Cache Management

```bash
# Clear cache when changing models
python -m phases.phase_4_2_embedding --clear-cache

# Monitor cache size
ls -lh data/embeddings_cache/

# Backup cache (for CI/CD artifacts)
tar -czf embedding_cache.tar.gz data/embeddings_cache/
```

### 2. Model Consistency

**Always use the same model for:**
- Index-time embedding (daily sync)
- Query-time embedding (Flask API)

**Why?** Different models produce incompatible vectors!

### 3. Error Handling

```python
try:
    vector = embedder.embed_single(query)
except Exception as e:
    logger.error(f"Embedding failed: {e}")
    # Fallback: return error response to user
    return {"error": "Search temporarily unavailable"}
```

### 4. Monitoring

**Track these metrics:**
- Cache hit rate (should be >80% for daily sync)
- API call failures (should be <5%)
- Average embedding time (should be <300ms)
- Dimension validation failures (should be 0)

---

## Integration with Other Phases

```
Phase 4.0 (Scraper)     →  Raw HTML/PDF text
        ↓
Phase 4.1 (Chunker)     →  Text chunks with metadata
        ↓
Phase 4.2 (Embedder)    →  Embedded chunks with vectors  ← YOU ARE HERE
        ↓
Phase 5.0 (Indexer)     →  Chroma Cloud upsert
        ↓
Phase 6.0 (Retriever)   →  Semantic search at query time
```

---

## Files

| File | Purpose |
|---|---|
| `embedder.py` | EmbeddingService implementation |
| `main.py` | Pipeline orchestrator + CLI |
| `README.md` | This documentation |

---

## Next Steps

After embedding, chunks flow to:
- **Phase 5.0 (Indexer)** → Upsert into Chroma Cloud
- **Phase 6.0 (Retriever)** → Query-time embedding + search

See [architecture.md](../../docs/architecture.md) for full pipeline details.
