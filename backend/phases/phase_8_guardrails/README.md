# Phase 8 — Guardrails & Compliance Layer (Enhanced)

Enhanced compliance system with audit logging, analytics, and reporting as per architecture.md Section 8.

---

## 📋 Overview

Phase 8 implements the complete **Guardrails & Compliance Layer** with enhanced features beyond basic input/output validation.

### Architecture Reference

This phase implements **architecture.md Section 8**:
- **8.1**: Input Guardrail (Pre-Retrieval)
- **8.2**: Output Guardrail (Post-Generation)
- **8.3**: Refusal Response Template

### Enhanced Features

Builds upon Phase 5.1 (basic guardrails) with:
- ✅ Audit logging for compliance
- ✅ Query analytics and reporting
- ✅ Rate limiting per user/session
- ✅ PII detection and masking
- ✅ Compliance dashboard data
- ✅ Violation tracking

---

## 🔄 Compliance Flow

```
User Query
    ↓
┌──────────────────────┐
│ 1. RATE LIMIT CHECK   │  ← Check per-minute/hour limits
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ 2. INPUT GUARDRAIL    │  ← Classify: factual vs advisory vs PII
│    (Phase 5.1)        │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ 3. AUDIT LOGGING      │  ← Log query for compliance
└──────────┬───────────┘
           ↓ (if safe)
┌──────────────────────┐
│ 4. RAG PIPELINE       │  ← Process query
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ 5. OUTPUT GUARDRAIL   │  ← Validate response (Phase 5.1)
│    + PII CHECK        │  ← Check for PII in response
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ 6. RECORD RESPONSE    │  ← Log to audit trail
└──────────┬───────────┘
           ↓
     Final Response
```

---

## 🛡️ Guardrail Rules (Section 8.1)

### Input Guardrail Patterns

**Advisory Patterns** (blocked):
```python
r"should I (invest|buy|sell|redeem)"
r"which (fund|scheme) is better"
r"recommend"
r"best (fund|scheme|investment)"
r"will .* (go up|grow|increase|fall)"
r"compare .* (returns|performance)"
r"how much (return|profit|loss)"
```

**PII Patterns** (blocked):
```python
r"\b[A-Z]{5}\d{4}[A-Z]\b"          # PAN card
r"\b\d{4}\s?\d{4}\s?\d{4}\b"        # Aadhaar
r"\b\d{9,18}\b"                      # Account numbers
r"\b\d{6}\b"                         # OTP
r"\b[\w.-]+@[\w.-]+\.\w+\b"          # Email
r"\b(\+91|91|0)?[6-9]\d{9}\b"        # Indian phone
```

### Output Guardrail Rules (Section 8.2)

| Check | Action |
|---|---|
| Response > 3 sentences | Truncate to first 3 sentences |
| Missing citation URL | Append best-match source URL |
| Contains advisory language | Strip and replace with disclaimer |
| Missing "Last updated" footer | Append automatically |
| Contains PII in response | Mask and log alert |

---

## 📝 Refusal Response Template (Section 8.3)

### Advisory Refusal

```json
{
  "response": "I appreciate your question, but I can only provide factual information about mutual fund schemes. For investment guidance, please consult a SEBI-registered financial advisor.",
  "source_url": "https://www.amfiindia.com/investor-corner/knowledge-center.html",
  "is_refusal": true,
  "last_updated": "2026-04-19"
}
```

### PII Detection Refusal

```json
{
  "response": "I cannot process personal information. Please remove sensitive details like PAN, Aadhaar, phone numbers, or email addresses and try again.",
  "is_refusal": true,
  "classification": "PII_DETECTED"
}
```

---

## 🚀 Quick Start

### 1. Run Compliance Tests

```bash
cd backend
python phases/phase_8_guardrails/main.py --mode test
```

Runs 8 test cases covering:
- ✅ Factual queries (allowed)
- 🚫 Advisory queries (blocked)
- 🚫 PII queries (blocked)

### 2. Run Demo Queries

```bash
python phases/phase_8_guardrails/main.py --mode demo
```

### 3. View Analytics

```bash
python phases/phase_8_guardrails/main.py --mode analytics
```

### 4. Generate Compliance Report

