# Phase 4.3 — Indexer Service (Vector DB Upsert)

Manages Chroma Cloud collections: upsert, versioning, rollback, and cleanup for semantic search.

---

## Overview

Phase 4.3 is the **storage layer** of the RAG pipeline. It takes embedded chunks from Phase 4.2 and upserts them into Chroma Cloud with intelligent versioning and quality guards.

### Why Indexing Matters

Good indexing ensures:
- ✅ **No stale data** — Clean-on-Source-Change prevents phantom chunks
- ✅ **Version control** — Date-versioned collections enable rollback
- ✅ **Quality assurance** — Volume checks catch indexing failures
- ✅ **Cost efficiency** — Batch upserts minimize API calls

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 4.3 INDEXING                           │
│                                                                 │
│  ┌──────────────┐     ┌───────────────┐     ┌──────────────┐  │
│  │  Embedded    │────▶│  Create New   │────▶│  Clean Old   │  │
│  │  Chunks from │     │  Collection   │     │  Source IDs  │  │
│  │  Phase 4.2   │     │  (YYYYMMDD)   │     │  (Delete)    │  │
│  └──────────────┘     └───────────────┘     └──────┬───────┘  │
│                                                    │          │
│                                                    ▼          │
│                                              ┌─────────────┐  │
│                                              │  Batch      │  │
│                                              │  Upsert     │  │
│                                              │  (100/chunk)│  │
│                                              └──────┬──────┘  │
│                                                     │         │
│                                              ┌──────▼──────┐  │
│                                              │  Quality    │  │
│                                              │  Verification│ │
│                                              └──────┬──────┘  │
│                                                     │         │
│                                          Pass ┌──────▼──────┐  │
│                                               │  Promote    │  │
│                                               │  Collection │  │
│                                               └──────┬──────┘  │
│                                                      │         │
│                                               ┌──────▼──────┐  │
│                                               │  Cleanup    │  │
│                                               │  Old Versions│ │
│                                               │  (Keep 3)   │  │
│                                               └─────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### 1. Clean-on-Source-Change Strategy

**Problem:** Daily syncs create "phantom chunks" — stale segments from older document versions.

**Solution:** Delete old chunks by source_id before upserting new ones.

```python
# For each unique source_id in today's sync:
for source_id in unique_source_ids:
    # Delete ALL existing chunks with this source_id
    collection.delete(where={"source_id": source_id})
    
    # Upsert NEW chunks with this source_id
    collection.upsert(ids, embeddings, documents, metadatas)
```

**Benefits:**
- ✅ No phantom chunks
- ✅ Collection stays current
- ✅ No full rebuild needed
- ✅ Atomic per-source updates

### 2. Date-Versioned Collections

**Naming convention:** `mutual_fund_faq_YYYYMMDD`

**Example:**
```
mutual_fund_faq_20260417  (yesterday)
mutual_fund_faq_20260418  (today — active)
mutual_fund_faq_20260419  (tomorrow)
```

**Why version?**
- ✅ Rollback if something breaks
- ✅ Compare versions side-by-side
- ✅ Audit trail of changes
- ✅ Zero-downtime updates

### 3. Quality Verification

**Three-level checks after every upsert:**

#### Level 1: Volume Check
```python
# If document count drops by >20%, fail
drop_ratio = (previous_count - current_count) / previous_count
if drop_ratio > 0.20:
    raise Exception("Volume check FAILED")
```

**Rationale:** Catches partial indexing or corrupted uploads.

#### Level 2: Query Test
```python
# Verify collection is queryable
collection.query(
    query_embeddings=[[0.0] * 384],
    n_results=1
)
```

**Rationale:** Ensures index is not corrupted.

#### Level 3: Metadata Scan (Optional)
```python
# Sample 100 chunks and verify mandatory fields
sample = collection.get(limit=100)
for metadata in sample['metadatas']:
    assert 'source_url' in metadata
    assert 'scheme_name' in metadata
```

**Rationale:** Prevents broken citations in UI.

### 4. Rollback Protection

**If verification fails:**
```python
if not verify_collection(new_collection):
    # Delete failed collection
    client.delete_collection(new_collection)
    
    # Previous version stays active
    logger.info("Rolled back — previous version still active")
```

