"""
Quick verification script for Phase 4.1 structure
"""

import sys
from pathlib import Path

print("=" * 70)
print("PHASE 4.1 — STRUCTURE VERIFICATION")
print("=" * 70)
print()

# Check directory structure
phase41_dir = Path(__file__).parent

print("✅ Phase 4.1 Directory:")
print(f"   {phase41_dir}")
print()

# Check files
required_files = {
    "__init__.py": "Module initialization",
    "chunker.py": "ChunkingService implementation",
    "main.py": "Pipeline orchestrator + CLI",
    "README.md": "Documentation"
}

print("📁 Required Files:")
all_ok = True
for filename, description in required_files.items():
    filepath = phase41_dir / filename
    if filepath.exists():
        size = filepath.stat().st_size
        print(f"   ✅ {filename:25} ({size:>6,} bytes) - {description}")
    else:
        print(f"   ❌ {filename:25} MISSING - {description}")
        all_ok = False

print()

# Check input directories
print("📂 Input/Output Directories:")
data_dirs = {
    "data/scraped": "Input from Phase 4.0",
    "data/chunks": "Output from Phase 4.1"
}

for dir_path, description in data_dirs.items():
    full_path = Path(dir_path)
    if full_path.exists():
        print(f"   ✅ {dir_path:25} - {description}")
    else:
        print(f"   ⚠️  {dir_path:25} - {description} (will be created)")

print()

# Check sources.json
print("📋 Sources Registry:")
sources_path = Path("phases/phase_1_corpus/sources.json")
if sources_path.exists():
    import json
    with open(sources_path, 'r') as f:
        data = json.load(f)
    sources = data.get("sources", [])
    print(f"   ✅ {sources_path}")
    print(f"   📊 {len(sources)} sources configured")
    
    # Show document types
    doc_types = {}
    for source in sources:
        dtype = source.get('type', 'unknown')
        doc_types[dtype] = doc_types.get(dtype, 0) + 1
    
    print(f"\n   Document types:")
    for dtype, count in sorted(doc_types.items()):
        print(f"     - {dtype:15} {count} source(s)")
else:
    print(f"   ❌ {sources_path} NOT FOUND")

print()

# Check dependencies
print("🔧 Dependencies:")
try:
    import langchain_text_splitters
    print(f"   ✅ langchain-text-splitters installed")
except ImportError:
    print(f"   ❌ langchain-text-splitters NOT INSTALLED")
    print(f"      Install: pip install langchain-text-splitters")
    all_ok = False

print()
print("=" * 70)

if all_ok:
    print("✅ Phase 4.1 structure is complete and ready!")
    print()
    print("Next steps:")
    print("  1. Ensure Phase 4.0 has run: python -m phases.phase_4_scheduler --mode scrape")
    print("  2. Run chunking: python -m phases.phase_4_1_chunking --mode chunk")
    print("  3. Check output: ls data/chunks/")
else:
    print("❌ Some files or dependencies are missing. Please check the output above.")

print("=" * 70)