```bash
python phases/phase_8_guardrails/main.py --mode report
```

### 5. Test Output Validation

```bash
python phases/phase_8_guardrails/main.py --mode output
```

---

## 💡 Usage Examples

### Python API

```python
from phases.phase_8_guardrails import ComplianceManager

# Initialize manager
manager = ComplianceManager()

# Validate query
result = manager.validate_query(
    query="Should I invest in HDFC?",
    user_session="session_123",
    ip_address="192.168.1.1"
)

if not result['is_safe']:
    print(f"Blocked: {result['classification']}")
    print(f"Message: {result['message']}")
else:
    print("Query is safe to process")

# Validate response
validation = manager.validate_response(
    response="The expense ratio is 0.95%.",
    source_url="https://example.com",
    scraped_date="2026-04-19"
)

print(f"Validated: {validation['response']}")
print(f"Issues fixed: {validation['issues_fixed']}")

# Record successful response
manager.record_response(
    query="What is the expense ratio?",
    response="The expense ratio is 0.95%.",
    confidence=0.87,
    source_url="https://example.com",
    processing_time_ms=1250,
    user_session="session_123"
)

# Get analytics
analytics = manager.get_analytics()
print(f"Total queries: {analytics['total_queries']}")
print(f"Block rate: {analytics['block_rate']:.1f}%")

# Generate compliance report
report = manager.get_compliance_report()
print(report)

# Save audit log
manager.save_audit_log()
```

---

## 📊 Analytics

### Query Analytics

Track query patterns and compliance metrics:

```json
{
  "total_queries": 150,
  "factual_queries": 120,
  "advisory_blocked": 25,
  "pii_blocked": 5,
  "block_rate": 20.0,
  "avg_confidence": 0.847,
  "avg_processing_time_ms": 1250.50,
  "hourly_distribution": {
    "09:00": 25,
    "10:00": 45,
    "11:00": 30,
    "12:00": 50
  }
}
```

### Compliance Report

Comprehensive report for audits:

```json
{
  "report_generated_at": "2026-04-19T10:30:00Z",
  "summary": {
    "total_queries": 150,
    "block_rate": 20.0
  },
  "rate_limits": {
    "max_per_minute": 30,
    "max_per_hour": 500
  },
  "guardrail_rules": {
    "advisory_patterns": 7,
    "pii_patterns": 6,
    "max_response_sentences": 3
  },
  "audit_log_size": 150
}
```

---

## 🔒 Rate Limiting

### Configuration

```python
MAX_QUERIES_PER_MINUTE = 30   # Per user/session
MAX_QUERIES_PER_HOUR = 500    # Per user/session
```

### Behavior

- **Per-minute limit**: 30 queries max
- **Per-hour limit**: 500 queries max
- **Sliding window**: Timestamps older than 1 hour are removed
- **Identifier**: Uses user session or IP address

### Rate Limit Response

```json
{
  "is_safe": false,
  "classification": "RATE_LIMITED",
  "message": "Rate limit exceeded. Please try again later.",
  "retry_after": 60
}
```

---

## 📁 Audit Logging

### Log Structure

Each query is logged with:

```json
{
  "timestamp": "2026-04-19T10:30:00Z",
  "query": "What is the NAV of HDFC Mid Cap Fund?",
  "classification": "FACTUAL",
  "is_safe": true,
  "response_provided": true,
  "processing_time_ms": 1250.5,
  "confidence_score": 0.87,
  "source_url": "https://example.com",
  "user_session": "session_123",
  "ip_address": "192.168.1.1"
}
```

### Violation Logging

Blocked queries are logged to separate file:

**File**: `data/audit_logs/violations_20260419.jsonl`

```json
{
  "timestamp": "2026-04-19T10:30:00Z",
  "classification": "ADVISORY",
  "query": "Should I invest in HDFC?",
  "user_session": "session_123",
  "ip_address": "192.168.1.1"
}
```

### Log Files

| File | Purpose |
|------|---------|
| `audit_YYYYMMDD_HHMMSS.json` | Complete audit trail |
| `violations_YYYYMMDD.jsonl` | Blocked queries only |

---

## 🧪 Testing

### Test Cases