**Benefits:**
- ✅ Zero downtime
- ✅ Automatic fallback
- ✅ No manual intervention needed

### 5. Old Version Cleanup

**Keep last 3 versions, delete the rest:**
```python
versions = ["mutual_fund_faq_20260415",
            "mutual_fund_faq_20260416",
            "mutual_fund_faq_20260417",
            "mutual_fund_faq_20260418"]

# Keep last 3, delete oldest
delete("mutual_fund_faq_20260415")
```

**Why keep 3?**
- ✅ Current version (active)
- ✅ Previous version (rollback target)
- ✅ Backup version (safety net)

---

## Upsert Strategy Details

### Batch Processing

| Parameter | Value | Rationale |
|---|---|---|
| **Batch Size** | 100 chunks | Chroma recommended limit |
| **Concurrent** | No (sequential) | Avoid rate limits |
| **Retry** | 3 attempts | Handle transient errors |

### Metadata Schema

Every chunk upserted includes:

```json
{
  "source_url": "https://www.hdfcfund.com/...",
  "source_id": "hdfc-top100-factsheet-20260419",
  "scheme_name": "HDFC Top 100 Fund",
  "document_type": "factsheet",
  "category": "large-cap",
  "scraped_at": "2026-04-19T09:15:00Z",
  "chunk_index": 4,
  "total_chunks": 12,
  "token_count": 387,
  "content_hash": "sha256_abc123",
  "embedding_model": "BAAI/bge-small-en-v1.5"
}
```

**Why so much metadata?**
- Powers filtered retrieval (`where` clauses)
- Enables citations in responses
- Tracks embedding model for compatibility
- Supports analytics and debugging

---

## Usage

### Basic Usage

```bash
# Upsert embedded chunks to Chroma Cloud
python -m phases.phase_4_3_indexing --mode upsert

# Upsert with custom input directory
python -m phases.phase_4_3_indexing \
    --input data/embedded/ \
    --collection mutual_fund_faq

# Upsert with specific date
python -m phases.phase_4_3_indexing --date 20260419
```

### Maintenance Commands

```bash
# Verify active collection
python -m phases.phase_4_3_indexing --mode verify

# Cleanup old versions (keep last 3)
python -m phases.phase_4_3_indexing --mode cleanup

# Rollback to previous version
python -m phases.phase_4_3_indexing --mode rollback
```

### Programmatic Usage

```python
from phases.phase_4_3_indexing import IndexerService

# Initialize indexer
indexer = IndexerService()

# Create today's collection
collection = indexer.create_collection()

# Upsert chunks
embedded_chunks = [...]  # From Phase 4.2
indexer.upsert_chunks(collection, embedded_chunks)

# Verify and promote
if indexer.verify_collection(collection.name):
    indexer.promote_collection(collection.name)
    indexer.cleanup_old_versions()
```

---

## Collection Lifecycle

### Daily Sync Flow

```
1. Load embedded_chunks.json from Phase 4.2
2. Create new collection: mutual_fund_faq_20260419
3. For each unique source_id:
   a. Delete old chunks with this source_id
   b. Upsert new chunks with this source_id
4. Verify collection:
   a. Volume check (count didn't drop >20%)
   b. Query test (collection is queryable)
5. If verification passes:
   a. Promote collection (it's now active)
   b. Cleanup old versions (keep last 3)
6. If verification fails:
   a. Delete failed collection
   b. Previous version stays active
```

### Rollback Scenario

```
Day 1: mutual_fund_faq_20260418 (1000 chunks) — ACTIVE
Day 2: mutual_fund_faq_20260419 (200 chunks) — FAILED VERIFICATION

Action:
- Delete mutual_fund_faq_20260419
- mutual_fund_faq_20260418 stays ACTIVE

Result: Zero downtime, automatic fallback
```

---

## Integration with Other Phases

```
Phase 4.0 (Scraper)     →  Raw HTML/PDF text
        ↓
Phase 4.1 (Chunker)     →  Text chunks with metadata
        ↓
Phase 4.2 (Embedder)    →  Embedded chunks with vectors
        ↓
Phase 4.3 (Indexer)     →  Chroma Cloud upsert  ← YOU ARE HERE
        ↓
Phase 6.0 (Retriever)   →  Semantic search at query time
```

