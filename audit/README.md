# Sakura V13 Audit Toolkit

Engineering-grade verification suite for the Sakura Personal AI system.

## Available Audit Scripts

All audit scripts are located in `backend/sakura_assistant/tests/audit/`.

| Script | Purpose | Key Metrics |
|--------|---------|-------------|
| `audit_brain.py` | World Graph invariants | Identity protection, source tracking |
| `audit_chaos.py` | Failure injection testing | Recovery rate, graceful degradation |
| `audit_leak.py` | Memory leak detection | RSS growth, object counts |
| `audit_speed.py` | Performance benchmarking | Response latency, O(1) scaling |
| `audit_tokens.py` | Token usage analysis | Cost per query, context efficiency |
| `audit_rag.py` | RAG fidelity testing | Precision, recall, citation accuracy |
| `audit_planner_strictness.py` | Plan execution compliance | Hallucination rate, tool selection |
| `final_v12_audit.py` | Full E2E validation | All V12 features working together |

## Quick Start

```bash
cd backend

# Run individual audit
python -m pytest sakura_assistant/tests/audit/audit_speed.py -v

# Run full audit suite
python -m pytest sakura_assistant/tests/audit/ -v

# Run V12 E2E audit
python tests/final_v12_audit.py
```

## Key Verification Results (V12)

- **O(1) Scaling**: Query latency variance < 15% at 10/50/100 turn histories
- **Memory Stability**: RSS < 500MB after 100+ queries
- **Chaos Recovery**: 95%+ recovery from failure injection
- **RAG Fidelity**: Precision 0.85+, Recall 0.80+

## V13 Additions

- **Code Interpreter Sandbox**: Docker-isolated Python execution
- **Temporal Decay**: 30-day half-life confidence decay
- **Adaptive Routing**: Urgency-based model selection
- **Audio Summarization**: Google STT + LLM summary

## Architecture Decisions

See `DOCUMENTATION.md` for the full V12/V13 architecture including:
- Smart Router with forced patterns
- ReAct loop with 70B planner
- World Graph single source of truth
- Context valve token management
- Rate limiting per model

## Running Performance Tests

```bash
# Stress test (100 parallel queries)
python sakura_assistant/tests/stress_test_v11.py

# Memory leak check (50 iterations)
python sakura_assistant/tests/audit/audit_leak.py
```

## Contributing

All audits should follow the pattern:
1. Setup isolation (fresh container)
2. Execute test scenario
3. Verify invariants
4. Cleanup state

See existing audit scripts for examples.