Phase 8 includes 8 comprehensive test cases:

| # | Query | Expected | Description |
|---|-------|----------|-------------|
| 1 | "What is the NAV?" | FACTUAL | Factual query - pass |
| 2 | "What is the expense ratio?" | FACTUAL | Factual query - pass |
| 3 | "Should I invest?" | ADVISORY | Advisory - block |
| 4 | "Which fund is better?" | ADVISORY | Comparison - block |
| 5 | "My PAN is ABCDE1234F" | PII_DETECTED | PAN - block |
| 6 | "Call me at 9876543210" | PII_DETECTED | Phone - block |
| 7 | "Email me at test@example.com" | PII_DETECTED | Email - block |
| 8 | "What is the best fund?" | ADVISORY | Recommendation - block |

### Expected Results

- ✅ **Factual queries**: Allowed through
- 🚫 **Advisory queries**: Blocked with polite refusal
- 🚫 **PII queries**: Blocked with security message
- 📊 **Success rate**: Should be 100%

---

## 🔧 Configuration

### Adjust Rate Limits

Edit `backend/phases/phase_8_guardrails/compliance_manager.py`:

```python
MAX_QUERIES_PER_MINUTE = 30   # Change per-minute limit
MAX_QUERIES_PER_HOUR = 500    # Change per-hour limit
```

### Add Advisory Patterns

Edit Phase 5.1 guardrails (used by Phase 8):

```python
# backend/phases/phase_5_runtime/guardrails.py
ADVISORY_PATTERNS = [
    r"should I (invest|buy|sell|redeem)",
    # Add new patterns...
]
```

### Change Audit Log Location

```python
manager = ComplianceManager(audit_log_dir="custom/logs/path/")
```

---

## 📈 Monitoring

### Key Metrics

| Metric | Target | Alert Threshold |
|---|---|---|
| Block Rate | 10-20% | >30% |
| Avg Response Time | <10ms | >50ms |
| PII Detections | <5% | >10% |
| Rate Limit Hits | <1% | >5% |

### Logging

```
2026-04-19 10:30:45 [phase_8_guardrails.compliance_manager] INFO: Phase 8 Compliance Manager initialized
2026-04-19 10:30:45 [phase_8_guardrails.compliance_manager] INFO: Advisory query detected: Should I invest in HDFC...
2026-04-19 10:30:45 [phase_8_guardrails.compliance_manager] INFO: Violation logged: ADVISORY
2026-04-19 10:30:46 [phase_8_guardrails.compliance_manager] INFO: Audit log saved: data/audit_logs/audit_20260419_103046.json (150 entries)
```

---

## 🔗 Integration with Phase 5

Phase 8 wraps and enhances Phase 5.1 guardrails:

```python
from phases.phase_5_runtime.guardrails import InputGuardrail, OutputGuardrail
from phases.phase_8_guardrails.compliance_manager import ComplianceManager

# Phase 8 uses Phase 5.1 internally
class ComplianceManager:
    def __init__(self):
        self.input_guardrail = InputGuardrail()   # Phase 5.1
        self.output_guardrail = OutputGuardrail()  # Phase 5.1
        # Plus additional compliance features...
```

---

## 📚 Related Documentation

- **Architecture**: `docs/architecture.md` (Section 8)
- **Phase 5 Guardrails**: `backend/phases/phase_5_runtime/guardrails.py`
- **Phase 7 RAG Flow**: `backend/phases/phase_7_rag_flow/README.md`

---

## ✅ Implementation Checklist

- [x] Section 8.1: Input Guardrail (advisory + PII detection)
- [x] Section 8.2: Output Guardrail (validation rules)
- [x] Section 8.3: Refusal Response Template
- [x] Audit logging
- [x] Query analytics
- [x] Rate limiting (per-minute + per-hour)
- [x] PII masking in responses
- [x] Violation tracking
- [x] Compliance reporting
- [x] Comprehensive testing
- [x] Documentation

**Status**: ✅ **COMPLETE** - Production Ready!

---

**Version**: 1.0.0  
**Last Updated**: 2026-04-19  
**Phase**: 8 (Guardrails & Compliance Layer - Enhanced)  
**Architecture**: Section 8.1-8.3
