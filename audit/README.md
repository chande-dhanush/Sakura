# Sakura V15.2.2 Audit Toolkit

Engineering-grade verification suite for the Sakura Personal AI system.

## Available Audit Scripts

| Script | Purpose | Key Metrics |
|--------|---------|-------------|
| `run_audit.py` | **Unified Audit Runner** | Runs all audits, generates JSON/MD reports |
| `audit_v15.py` | V15.2.2 Production Audit | Security, SOLID, Performance, Cognitive |
| `audit_brain.py` | World Graph invariants | Identity protection, source tracking |
| `audit_chaos.py` | Failure injection testing | Recovery rate, graceful degradation |
| `audit_leak.py` | Memory leak detection | RSS growth, object counts |
| `audit_speed.py` | Performance benchmarking | Response latency, O(1) scaling |
| `audit_tokens.py` | Token usage analysis | Cost per query, context efficiency |
| `audit_rag.py` | RAG fidelity testing | Precision, recall, citation accuracy |
| `audit_planner_strictness.py` | Plan execution compliance | Hallucination rate, tool selection |

## Quick Start

```bash
cd audit

# Run unified audit (recommended - generates reports)
python run_audit.py

# Run individual audits
python audit_speed.py
python audit_brain.py
```

## Key Verification Results (V15.2.2)

- **O(1) Scaling**: Query latency variance < 15% at 10/50/100 turn histories
- **Memory Stability**: RSS < 500MB after 100+ queries
- **Chaos Recovery**: 95%+ recovery from failure injection
- **RAG Fidelity**: Precision 0.85+, Recall 0.80+
- **Security Hardening**: OWASP CWE-22, LLM01 compliant
- **SOLID Principles**: Verified for desktop app architecture

## V15.2.2 Additions

- **WebSocket Origin Validation**: Prevents hijacking attacks
- **Path Injection Defense**: DANGEROUS_PATTERNS + Unicode normalization
- **Scraped Content Sanitization**: Filters prompt injection
- **RLock Thread Safety**: TOCTOU race condition prevention
- **Backoff Persistence**: Survives app restarts
- **SOLID Principles Audit**: S/O/L/I/D checks for desktop app

## V15 Cognitive Architecture

- **DesireSystem**: CPU-based mood tracking (social_battery, loneliness)
- **ProactiveScheduler**: Autonomous check-ins (0 daytime LLM cost)
- **Mood Injection**: Responder adapts tone based on internal state
- **Bubble-Gate**: Respects UI visibility

## Architecture Decisions

See `docs/DOCUMENTATION.md` for the full architecture including:
- Smart Router with forced patterns
- ReAct loop with 70B planner
- World Graph single source of truth
- Context valve token management
- Rate limiting per model

## Running Performance Tests

```bash
# Stress test (100 parallel queries)
python backend/sakura_assistant/tests/stress_test_v11.py

# Memory leak check (50 iterations)
python audit/audit_leak.py

# Full V15.2.2 audit
python audit/audit_v15.py
```

## Contributing

All audits should follow the pattern:
1. Setup isolation (fresh container)
2. Execute test scenario
3. Verify invariants
4. Cleanup state

See existing audit scripts for examples.

