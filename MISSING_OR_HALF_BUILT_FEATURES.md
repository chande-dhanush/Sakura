# Sakura: Missing or Half-Built Features
**Updated:** 2026-04-14 (Phase 1 Stabilization)

## Previously Missing / Now Fixed

| Feature | Was | Now | Fix |
|---------|-----|-----|-----|
| Feature | Was | Now | Fix |
|---------|-----|-----|-----|
| Reference Resolution Injection | 👻 Ghost — computed then discarded | ✅ Wired — injected into responder context | Phase 2 |
| Desire System Hourly Tick | ❌ Dead — wrong import path, silently swallowed | 🔧 Fixed — correct path + loud error handling | Phase 1 |
| Proactive Scheduler Loop | ❌ Dead — wrong import path, silently swallowed | 🔧 Fixed — correct path + startup verification | Phase 1 |
| Sync Router Path | ⚠️ Broken — Undefined template variable | ✅ Fixed — Now uses ROUTER_SYSTEM_PROMPT | Phase 2 |
| World Graph get_context_for_planner | ⚠️ Redundant — Double resolution | ✅ Fixed — Removed dead resolution code | Phase 2 |
| Version String | ⚠️ Drifted — V10/V18 mismatch | ✅ Fixed — Canonical V19.0 in version.py | Phase 3 |
| Test Fixture Stale assumptions | ⚠️ Stale — "Dhanush" hardcoded | ✅ Fixed — pytest mocks/fixtures | Phase 3 |

## Still Partial

| Feature | Status | Details | Priority |
|---------|--------|---------|----------|
| **Confidence Gating** | 👻 Documented, not implemented | `dispatcher.py` uses deterministic heuristics only. No confidence thresholds. Documented in V18 design but never coded. | P2 — Phase 4 |
| **Desire Behavioral Impact** | ⚠️ Cosmetic | Desire system successfully modulates prompt tone (e.g., "[MOOD: TIRED]") but does not affect routing decisions, tool selection, or proactive timing. | P2 — Phase 5 |
| **Tool Fidelity Verification** | ⚠️ Loose | Responder checks if tool succeeded, but doesn't verify if output matches schema exactly before narrating. | P2 — Phase 4 |

## Explicitly Deferred

| Feature | Reason | When |
|---------|--------|------|
| Multi-agent reasoning | Current architecture is sequential ReAct, not multi-agent. Would require fundamental redesign. | Post-stabilization |
| Confidence-based routing | Requires evaluation dataset and performance benchmarking. | Phase 4 |
| Full test fixture setup | World graph and identity tests need proper fixture files. | Phase 3 |
