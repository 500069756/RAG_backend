# Phase 4.1 — Chunking Service

Splits scraped text into semantically meaningful chunks with enriched metadata for embedding and retrieval.

---

## Overview

Phase 4.1 is the **granularity layer** of the RAG pipeline. It transforms raw scraped text into optimized chunks that preserve semantic context while fitting within embedding model limits.

### Why Chunking Matters

Poor chunking directly degrades retrieval quality. Good chunking:
- ✅ Preserves semantic completeness (Q&A pairs stay together)
- ✅ Respects document structure (pages, paragraphs, sections)
- ✅ Optimizes for embedding model limits (~500 tokens)
- ✅ Enables precise retrieval (not too broad, not too narrow)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 4.1 CHUNKING PIPELINE                      │
│                                                                     │
│  Scraped Text ──▶ Document Type Detection ──▶ Strategy Selection   │
│                                                                     │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐                       │
│  │Factsheets  │  │ SID/KIM  │  │   FAQ    │                       │
│  │ (500 tok)  │  │(800 tok) │  │(QA-pair) │                       │
│  └─────┬──────┘  └────┬─────┘  └────┬─────┘                       │
│        │               │            │                               │
│        └───────────────┼────────────┘                               │
│                        ▼                                             │
│              Metadata Enrichment                                     │
│              (source, scheme, category)                              │
│                        ▼                                             │
│              Quality Validation                                      │
│              (min/max length, content check)                         │
│                        ▼                                             │
│              Output: List of Enriched Chunks                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Document-Type-Aware Splitting

Different document types have different structures. We use specialized strategies:

| Document Type | Chunk Size | Overlap | Separators | Rationale |
|---|---|---|---|---|
| **Factsheet (HTML)** | 500 tokens | 50 tokens | `["\n\n", "\n", ". ", " "]` | Short factual paragraphs; keep expense ratio, NAV together |
| **Factsheet (PDF)** | 500 tokens | 50 tokens | `["--- Page", "\n\n", "\n", ". "]` | Respect page boundaries from PDF extraction |
| **SID / KIM (PDF)** | 800 tokens | 100 tokens | `["--- Page", "\n\n", "\n", ". "]` | Longer legal sections need more context |
| **FAQ Pages** | QA-pair based | 0 (no overlap) | Split on Q&A boundaries | Each Q&A pair = 1 chunk (semantic completeness) |
| **Guides** | 400 tokens | 40 tokens | `["\n\n", "\n", ". ", " "]` | Step-by-step instructions; smaller chunks |

---

## Components

### 1. Chunk Dataclass

Every chunk carries rich metadata for filtered retrieval and citation:

```python
@dataclass
class Chunk:
    chunk_id: str          # Unique ID: {source_id}-chunk-{NNN}
    text: str              # Chunk content
    source_id: str         # Links to sources.json
    source_url: str        # Citation URL
    scheme_name: str       # For metadata filtering
    document_type: str     # factsheet | sid | kim | faq | guide
    category: str          # large-cap | flexi-cap | elss | debt | index
    scraped_at: str        # ISO 8601 timestamp
    chunk_index: int       # Position within source
    total_chunks: int      # Total chunks from this source
    token_count: int       # Approximate token count
    content_hash: str      # SHA-256 for deduplication
```

### 2. SplitterConfig

Configuration for each document type:

```python
@dataclass
class SplitterConfig:
    chunk_size: int         # Target chunk size (tokens)
    chunk_overlap: int      # Overlap between chunks (tokens)
    separators: list[str]   # Splitting boundaries (priority order)
    is_qa_mode: bool        # Use QA-aware splitting
```

### 3. ChunkingService

Main service class with methods:
- `chunk_source(source, text)` — Chunk a single source
- `chunk_all(scraped_results)` — Chunk all sources
- `_split_qa_content(text)` — FAQ-specific splitting
- `_split_standard(text, config)` — Recursive character splitting
- `_validate_chunk(text)` — Quality validation

---

## Usage

### Command-Line Interface

```bash
cd backend

# Chunk all scraped files
python -m phases.phase_4_1_chunking --mode chunk

# Custom paths
python -m phases.phase_4_1_chunking \
    --input data/scraped/ \
    --output data/chunks/ \
    --sources phases/phase_1_corpus/sources.json

# Verbose logging
python -m phases.phase_4_1_chunking --mode chunk --verbose
```

### Programmatic Usage

