# Phase 4.0 — Scheduler & Scraping Service

Daily automated data ingestion pipeline that fetches, scrapes, and preprocesses content from official mutual fund sources.

---

## Overview

Phase 4.0 is the **data acquisition layer** of the RAG pipeline. It runs daily at **9:15 AM IST** via GitHub Actions to ensure the corpus stays synchronized with official source updates.

### What It Does

1. **Loads** source URLs from the corpus registry (`sources.json`)
2. **Scrapes** HTML pages and PDF documents with intelligent retry logic
3. **Detects** content changes via SHA-256 hashing (skips unchanged sources)
4. **Extracts** clean text using format-specific parsers
5. **Preprocesses** text to remove boilerplate, normalize whitespace, and fix encoding
6. **Outputs** clean text ready for Phase 5 (Chunking & Embedding)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 4.0 PIPELINE                               │
│                                                                     │
│  sources.json ──▶ Scraper ──▶ Raw Text ──▶ Preprocessor ──▶ Clean  │
│   (URLs)        Service       (.txt)        Service        Text     │
│                                                                     │
│  ┌────────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐           │
│  │ HTML Pages │─▶│ BS4/     │─▶│ .txt   │─▶│ Clean    │           │
│  │            │  │ Trafil.  │  │ files  │  │ & Normalize│          │
│  └────────────┘  └──────────┘  └────────┘  └──────────┘           │
│  ┌────────────┐  ┌──────────┐                                     │
│  │ PDF Files  │─▶│ PyMuPDF  │                                     │
│  │            │  │          │                                     │
│  └────────────┘  └──────────┘                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Scraper Service (`scraper.py`)

**Purpose:** Fetch and extract text from registered URLs

**Features:**
- ✅ Multi-format support (HTML, PDF)
- ✅ SHA-256 content hash for change detection
- ✅ Exponential backoff retry logic (handles 429, 500 errors)
- ✅ Rate limiting (polite crawling)
- ✅ Individual file output per source
- ✅ Run summary and statistics

**Parsers:**
- **HTML:** Trafilatura (preferred) → BeautifulSoup (fallback)
- **PDF:** PyMuPDF (fitz) for page-by-page extraction

**Configuration:**
| Setting | Value | Rationale |
|---|---|---|
| Request Timeout | 30 seconds | Handles slow AMC servers |
| Rate Limit Delay | 2 seconds | Respectful crawling |
| Max Retries | 3 with backoff (2s, 5s, 10s) | Handles transient errors |
| Max PDF Size | 50 MB | Skips oversized documents |
| Min Content Length | 50 characters | Rejects empty responses |

### 2. Preprocessor Service (`preprocessor.py`)

**Purpose:** Clean and normalize raw scraped text

**Features:**
- ✅ Fix encoding issues (mojibake, smart quotes) via `ftfy`
- ✅ Remove residual HTML tags and entities
- ✅ Strip boilerplate content (copyright, navigation, etc.)
- ✅ Normalize whitespace and line breaks
- ✅ Content validation (minimum length, alpha ratio)
- ✅ Reduction statistics

**Cleaning Pipeline:**
```
Raw Text → Fix Encoding → Remove HTML → Decode Entities → 
Remove Boilerplate → Normalize Whitespace → Validate → Clean Text
```

### 3. Main Pipeline (`main.py`)

**Purpose:** Orchestrate scraping + preprocessing

**Modes:**
- `full` (default): Scrape → Preprocess
- `scrape`: Only scrape sources
- `preprocess`: Only preprocess existing raw text

---

## Usage

### Prerequisites

Install required packages:
```bash
pip install -r requirements.txt
```

### Command-Line Interface

#### Full Pipeline (Scrape + Preprocess)
```bash
cd backend

# Run complete pipeline
python -m phases.phase_4_scheduler --mode full

# Force re-scrape all sources (ignore content hash)
python -m phases.phase_4_scheduler --mode full --force

# Verbose logging
python -m phases.phase_4_scheduler --mode full --verbose
```

#### Scrape Only
```bash
# Scrape sources and save raw text
python -m phases.phase_4_scheduler --mode scrape

# Custom sources file and output directory
python -m phases.phase_4_scheduler \
  --mode scrape \
  --sources phases/phase_1_corpus/sources.json \
  --scraped-dir data/scraped/
```

#### Preprocess Only
```bash
# Preprocess existing raw text files
python -m phases.phase_4_scheduler --mode preprocess

# Custom directories
python -m phases.phase_4_scheduler \
  --mode preprocess \
  --input data/scraped/ \
  --output data/scraped/
```

### Programmatic Usage

```python
from phases.phase_4_scheduler import Phase4Pipeline

# Initialize pipeline
pipeline = Phase4Pipeline(
    sources_path="phases/phase_1_corpus/sources.json",
    scraped_dir="data/scraped/",
    cleaned_dir="data/scraped/",
    force=False  # Set True to re-scrape everything
)

# Run full pipeline
stats = pipeline.run_full_pipeline()

print(f"Scraped: {stats['scraped_count']}")
print(f"Preprocessed: {stats['preprocessed_count']}")
print(f"Failed: {stats['failed_count']}")
```

---

## File Structure

```
backend/phases/phase_4_scheduler/
├── __init__.py           # Module exports
├── scraper.py            # ScraperService class
├── preprocessor.py       # PreprocessorService class
├── main.py              # Phase4Pipeline orchestrator + CLI
└── README.md            # This file

backend/data/scraped/
├── {source_id}.txt              # Raw scraped text
├── {source_id}.meta.json        # Source metadata
├── {source_id}.clean.txt        # Preprocessed text (output)
├── summary.json                 # Run summary
└── pipeline_summary.json        # Pipeline execution summary
```

