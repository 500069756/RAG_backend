"""
Phase 8 — Main Entry Point
Tests and demonstrates the enhanced guardrails and compliance layer.

Usage:
    python phases/phase_8_guardrails/main.py --mode test
    python phases/phase_8_guardrails/main.py --mode analytics
    python phases/phase_8_guardrails/main.py --mode report
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from phases.phase_8_guardrails.compliance_manager import ComplianceManager

logger = logging.getLogger(__name__)


def run_compliance_tests(manager: ComplianceManager):
    """Run comprehensive compliance tests."""
    test_cases = [
        {
            "query": "What is the NAV of HDFC Mid Cap Fund?",
            "expected": "FACTUAL",
            "description": "Factual query - should pass"
        },
        {
            "query": "What is the expense ratio?",
            "expected": "FACTUAL",
            "description": "Factual query - should pass"
        },
        {
            "query": "Should I invest in HDFC Equity Fund?",
            "expected": "ADVISORY",
            "description": "Advisory query - should be BLOCKED"
        },
        {
            "query": "Which fund is better, HDFC or Axis?",
            "expected": "ADVISORY",
            "description": "Comparison query - should be BLOCKED"
        },
        {
            "query": "My PAN is ABCDE1234F, check my investments",
            "expected": "PII_DETECTED",
            "description": "PII query - should be BLOCKED"
        },
        {
            "query": "Call me at 9876543210",
            "expected": "PII_DETECTED",
            "description": "Phone number - should be BLOCKED"
        },
        {
            "query": "Email me at test@example.com",
            "expected": "PII_DETECTED",
            "description": "Email - should be BLOCKED"
        },
        {
            "query": "What is the best fund to invest in?",
            "expected": "ADVISORY",
            "description": "Recommendation query - should be BLOCKED"
        },
    ]

    print("\n" + "="*80)
    print("🧪 Phase 8: Compliance Tests")
    print("="*80)

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"Test {i}/{len(test_cases)}")
        print(f"Query: {test['query']}")
        print(f"Expected: {test['expected']} - {test['description']}")
        print(f"{'='*80}")

        result = manager.validate_query(test['query'], user_session="test_session")

        actual = result['classification']
        status = "✅ PASS" if actual == test['expected'] else "❌ FAIL"

        if actual == test['expected']:
            passed += 1
        else:
            failed += 1

        print(f"\nResult: {actual}")
        print(f"Status: {status}")
        print(f"Is Safe: {result['is_safe']}")
        print(f"Processing Time: {result['processing_time_ms']:.2f}ms")

        if not result['is_safe'] and 'message' in result:
            print(f"\nRefusal Message:")
            print(f"  {result['message']}")

    print(f"\n{'='*80}")
    print(f"📊 Test Results")
    print(f"{'='*80}")
    print(f"Total: {len(test_cases)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    print(f"Success Rate: {passed/len(test_cases)*100:.1f}%")


def test_output_validation(manager: ComplianceManager):
    """Test output guardrail validation."""
    print("\n" + "="*80)
    print("📝 Phase 8: Output Validation Tests")
    print("="*80)

    test_responses = [
        {
            "response": "The expense ratio is 0.95%. The fund size is ₹35,000 Cr. The NAV is ₹152.34.",
            "source_url": "https://example.com",
            "scraped_date": "2026-04-19",
            "description": "Valid response with all required elements"
        },
        {
            "response": "The expense ratio is 0.95%.",
            "source_url": "https://example.com",
            "scraped_date": "2026-04-19",
            "description": "Short response - should add footer"
        },
        {
            "response": "I recommend investing in HDFC Mid Cap Fund because it has good returns. You should definitely buy it.",
            "source_url": "https://example.com",
            "scraped_date": "2026-04-19",
            "description": "Advisory language - should be removed"
        },
    ]

    for i, test in enumerate(test_responses, 1):
        print(f"\n{'='*80}")
        print(f"Output Test {i}")
        print(f"Description: {test['description']}")
        print(f"{'='*80}")
        print(f"\nOriginal Response:")
        print(f"  {test['response']}")

        validation = manager.validate_response(
            test['response'],
            test['source_url'],
            test['scraped_date']
        )

        print(f"\nValidated Response:")
        print(f"  {validation['response']}")
        print(f"\nIssues Fixed: {validation['issues_fixed']}")
        print(f"Valid: {validation['is_valid']}")
        print(f"Sentence Count: {validation['sentence_count']}")

        if validation.get('pii_masked'):
            print(f"PII Masked: {validation.get('pii_type')}")


def run_demo_queries(manager: ComplianceManager):
    """Run demo queries to showcase compliance features."""
    print("\n" + "="*80)
    print("🎬 Phase 8: Demo Queries")
    print("="*80)

    queries = [
        "What is the minimum SIP amount?",
        "Should I invest in mutual funds?",
        "My Aadhaar is 1234 5678 9012",
        "Which fund has the best returns?",
        "What is the NAV of HDFC Large Cap Fund?",
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n{'='*80}")
        print(f"Demo {i}: {query}")
        print(f"{'='*80}")

        result = manager.validate_query(query, user_session="demo_session")

        if result['is_safe']:
            print(f"✅ ALLOWED ({result['classification']})")
            print(f"   Processing time: {result['processing_time_ms']:.2f}ms")
        else:
            print(f"🚫 BLOCKED ({result['classification']})")
            print(f"   Message: {result.get('message', 'N/A')[:100]}...")

    # Show analytics
    print(f"\n{'='*80}")
    print("📊 Analytics After Demo")
    print(f"{'='*80}")
    analytics = manager.get_analytics()
    print(f"Total Queries: {analytics['total_queries']}")
    print(f"Factual: {analytics['factual_queries']}")
    print(f"Advisory Blocked: {analytics['advisory_blocked']}")
    print(f"PII Blocked: {analytics['pii_blocked']}")
    print(f"Block Rate: {analytics['block_rate']:.1f}%")
    print(f"Avg Confidence: {analytics['avg_confidence']:.3f}")


def show_compliance_report(manager: ComplianceManager):
    """Display comprehensive compliance report."""
    print("\n" + "="*80)
    print("📋 Phase 8: Compliance Report")
    print("="*80)

    report = manager.get_compliance_report()

    print(f"\nReport Generated: {report['report_generated_at']}")
    print(f"\n📊 Summary:")
    summary = report['summary']
    print(f"  Total Queries: {summary['total_queries']}")
    print(f"  Factual Queries: {summary['factual_queries']}")
    print(f"  Advisory Blocked: {summary['advisory_blocked']}")
    print(f"  PII Blocked: {summary['pii_blocked']}")
    print(f"  Block Rate: {summary['block_rate']:.1f}%")
    print(f"  Avg Confidence: {summary['avg_confidence']}")
    print(f"  Avg Processing Time: {summary['avg_processing_time_ms']:.2f}ms")

    print(f"\n🔒 Rate Limits:")
    print(f"  Max per Minute: {report['rate_limits']['max_per_minute']}")
    print(f"  Max per Hour: {report['rate_limits']['max_per_hour']}")

    print(f"\n🛡️  Guardrail Rules:")
    print(f"  Advisory Patterns: {report['guardrail_rules']['advisory_patterns']}")
    print(f"  PII Patterns: {report['guardrail_rules']['pii_patterns']}")
    print(f"  Max Response Sentences: {report['guardrail_rules']['max_response_sentences']}")

    print(f"\n📁 Audit Log Size: {report['audit_log_size']} entries")


def main():
    """CLI entry point for Phase 8."""
    parser = argparse.ArgumentParser(
        description="Phase 8: Guardrails & Compliance Layer"
    )
    parser.add_argument(
        "--mode",
        choices=["test", "analytics", "report", "demo", "output"],
        default="test",
        help="Mode: test (run tests), demo (demo queries), analytics (show analytics), report (compliance report), output (test output validation)"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    try:
        # Initialize compliance manager
        manager = ComplianceManager()

        if args.mode == "test":
            run_compliance_tests(manager)
            manager.save_audit_log()

        elif args.mode == "demo":
            run_demo_queries(manager)
            manager.save_audit_log()

        elif args.mode == "analytics":
            # Run some queries first to generate data
            demo_queries = [
                "What is the NAV?",
                "Should I invest?",
                "My PAN is ABCDE1234F",
                "What is the expense ratio?",
                "Which fund is better?",
            ]

            for query in demo_queries:
                manager.validate_query(query)

            analytics = manager.get_analytics()
            print("\n" + "="*80)
            print("📊 Query Analytics")
            print("="*80)
            print(json.dumps(analytics, indent=2))

            manager.save_audit_log()

        elif args.mode == "report":
            # Generate some data
            demo_queries = [
                "What is the NAV?",
                "Should I invest?",
                "What is the SIP minimum?",
            ]

            for query in demo_queries:
                manager.validate_query(query)

            show_compliance_report(manager)
            manager.save_audit_log()

        elif args.mode == "output":
            test_output_validation(manager)

    except Exception as e:
        logger.error(f"Phase 8 failed: {e}", exc_info=True)
        print(f"\n❌ Phase 8 execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