```python
from phases.phase_4_1_chunking import ChunkingService

# Initialize chunker
chunker = ChunkingService(output_dir="data/chunks/")

# Chunk a single source
source = {
    "id": "hdfc-top100-factsheet",
    "url": "https://www.hdfcfund.com/...",
    "type": "factsheet",
    "scheme": "HDFC Top 100 Fund",
    "category": "large-cap",
    "last_scraped": "2026-04-19T09:15:00+00:00"
}
text = "Raw scraped text..."

chunks = chunker.chunk_source(source, text)
print(f"Created {len(chunks)} chunks")

# Chunk all sources
scraped_results = [
    {"source": source1, "text": text1},
    {"source": source2, "text": text2}
]
all_chunks = chunker.chunk_all(scraped_results)
```

---

## Chunk Quality Validation

Chunks must pass these validation rules:

| Rule | Threshold | Action |
|---|---|---|
| **Minimum length** | >= 30 characters | Discard (too small) |
| **Maximum length** | <= 3000 characters (~750 tokens) | Log warning |
| **Page marker only** | Matches `Page N` pattern | Discard |
| **No alphabetic content** | No 3+ letter word | Discard (noise) |
| **Duplicate hash** | Same SHA-256 as existing | Deduplicate |

---

## Metadata Schema

Example chunk with full metadata:

```json
{
  "chunk_id": "hdfc-top100-factsheet-chunk-003",
  "text": "The expense ratio of HDFC Top 100 Fund (Direct Plan) is 1.04%...",
  "source_id": "hdfc-top100-factsheet",
  "source_url": "https://www.hdfcfund.com/mutual-fund/equity/hdfc-top-100",
  "scheme_name": "HDFC Top 100 Fund",
  "document_type": "factsheet",
  "category": "large-cap",
  "scraped_at": "2026-04-19T09:15:00Z",
  "chunk_index": 3,
  "total_chunks": 12,
  "token_count": 128,
  "content_hash": "a3f2b8c1d9e04567"
}
```

**Why This Matters:**
- `source_url` → Powers source citations in responses
- `scheme_name` → Enables metadata-filtered retrieval
- `scraped_at` → "Last updated from sources: <date>" footer
- `chunk_index` + `total_chunks` → Completeness tracking
- `content_hash` → Deduplication and cache keying

---

## File Structure

```
backend/phases/phase_4_1_chunking/
├── __init__.py           # Module exports
├── chunker.py            # ChunkingService implementation
├── main.py              # Pipeline orchestrator + CLI
└── README.md            # This file

backend/data/chunks/
├── chunks.json                  # Output: All chunks with metadata
└── chunking_summary.json        # Pipeline execution summary
```

---

## Output

### chunks.json

Contains all chunks from all sources:

```json
[
  {
    "chunk_id": "hdfc-top100-factsheet-chunk-000",
    "text": "HDFC Top 100 Fund - Direct Plan\nCategory: Large Cap Fund...",
    "source_id": "hdfc-top100-factsheet",
    "source_url": "https://www.hdfcfund.com/...",
    "scheme_name": "HDFC Top 100 Fund",
    "document_type": "factsheet",
    "category": "large-cap",
    "scraped_at": "2026-04-19T09:15:00Z",
    "chunk_index": 0,
    "total_chunks": 12,
    "token_count": 120,
    "content_hash": "abc123..."
  },
  // ... more chunks
]
```

### chunking_summary.json

```json
{
  "started_at": "2026-04-19T09:16:00Z",
  "completed_at": "2026-04-19T09:16:05Z",
  "files_loaded": 16,
  "chunks_created": 245,
  "chunks_discarded": 12
}
```

---

## Splitting Strategies

### 1. Standard Recursive Splitting

For factsheets, SID, KIM, and guides:

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=2000,        # 500 tokens * 4 chars/token
    chunk_overlap=200,      # 50 tokens * 4 chars/token
    separators=["\n\n", "\n", ". ", " "],
    length_function=len
)
chunks = splitter.split_text(text)
```

**How it works:**
1. Try splitting on `\n\n` (paragraphs)
2. If chunk too large, split on `\n` (lines)
3. If still too large, split on `. ` (sentences)
4. Finally split on ` ` (words)

### 2. QA-Aware Splitting (FAQ Pages)

For FAQ documents:

```python
def _split_qa_content(self, text: str) -> list[str]:
    # Detect question patterns:
    # - "Q: ..." or "Question: ..."
    # - "**What is...?**"
    # - "1. How do I...?"
    # - Lines ending with "?"
    
    qa_pattern = re.compile(
        r'(?:^|\n)(?:Q[:.\s]|\d+[.)\s]|\*\*.*\?\*\*|.*\?\s*$)',
        re.MULTILINE | re.IGNORECASE
    )
    
    # Split on question boundaries
    # Recombine question + answer as single chunk