---

## Output Files

### Scraped Text (`data/scraped/{source_id}.txt`)
Raw extracted text from the source URL.

### Metadata (`data/scraped/{source_id}.meta.json`)
```json
{
  "id": "hdfc-top100-factsheet",
  "url": "https://www.hdfcfund.com/...",
  "type": "factsheet",
  "scheme": "HDFC Top 100 Fund",
  "category": "large-cap",
  "last_scraped": "2026-04-19T09:15:00+00:00",
  "content_hash": "abc123..."
}
```

### Clean Text (`data/scraped/{source_id}.clean.txt`)
Preprocessed text ready for chunking in Phase 5.

### Run Summary (`data/scraped/summary.json`)
```json
{
  "run_timestamp": "2026-04-19T09:15:00+00:00",
  "total_sources": 16,
  "scraped": 5,
  "skipped_unchanged": 10,
  "failed": 1,
  "duration_seconds": 45.2,
  "force_mode": false
}
```

---

## Change Detection

The scraper uses **SHA-256 content hashing** to avoid re-processing unchanged sources:

1. **First Run:** Scrape all sources, compute hash, save to `sources.json`
2. **Subsequent Runs:**
   - Scrape source → Extract text → Compute new hash
   - Compare with stored hash
   - **If same:** Skip (log as "unchanged")
   - **If different:** Save new text, update hash

**Benefits:**
- ⚡ Faster daily runs (only process changed sources)
- 💾 Reduced API calls and server load
- 📊 Accurate tracking of source update frequency

**Override with `--force`:** Re-scrape all sources regardless of hash.

---

## GitHub Actions Integration

Automated daily run via GitHub Actions (`.github/workflows/daily-sync.yml`):

```yaml
- name: Phase 4.0 — Scrape & Preprocess
  run: |
    cd backend
    python -m phases.phase_4_scheduler --mode full
  env:
    # No secrets needed for scraping (public URLs)
```

**Schedule:** Daily at 9:15 AM IST (3:45 AM UTC)

---

## Troubleshooting

### Issue: "Sources file not found"
**Solution:** Ensure `sources.json` exists at the specified path:
```bash
ls phases/phase_1_corpus/sources.json
```

### Issue: "No .txt files found"
**Solution:** Run scraping first before preprocessing:
```bash
python -m phases.phase_4_scheduler --mode scrape
```

### Issue: "PDF extraction failed"
**Solution:** Check if PyMuPDF is installed:
```bash
pip install PyMuPDF
```

### Issue: "Connection timeout"
**Solution:** The scraper already retries 3 times with backoff. If persistent:
- Check internet connection
- Verify source URL is accessible
- Increase `REQUEST_TIMEOUT` in `scraper.py`

### Issue: "Content too short after cleaning"
**Solution:** Source may have minimal text or be image-heavy. The preprocessor rejects content < 100 chars or low alpha ratio.

---

## Next Steps

After Phase 4.0 completes, the clean text files are passed to:

**Phase 5.0 — Ingestion Pipeline:**
1. **Chunking:** Split clean text into semantic chunks
2. **Embedding:** Convert chunks to vectors via HuggingFace API
3. **Indexing:** Upsert vectors to Chroma Cloud
4. **Verification:** Validate index quality

```bash
# Phase 5.0 pipeline
python -m phases.phase_5_ingestion.chunker --input data/scraped/
python -m phases.phase_5_ingestion.embedder --input data/chunks/
python -m phases.phase_5_ingestion.indexer --chunks data/embedded/
```

---

## Configuration Reference

### ScraperService Parameters
| Parameter | Default | Description |
|---|---|---|
| `sources_path` | `data/sources.json` | Path to source URL manifest |
| `output_dir` | `data/scraped/` | Directory for output files |
| `force` | `False` | Force re-scrape all sources |
| `REQUEST_TIMEOUT` | 30 | Seconds per HTTP request |
| `RATE_LIMIT_DELAY` | 2.0 | Seconds between requests |
| `MAX_RETRIES` | 3 | Retry count per URL |
| `MAX_PDF_SIZE_MB` | 50 | Max PDF size to process |
| `MIN_CONTENT_LENGTH` | 50 | Min chars to accept |

### PreprocessorService Parameters
| Parameter | Default | Description |
|---|---|---|
| `min_content_length` | 100 | Min chars after cleaning |
| `ftfy` | auto-installed | Encoding fix library |

---

## Performance Metrics

Typical run statistics (16 sources):
- **All unchanged:** ~5 seconds (hash check only)
- **3-5 changed:** ~30-60 seconds (scrape + preprocess)
- **All changed (force):** ~2-3 minutes

---

## Best Practices

1. **Run daily via cron** to keep corpus fresh
2. **Monitor `summary.json`** for failed sources
3. **Use `--force` sparingly** (only when sources.json is corrupted)
4. **Check logs** for rate limiting or connection issues
5. **Add new sources** to `sources.json` before running

---

## References

- **Architecture:** [docs/architecture.md](../../docs/architecture.md) — Section 4.3
- **Sources Registry:** [phases/phase_1_corpus/sources.json](../phase_1_corpus/sources.json)
- **Phase 5 (Ingestion):** [phases/phase_5_ingestion/](../phase_5_ingestion/)
- **GitHub Actions:** [.github/workflows/daily-sync.yml](../../.github/workflows/daily-sync.yml)
