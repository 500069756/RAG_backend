"""
Quick verification script for Phase 4.0 structure
Doesn't require all dependencies to be installed.
"""

import sys
from pathlib import Path

print("=" * 70)
print("PHASE 4.0 — STRUCTURE VERIFICATION")
print("=" * 70)
print()

# Check directory structure
phase4_dir = Path(__file__).parent

print("✅ Phase 4.0 Directory:")
print(f"   {phase4_dir}")
print()

# Check files
required_files = {
    "__init__.py": "Module initialization",
    "scraper.py": "ScraperService implementation",
    "preprocessor.py": "PreprocessorService implementation",
    "main.py": "Pipeline orchestrator + CLI",
    "README.md": "Documentation",
    "test_phase4.py": "Test suite"
}

print("📁 Required Files:")
all_ok = True
for filename, description in required_files.items():
    filepath = phase4_dir / filename
    if filepath.exists():
        size = filepath.stat().st_size
        print(f"   ✅ {filename:25} ({size:>6,} bytes) - {description}")
    else:
        print(f"   ❌ {filename:25} MISSING - {description}")
        all_ok = False

print()

# Check data directories
print("📂 Data Directories:")
data_dirs = [
    Path("data/scraped"),
    Path("data/chunks"),
    Path("data/embeddings_cache")
]

for dir_path in data_dirs:
    if dir_path.exists():
        print(f"   ✅ {dir_path}")
    else:
        print(f"   ⚠️  {dir_path} (will be created on first run)")

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
    
    # Show sample
    print(f"\n   Sample sources:")
    for source in sources[:3]:
        print(f"     - {source['id']:30} ({source['type']:10}) {source['scheme']}")
else:
    print(f"   ❌ {sources_path} NOT FOUND")

print()

# Check .env file
print("🔑 Environment Configuration:")
env_file = Path(".env")
if env_file.exists():
    print(f"   ✅ {env_file} exists")
    # Check if it has placeholders
    with open(env_file, 'r') as f:
        content = f.read()
    if "gsk_" in content and "ck_" in content:
        print(f"   ⚠️  Contains placeholder keys - needs to be configured")
    else:
        print(f"   ✅ API keys appear to be configured")
else:
    print(f"   ⚠️  {env_file} not found (copy from .env.example)")

print()
print("=" * 70)

if all_ok:
    print("✅ Phase 4.0 structure is complete and ready!")
    print()
    print("Next steps:")
    print("  1. Install dependencies: pip install -r requirements.txt")
    print("  2. Configure .env file with your API keys")
    print("  3. Test run: python -m phases.phase_4_scheduler --mode scrape")
else:
    print("❌ Some files are missing. Please check the output above.")

print("=" * 70)
