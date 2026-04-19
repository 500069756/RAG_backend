"""
Test script for Phase 4.0 — Scheduler & Scraping Service

Run this to verify all components are working correctly:
    python phases/phase_4_scheduler/test_phase4.py
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

def test_imports():
    """Test that all modules can be imported."""
    print("=" * 60)
    print("TEST 1: Module Imports")
    print("=" * 60)
    
    try:
        from phases.phase_4_scheduler import ScraperService
        print("✅ ScraperService imported")
    except Exception as e:
        print(f"❌ Failed to import ScraperService: {e}")
        return False
    
    try:
        from phases.phase_4_scheduler import PreprocessorService
        print("✅ PreprocessorService imported")
    except Exception as e:
        print(f"❌ Failed to import PreprocessorService: {e}")
        return False
    
    try:
        from phases.phase_4_scheduler import Phase4Pipeline
        print("✅ Phase4Pipeline imported")
    except Exception as e:
        print(f"❌ Failed to import Phase4Pipeline: {e}")
        return False
    
    print()
    return True


def test_dependencies():
    """Test that required packages are installed."""
    print("=" * 60)
    print("TEST 2: Required Dependencies")
    print("=" * 60)
    
    dependencies = {
        "requests": "HTTP requests",
        "bs4": "HTML parsing",
        "fitz": "PDF extraction (PyMuPDF)",
    }
    
    optional_deps = {
        "trafilatura": "Advanced HTML extraction",
        "ftfy": "Text encoding fixes",
    }
    
    all_ok = True
    
    for module, description in dependencies.items():
        try:
            __import__(module)
            print(f"✅ {module} ({description})")
        except ImportError:
            print(f"❌ {module} ({description}) - REQUIRED")
            all_ok = False
    
    print("\nOptional Dependencies:")
    for module, description in optional_deps.items():
        try:
            __import__(module)
            print(f"✅ {module} ({description})")
        except ImportError:
            print(f"⚠️  {module} ({description}) - optional but recommended")
    
    print()
    return all_ok


def test_sources_file():
    """Test that sources.json exists and is valid."""
    print("=" * 60)
    print("TEST 3: Sources Registry")
    print("=" * 60)
    
    sources_path = backend_dir / "phases" / "phase_1_corpus" / "sources.json"
    
    if not sources_path.exists():
        print(f"❌ Sources file not found: {sources_path}")
        return False
    
    print(f"✅ Sources file found: {sources_path}")
    
    import json
    with open(sources_path, 'r') as f:
        data = json.load(f)
    
    sources = data.get("sources", [])
    print(f"✅ Loaded {len(sources)} sources")
    
    # Validate structure
    required_fields = ["id", "url", "type", "scheme", "category"]
    for source in sources[:3]:  # Check first 3
        for field in required_fields:
            if field not in source:
                print(f"❌ Source '{source.get('id', 'unknown')}' missing field: {field}")
                return False
    
    print(f"✅ Source structure validated")
    print()
    return True


def test_scraper_instantiation():
    """Test that ScraperService can be instantiated."""
    print("=" * 60)
    print("TEST 4: ScraperService Instantiation")
    print("=" * 60)
    
    try:
        from phases.phase_4_scheduler import ScraperService
        
        scraper = ScraperService(
            sources_path="phases/phase_1_corpus/sources.json",
            output_dir="data/scraped/",
            force=False
        )
        print(f"✅ ScraperService instantiated successfully")
        print(f"   Sources loaded: {len(scraper.sources)}")
        print(f"   Output directory: {scraper.output_dir}")
        print()
        return True
    except Exception as e:
        print(f"❌ Failed to instantiate ScraperService: {e}")
        print()
        return False


def test_preprocessor_instantiation():
    """Test that PreprocessorService can be instantiated."""
    print("=" * 60)
    print("TEST 5: PreprocessorService Instantiation")
    print("=" * 60)
    
    try:
        from phases.phase_4_scheduler import PreprocessorService
        
        preprocessor = PreprocessorService()
        print(f"✅ PreprocessorService instantiated successfully")
        print(f"   Min content length: {preprocessor.min_content_length}")
        print()
        return True
    except Exception as e:
        print(f"❌ Failed to instantiate PreprocessorService: {e}")
        print()
        return False


def test_pipeline_instantiation():
    """Test that Phase4Pipeline can be instantiated."""
    print("=" * 60)
    print("TEST 6: Phase4Pipeline Instantiation")
    print("=" * 60)
    
    try:
        from phases.phase_4_scheduler import Phase4Pipeline
        
        pipeline = Phase4Pipeline(
            sources_path="phases/phase_1_corpus/sources.json",
            scraped_dir="data/scraped/",
            cleaned_dir="data/scraped/",
            force=False
        )
        print(f"✅ Phase4Pipeline instantiated successfully")
        print(f"   Sources: {pipeline.sources_path}")
        print(f"   Scraped dir: {pipeline.scraped_dir}")
        print()
        return True
    except Exception as e:
        print(f"❌ Failed to instantiate Phase4Pipeline: {e}")
        print()
        return False


def test_preprocessor_functionality():
    """Test preprocessor text cleaning."""
    print("=" * 60)
    print("TEST 7: Preprocessor Functionality")
    print("=" * 60)
    
    try:
        from phases.phase_4_scheduler import PreprocessorService
        
        preprocessor = PreprocessorService()
        
        # Test with sample text containing HTML and encoding issues
        test_text = """
        <html>
        <body>
            <nav>Navigation Menu</nav>
            <h1>Hello World &amp; Friends</h1>
            <p>This is a   test   with   multiple   spaces.</p>
            <footer>Copyright 2026</footer>
        </body>
        </html>
        """
        
        cleaned = preprocessor.clean_text(test_text)
        
        if not cleaned:
            print("❌ Preprocessor returned empty text")
            return False
        
        # Check that HTML tags are removed
        if "<html>" in cleaned or "<body>" in cleaned:
            print("❌ HTML tags not removed")
            return False
        
        # Check that entities are decoded
        if "&amp;" in cleaned:
            print("❌ HTML entities not decoded")
            return False
        
        print(f"✅ Text preprocessing works correctly")
        print(f"   Input length: {len(test_text)} chars")
        print(f"   Output length: {len(cleaned)} chars")
        print(f"   Sample output: {cleaned[:100]}...")
        print()
        return True
        
    except Exception as e:
        print(f"❌ Preprocessor test failed: {e}")
        print()
        return False


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "PHASE 4.0 — COMPONENT TESTS" + " " * 19 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    tests = [
        ("Module Imports", test_imports),
        ("Dependencies", test_dependencies),
        ("Sources Registry", test_sources_file),
        ("ScraperService", test_scraper_instantiation),
        ("PreprocessorService", test_preprocessor_instantiation),
        ("Phase4Pipeline", test_pipeline_instantiation),
        ("Preprocessor Logic", test_preprocessor_functionality),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"❌ Test '{name}' crashed: {e}\n")
            results[name] = False
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} — {name}")
    
    print()
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Phase 4.0 is ready to use.")
        print("\nNext steps:")
        print("  1. Run scraper: python -m phases.phase_4_scheduler --mode scrape")
        print("  2. Run full pipeline: python -m phases.phase_4_scheduler --mode full")
        print("  3. Check output: ls data/scraped/")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