---

## Chroma Cloud Connection

### Required Environment Variables

```bash
CHROMA_API_KEY=ck_xxxxxxxx        # Authentication
CHROMA_TENANT=your-tenant         # Multi-tenant isolation
CHROMA_DATABASE=your-database     # Database name
CHROMA_COLLECTION_BASE=mutual_fund_faq  # Collection prefix
```

### Connection Code

```python
import chromadb

client = chromadb.HttpClient(
    host="api.trychroma.com",
    port=443,
    ssl=True,
    headers={"Authorization": f"Bearer {api_key}"},
    tenant=tenant,
    database=database
)
```

**See:** [Chroma Cloud Setup Guide](../../docs/chroma-cloud-setup.md)

---

## Troubleshooting

### Common Issues

#### 1. No Collections Found

```
RuntimeError: No indexed collections found in Chroma Cloud!
```

**Solution:**
- Run upsert mode first: `--mode upsert`
- Check CHROMA_TENANT and CHROMA_DATABASE are correct
- Verify API key has read permissions

#### 2. Volume Check Failed

```
ERROR  Volume check FAILED: 45.2% drop (threshold: 20%)
```

**Causes:**
- Partial embedding (some chunks failed Phase 4.2)
- Wrong source_id filtering
- Network timeout during upsert

**Solution:**
- Check Phase 4.2 logs for embedding failures
- Verify source_id metadata is consistent
- Re-run upsert with `--mode upsert`

#### 3. Upsert Batch Failed

```
ERROR  Batch 3/5 failed: Connection timeout
```

**Solution:**
- Automatic retry is built-in (3 attempts)
- Check Chroma Cloud status: https://status.trychroma.com
- Verify network connectivity

#### 4. Rollback Failed

```
ERROR  Cannot rollback: less than 2 versions available
```

**Solution:**
- Only 1 version exists — no previous version to rollback to
- Run a successful upsert first to create a second version

---

## Performance Metrics

### Expected Performance (Chroma Cloud)

| Metric | Value | Notes |
|---|---|---|
| **Upsert batch (100 chunks)** | 2-5 seconds | Depends on embedding size |
| **Delete by source_id** | 1-3 seconds | Depends on chunk count |
| **Volume check** | <1 second | Simple count query |
| **500 chunks total** | ~30 seconds | 5 batches × 6s avg |
| **Cleanup old versions** | 5-10 seconds | Deletes 1 collection |

### Optimization Tips

1. **Batch size 100** — Chroma's recommended limit
2. **Sequential upserts** — Avoid rate limits
3. **Delete before upsert** — Keeps collection size manageable
4. **Monitor volume changes** — Catch issues early

---

## Best Practices

### 1. Always Verify Before Promoting

```python
# Don't skip verification!
if indexer.verify_collection(collection.name, previous_count):
    indexer.promote_collection(collection.name)
else:
    indexer.rollback()  # Safe fallback
```

### 2. Keep Metadata Consistent

```python
# Always include these fields:
metadata = {
    "source_url": "...",      # For citations
    "source_id": "...",       # For cleanup
    "scheme_name": "...",     # For filtering
    "embedding_model": "..."  # For compatibility
}
```

### 3. Monitor Collection Sizes

```bash
# Check collection sizes
python -m phases.phase_4_3_indexing --mode verify

# Look for unexpected drops in document count
```

### 4. Test Rollback Periodically

```bash
# In staging environment:
python -m phases.phase_4_3_indexing --mode rollback

# Verify previous version is active
python -m phases.phase_4_3_indexing --mode verify
```

---

## Files

| File | Purpose |
|---|---|
| `indexer.py` | IndexerService implementation |
| `main.py` | Pipeline orchestrator + CLI |
| `README.md` | This documentation |

---

## Next Steps

After indexing, chunks are available for:
- **Phase 6.0 (Retriever)** → Semantic search at query time
- **Flask Backend** → Active collection resolution
- **Quality Verification** → Golden query testing

See [architecture.md](../../docs/architecture.md) for full pipeline details.
