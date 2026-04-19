"""
Quick verification script for Phase 4.3 structure
"""

import sys
from pathlib import Path

print("=" * 70)
print("PHASE 4.3 — STRUCTURE VERIFICATION")
print("=" * 70)
print()

# Check directory structure
phase43_dir = Path(__file__).parent

print("✅ Phase 4.3 Directory:")
print(f"   {phase43_dir}")
print()

# Check files
required_files = {
    "__init__.py": "Module initialization",
    "indexer.py": "IndexerService implementation",
    "main.py": "Pipeline orchestrator + CLI",
    "README.md": "Documentation"
}

print("📁 Required Files:")
all_ok = True
for filename, description in required_files.items():
    filepath = phase43_dir / filename
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
    sys.path.insert(0, str(phase43_dir.parent.parent))
    from phases.phase_4_3_indexing import IndexerService
    print("   ✅ IndexerService imported successfully")
except Exception as e:
    print(f"   ❌ Failed to import IndexerService: {e}")
    all_ok = False

try:
    from phases.phase_4_3_indexing.indexer import IndexerStats
    print("   ✅ IndexerStats dataclass imported")
except Exception as e:
    print(f"   ❌ Failed to import IndexerStats: {e}")
    all_ok = False

print()

# Check class structure
print("🏗️  IndexerService Class Structure:")
try:
    # Check required methods
    required_methods = [
        "__init__",
        "_versioned_name",
        "_list_versions",
        "_get_active_collection_name",
        "create_collection",
        "get_active_collection",
        "delete_by_source_id",
        "upsert_chunks",
        "promote_collection",
        "rollback",
        "cleanup_old_versions",
        "verify_collection"
    ]

    for method in required_methods:
        if hasattr(IndexerService, method):
            print(f"   ✅ {method}()")
        else:
            print(f"   ❌ {method}() MISSING")
            all_ok = False

    # Check class attributes
    expected_attrs = {
        "BASE_COLLECTION": "mutual_fund_faq",
        "UPSERT_BATCH_SIZE": 100,
        "MAX_VERSIONS_KEEP": 3
    }

    print()
    print("⚙️  Class Attributes:")
    for attr, expected_value in expected_attrs.items():
        actual_value = getattr(IndexerService, attr, None)
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
    "data/embedded/": "Input embedded chunks from Phase 4.2",
    "data/chunks/": "Intermediate chunks from Phase 4.1"
}

for dir_path, description in data_dirs.items():
    full_path = phase43_dir.parent.parent / dir_path
    if full_path.exists():
        print(f"   ✅ {dir_path:30} - {description}")
    else:
        print(f"   ⚠️  {dir_path:30} - Will be created on first run")

print()

# Check Chroma Cloud configuration
print("🌐 Chroma Cloud Configuration:")
try:
    sys.path.insert(0, str(phase43_dir.parent.parent))
    import os
    from pathlib import Path
    
    env_file = phase43_dir.parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            env_content = f.read()
        
        chroma_vars = ["CHROMA_API_KEY", "CHROMA_TENANT", "CHROMA_DATABASE"]
        for var in chroma_vars:
            if var in env_content:
                # Check if it has a value
                for line in env_content.split("\n"):
                    if line.startswith(var + "="):
                        value = line.split("=", 1)[1].strip()
                        if value:
                            print(f"   ✅ {var} = configured")
                        else:
                            print(f"   ⚠️  {var} = empty (needs value)")
                        break
            else:
                print(f"   ❌ {var} = not found in .env")
    else:
        print("   ⚠️  .env file not found")
        
except Exception as e:
    print(f"   ⚠️  Could not check .env: {e}")

print()

# Summary
print("=" * 70)
if all_ok:
    print("✅ PHASE 4.3 VERIFICATION PASSED")
    print()
    print("Next steps:")
    print("  1. Configure Chroma Cloud credentials in .env")
    print("  2. Run Phase 4.2 to create embedded chunks")
    print("  3. Run: python -m phases.phase_4_3_indexing --mode upsert")
    print("  4. Verify: python -m phases.phase_4_3_indexing --mode verify")
else:
    print("❌ PHASE 4.3 VERIFICATION FAILED")
    print("   Please fix the issues above before proceeding.")
print("=" * 70)
