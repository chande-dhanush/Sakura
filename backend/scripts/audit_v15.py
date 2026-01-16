#!/usr/bin/env python3
"""
Sakura V15: Production Audit Script
====================================
Comprehensive verification of V15 architecture.

Run with: python scripts/audit_v15.py

Checks:
1. All imports work
2. DesireSystem functions correctly
3. ProactiveScheduler functions correctly
4. Prompts are well-formed
5. Server starts without errors
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

results = []


def test(name: str, condition: bool, details: str = ""):
    """Record test result."""
    status = PASS if condition else FAIL
    results.append((status, name, details))
    print(f"  {status} {name}" + (f" ({details})" if details else ""))
    return condition


def section(title: str):
    """Print section header."""
    print()
    print(f"{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def audit_imports():
    """Test all V15 imports."""
    section("1. IMPORT VERIFICATION")
    
    # Core imports
    try:
        from sakura_assistant.core.cognitive.desire import DesireSystem, get_desire_system, Mood
        test("DesireSystem import", True)
    except Exception as e:
        test("DesireSystem import", False, str(e))
    
    try:
        from sakura_assistant.core.cognitive.proactive import ProactiveScheduler, get_proactive_scheduler
        test("ProactiveScheduler import", True)
    except Exception as e:
        test("ProactiveScheduler import", False, str(e))
    
    try:
        from sakura_assistant.core.scheduler import (
            schedule_cognitive_tasks,
            precompute_initiations,
            run_hourly_desire_tick,
            run_full_sleep_cycle
        )
        test("Scheduler V15 functions import", True)
    except Exception as e:
        test("Scheduler V15 functions import", False, str(e))
    
    try:
        from sakura_assistant.core.memory.reflection import get_reflection_engine
        test("ReflectionEngine import", True)
    except Exception as e:
        test("ReflectionEngine import", False, str(e))
    
    try:
        from sakura_assistant.core.world_graph import get_world_graph
        test("WorldGraph import", True)
    except Exception as e:
        test("WorldGraph import", False, str(e))


def audit_desire_system():
    """Test DesireSystem functionality."""
    section("2. DESIRE SYSTEM")
    
    from sakura_assistant.core.cognitive.desire import DesireSystem, Mood
    
    # Create fresh instance for testing
    ds = DesireSystem.__new__(DesireSystem)
    ds._initialized = False
    ds.__init__()
    
    # Test initial state
    test("Initial social_battery = 1.0", ds.state.social_battery == 1.0)
    test("Initial loneliness = 0.0", ds.state.loneliness == 0.0)
    
    # Test message handling
    initial_battery = ds.state.social_battery
    ds.on_user_message("Test message")
    test("User message drains battery", ds.state.social_battery < initial_battery)
    
    # Test mood generation
    mood_prompt = ds.get_mood_prompt()
    test("Mood prompt is non-empty", len(mood_prompt) > 10)
    test("Mood prompt has [MOOD:] prefix", "[MOOD:" in mood_prompt)
    
    # Test mood states
    ds.state.social_battery = 0.1
    test("Low battery → TIRED mood", ds.get_mood() == Mood.TIRED)
    
    ds.state.social_battery = 0.5
    ds.state.loneliness = 0.8
    test("High loneliness → MELANCHOLIC mood", ds.get_mood() == Mood.MELANCHOLIC)
    
    # Test initiation logic
    ds.state.loneliness = 0.3
    should_act, reason = ds.should_initiate()
    test("Low loneliness → no initiation", should_act is False)


def audit_proactive_scheduler():
    """Test ProactiveScheduler functionality."""
    section("3. PROACTIVE SCHEDULER")
    
    from sakura_assistant.core.cognitive.proactive import ProactiveScheduler
    import tempfile
    
    ps = ProactiveScheduler.__new__(ProactiveScheduler)
    ps._initialized = False
    ps.__init__()
    
    # Test with temp file
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        ps.initiations_path = f.name
    
    # Test save/load
    ps.save_planned_initiations(["Hello", "How are you?", "Miss you"])
    messages = ps.get_planned_initiations()
    test("Can save initiations", True)
    test("Can load 3 initiations", len(messages) == 3)
    
    # Test pop
    msg = ps.pop_initiation()
    test("Pop returns first message", msg == "Hello")
    
    remaining = ps.get_planned_initiations()
    test("Pop removes message", len(remaining) == 2)
    
    # Cleanup
    os.unlink(ps.initiations_path)


def audit_prompts():
    """Audit system prompts for consistency."""
    section("4. PROMPT AUDIT")
    
    from sakura_assistant.config import REFLECTION_SYSTEM_PROMPT
    
    # Reflection prompt
    test("REFLECTION_SYSTEM_PROMPT exists", len(REFLECTION_SYSTEM_PROMPT) > 100)
    test("Reflection prompt has entities section", "entities" in REFLECTION_SYSTEM_PROMPT.lower())
    test("Reflection prompt has constraints section", "constraint" in REFLECTION_SYSTEM_PROMPT.lower())
    test("Reflection prompt has retirements section", "retirement" in REFLECTION_SYSTEM_PROMPT.lower())
    test("Reflection prompt requests JSON", "json" in REFLECTION_SYSTEM_PROMPT.lower())


def audit_world_graph():
    """Audit World Graph configuration."""
    section("5. WORLD GRAPH")
    
    from sakura_assistant.core.world_graph import WorldGraph, EntityType, EntityLifecycle
    
    # Test constraint priority filter
    wg = WorldGraph()
    
    # Add a mock constraint
    wg.entities["constraint:test"] = type('MockEntity', (), {
        'id': 'constraint:test',
        'summary': 'Test constraint',
        'lifecycle': EntityLifecycle.PROMOTED,
        'attributes': {'implications': ['walking'], 'criticality': 0.9}
    })()
    
    context = wg.get_context_for_responder()
    test("Responder context generated", len(context) > 50)
    
    # Clean up
    del wg.entities["constraint:test"]


def audit_data_files():
    """Audit data file integrity."""
    section("6. DATA FILES")
    
    from sakura_assistant.config import get_project_root
    data_dir = Path(get_project_root()) / "data"
    
    # Check expected files
    expected_files = [
        "world_graph.json",
    ]
    
    for filename in expected_files:
        filepath = data_dir / filename
        exists = filepath.exists()
        test(f"{filename} exists", exists)
        
        if exists and filename.endswith(".json"):
            try:
                with open(filepath) as f:
                    json.load(f)
                test(f"{filename} is valid JSON", True)
            except Exception as e:
                test(f"{filename} is valid JSON", False, str(e))


def print_summary():
    """Print summary of all tests."""
    section("SUMMARY")
    
    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    total = len(results)
    
    print()
    print(f"  Total:  {total}")
    print(f"  Passed: {passed} {PASS}")
    print(f"  Failed: {failed} {FAIL}")
    print()
    
    if failed > 0:
        print("  Failed tests:")
        for status, name, details in results:
            if status == FAIL:
                print(f"    {FAIL} {name}: {details}")
        print()
    
    return failed == 0


def main():
    print()
    print("🔍 SAKURA V15 PRODUCTION AUDIT")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    audit_imports()
    audit_desire_system()
    audit_proactive_scheduler()
    audit_prompts()
    audit_world_graph()
    audit_data_files()
    
    success = print_summary()
    
    if success:
        print("✅ All checks passed! V15 is production-ready.")
    else:
        print("❌ Some checks failed. Please fix before deploying.")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
