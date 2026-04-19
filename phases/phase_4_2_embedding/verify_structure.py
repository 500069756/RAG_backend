"""
Quick verification script for Phase 4.2 structure
"""

import sys
from pathlib import Path

print("=" * 70)
print("PHASE 4.2 — STRUCTURE VERIFICATION")
print("=" * 70)
print()

# Check directory structure
phase42_dir = Path(__file__).parent

print("✅ Phase 4.2 Directory:")
print(f"   {phase42_dir}")
print()

# Check files
required_files = {
    "__init__.py": "Module initialization",
    "embedder.py": "EmbeddingService implementation",
    "main.py": "Pipeline orchestrator + CLI",
    "README.md": "Documentation"
}

print("📁 Required Files:")
all_ok = True
for filename, description in required_files.items():
    filepath = phase42_dir / filename
    if filepath.exists():
        size = filepath.stat().st_size
        print(f"   ✅ {filename:25} ({size:>6,} bytes) - {description}")
    else:
        print(f"   ❌ {filename:25} MISSING - {description}")
        all_ok = False

print()

# Check imports
print("🔍 Module Imports:")
try:
    sys.path.insert(0, str(phase42_dir.parent.parent))
    from phases.phase_4_2_embedding import EmbeddingService
    print("   ✅ EmbeddingService imported successfully")
except Exception as e:
    print(f"   ❌ Failed to import EmbeddingService: {e}")
    all_ok = False

try:
    from phases.phase_4_2_embedding.embedder import EmbeddingStats
    print("   ✅ EmbeddingStats dataclass imported")
except Exception as e:
    print(f"   ❌ Failed to import EmbeddingStats: {e}")
    all_ok = False

print()

# Check class structure
print("🏗️  EmbeddingService Class Structure:")
try:
    # Check required methods
    required_methods = [
        "__init__",
        "_cache_key",
        "_load_cache",
        "_save_cache",
        "_get_cached",
        "_set_cached",
        "_call_hf_api",
        "_validate_embedding",
        "embed_single",
        "embed_chunks",
        "clear_cache"
    ]

    for method in required_methods:
        if hasattr(EmbeddingService, method):
            print(f"   ✅ {method}()")
        else:
            print(f"   ❌ {method}() MISSING")
            all_ok = False

    # Check class attributes
    expected_attrs = {
        "DEFAULT_MODEL": "BAAI/bge-small-en-v1.5",
        "BATCH_SIZE": 32,
        "MAX_RETRIES": 3
    }

    print()
    print("⚙️  Class Attributes:")
    for attr, expected_value in expected_attrs.items():
        actual_value = getattr(EmbeddingService, attr, None)
        if actual_value == expected_value:
            print(f"   ✅ {attr} = {actual_value}")
        else:
            print(f"   ❌ {attr} = {actual_value} (expected {expected_value})")
            all_ok = False

except Exception as e:
    print(f"   ❌ Error checking class structure: {e}")
    all_ok = False

print()

# Check data directory structure
print("📂 Data Directory Structure:")
data_dirs = {
    "data/chunks/": "Input chunks from Phase 4.1",
    "data/embedded/": "Output embedded chunks",
    "data/embeddings_cache/": "Embedding cache"
}

for dir_path, description in data_dirs.items():
    full_path = phase42_dir.parent.parent / dir_path
    if full_path.exists():
        print(f"   ✅ {dir_path:30} - {description}")
    else:
        print(f"   ⚠️  {dir_path:30} - Will be created on first run")

print()

# Summary
print("=" * 70)
if all_ok:
    print("✅ PHASE 4.2 VERIFICATION PASSED")
    print()
    print("Next steps:")
    print("  1. Set HF_API_TOKEN in .env file")
    print("  2. Run: python -m phases.phase_4_2_embedding --mode embed")
    print("  3. Check output in data/embedded/embedded_chunks.json")
else:
    print("❌ PHASE 4.2 VERIFICATION FAILED")
    print("   Please fix the issues above before proceeding.")
print("=" * 70)