```

**Example:**

Input:
```
Q: What is the expense ratio?
A: The expense ratio is 1.04% for Direct Plan.

Q: What is the minimum SIP amount?
A: Minimum SIP is Rs 500.
```

Output:
```
Chunk 1: "Q: What is the expense ratio?\nA: The expense ratio is 1.04%..."
Chunk 2: "Q: What is the minimum SIP amount?\nA: Minimum SIP is Rs 500."
```

---

## Integration with Pipeline

### Input
- **From Phase 4.0:** `data/scraped/*.txt` or `*.clean.txt` (scraped text)
- **From Phase 1.0:** `phases/phase_1_corpus/sources.json` (source metadata)

### Output
- **To Phase 5.0:** `data/chunks/chunks.json` (enriched chunks)

### Pipeline Flow
```
Phase 4.0 (Scraping + Preprocessing)
    ↓ *.txt / *.clean.txt
Phase 4.1 (Chunking) ← This phase
    ↓ chunks.json
Phase 5.0 (Embedding → Indexing)
    ↓ vectors
Chroma Cloud
```

---

## Performance Metrics

Typical run statistics:

| Input | Output | Duration |
|---|---|---|
| 16 sources (~50K chars) | ~250 chunks | ~2-5 seconds |

**Chunk distribution:**
- Factsheets: 10-15 chunks each
- SID/KIM: 20-30 chunks each
- FAQ pages: 1 chunk per Q&A pair
- Guides: 5-10 chunks each

---

## Troubleshooting

### Issue: "No .txt files found"
**Solution:** Run Phase 4.0 first to generate scraped files:
```bash
python -m phases.phase_4_scheduler --mode scrape
```

### Issue: "Sources file not found"
**Solution:** Ensure sources.json exists:
```bash
ls phases/phase_1_corpus/sources.json
```

### Issue: "QA splitting failed"
**Solution:** The fallback to standard splitting is automatic. Check logs for warnings.

### Issue: Too many chunks discarded
**Solution:** Check input text quality. Chunks are discarded if:
- Too short (< 30 chars)
- Only page markers
- No alphabetic content

---

## Best Practices

1. **Use clean text** from Phase 4.0 preprocessor for best results
2. **Monitor chunk counts** — sudden drops may indicate scraping issues
3. **Review discarded chunks** in logs to identify quality issues
4. **Test with different chunk sizes** if retrieval quality is poor
5. **Keep Q&A pairs together** — FAQ chunks should be semantically complete

---

## Next Steps

After Phase 4.1 completes, chunks are passed to:

**Phase 5.0 — Embedding & Indexing:**
```bash
# Embed chunks into vectors
python -m phases.phase_5_ingestion.embedder --input data/chunks/

# Index vectors in Chroma Cloud
python -m phases.phase_5_ingestion.indexer --chunks data/embedded/
```

---

## Configuration Reference

### SplitterConfig Values

| Document Type | Chunk Size | Overlap | Separators |
|---|---|---|---|
| factsheet | 500 | 50 | `["\n\n", "\n", ". ", " "]` |
| factsheet_pdf | 500 | 50 | `["--- Page", "\n\n", "\n", ". "]` |
| sid | 800 | 100 | `["--- Page", "\n\n", "\n", ". "]` |
| kim | 800 | 100 | `["--- Page", "\n\n", "\n", ". "]` |
| faq | 500 | 0 | QA-aware mode |
| guide | 400 | 40 | `["\n\n", "\n", ". ", " "]` |
| default | 500 | 50 | `["\n\n", "\n", ". ", " "]` |

### ChunkingService Parameters

| Parameter | Default | Description |
|---|---|---|
| `output_dir` | `data/chunks/` | Directory to save chunks.json |
| `MIN_CHUNK_LENGTH` | 30 | Minimum chars per chunk |
| `MAX_CHUNK_LENGTH` | 3000 | Maximum chars per chunk |

---

## References

- **Architecture:** [docs/architecture.md](../../docs/architecture.md) — Section 4.4
- **Chunking Details:** [docs/chunking-embedding-architecture.md](../../docs/chunking-embedding-architecture.md)
- **Phase 4.0 (Scraping):** [phases/phase_4_scheduler/](../phase_4_scheduler/)
- **Phase 5.0 (Ingestion):** [phases/phase_5_ingestion/](../phase_5_ingestion/)
