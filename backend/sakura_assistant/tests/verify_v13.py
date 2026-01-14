"""
V13 Feature Verification Script
===============================
Quick verification of all V13 features in one pass.

Run: python sakura_assistant/tests/verify_v13.py
"""

import sys
import os
from datetime import datetime, timedelta

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_temporal_decay():
    """Verify temporal decay works."""
    print("\n" + "="*50)
    print("🧪 TEST: Temporal Decay")
    print("="*50)
    
    from sakura_assistant.core.world_graph import (
        EntityNode, EntityType, EntityLifecycle, EntitySource
    )
    
    # Test 1: Fresh entity
    entity = EntityNode(
        id="test:fresh",
        type=EntityType.TOPIC,
        name="Fresh",
        confidence=0.8,
        last_referenced=datetime.now()
    )
    conf = entity.get_current_confidence()
    assert conf == 0.8, f"Fresh confidence wrong: {conf}"
    print(f"  ✅ Fresh entity confidence: {conf}")
    
    # Test 2: Decay after 30 days
    entity_old = EntityNode(
        id="test:old",
        type=EntityType.TOPIC,
        name="Old",
        confidence=1.0,
        last_referenced=datetime.now() - timedelta(days=30)
    )
    conf_old = entity_old.get_current_confidence()
    assert 0.45 <= conf_old <= 0.55, f"30-day decay wrong: {conf_old}"
    print(f"  ✅ 30-day decay (half-life): {conf_old:.3f}")
    
    # Test 3: touch() boost
    entity_boost = EntityNode(
        id="test:boost",
        type=EntityType.TOPIC,
        name="Boost",
        confidence=0.8,
        last_referenced=datetime.now()
    )
    entity_boost.touch()
    # Use approximate comparison for floating point
    assert abs(entity_boost.confidence - 0.85) < 0.0001, f"touch() boost wrong: {entity_boost.confidence}"
    print(f"  ✅ touch() boost: 0.8 → {entity_boost.confidence}")
    
    # Test 4: Demotion
    demote_entity = EntityNode(
        id="test:demote",
        type=EntityType.TOPIC,
        name="Demote",
        lifecycle=EntityLifecycle.PROMOTED,
        source=EntitySource.TOOL_RESULT,
        confidence=0.5,
        last_referenced=datetime.now() - timedelta(days=60)
    )
    demoted = demote_entity.check_lifecycle_demotion()
    assert demoted == True
    assert demote_entity.lifecycle == EntityLifecycle.CANDIDATE
    print(f"  ✅ Lifecycle demotion: PROMOTED → CANDIDATE")
    
    print("  ✅ TEMPORAL DECAY: ALL PASSED")
    return True


def test_adaptive_routing():
    """Verify urgency detection."""
    print("\n" + "="*50)
    print("🧪 TEST: Adaptive Routing")
    print("="*50)
    
    # Force reimport to get latest code
    import importlib
    import sakura_assistant.core.router as router_module
    importlib.reload(router_module)
    from sakura_assistant.core.router import get_urgency, RouteResult
    
    # Test urgency detection
    urgent_tests = [
        ("I need this urgently", "URGENT"),
        ("ASAP check my email", "URGENT"),
        ("What's the weather?", "NORMAL"),
        ("Play some music", "NORMAL"),
    ]
    
    for query, expected in urgent_tests:
        result = get_urgency(query)
        assert result == expected, f"'{query}' expected {expected}, got {result}"
        print(f"  ✅ '{query[:25]}...' → {result}")
    
    # Test RouteResult with urgency
    result = RouteResult("DIRECT", "gmail_read_email", "URGENT")
    assert result.is_urgent == True
    print(f"  ✅ RouteResult.is_urgent works")
    
    print("  ✅ ADAPTIVE ROUTING: ALL PASSED")
    return True


def test_code_interpreter():
    """Verify code interpreter setup."""
    print("\n" + "="*50)
    print("🧪 TEST: Code Interpreter")
    print("="*50)
    
    from sakura_assistant.core.tools_libs.code_interpreter import (
        execute_python, check_code_interpreter_status, _check_docker_available
    )
    
    # Check tools exist
    assert execute_python is not None
    print("  ✅ execute_python tool exists")
    
    # Check docker availability
    docker_ok = _check_docker_available()
    if docker_ok:
        print("  ✅ Docker is running")
        
        # Try a simple execution
        result = check_code_interpreter_status.invoke({})
        print(f"  ✅ Status check: {result[:50]}...")
    else:
        print("  ⚠️ Docker not running (start Docker Desktop to use)")
    
    print("  ✅ CODE INTERPRETER: SETUP VERIFIED")
    return True


def test_audio_tools():
    """Verify audio tools setup."""
    print("\n" + "="*50)
    print("🧪 TEST: Audio Summarization")
    print("="*50)
    
    from sakura_assistant.core.tools_libs.audio_tools import (
        transcribe_audio, summarize_audio
    )
    
    # Check tools exist and are LangChain tools
    assert hasattr(transcribe_audio, 'name')
    assert transcribe_audio.name == "transcribe_audio"
    print("  ✅ transcribe_audio tool exists")
    
    assert hasattr(summarize_audio, 'name')
    assert summarize_audio.name == "summarize_audio"
    print("  ✅ summarize_audio tool exists")
    
    # Check pydub availability
    try:
        from pydub import AudioSegment
        print("  ✅ pydub installed")
    except ImportError:
        print("  ⚠️ pydub not installed: pip install pydub")
    
    # Check speech_recognition
    try:
        import speech_recognition as sr
        print("  ✅ speech_recognition installed")
    except ImportError:
        print("  ⚠️ speech_recognition not installed")
    
    print("  ✅ AUDIO TOOLS: SETUP VERIFIED")
    return True


def test_tools_registry():
    """Verify all V13 tools are in registry."""
    print("\n" + "="*50)
    print("🧪 TEST: Tools Registry")
    print("="*50)
    
    from sakura_assistant.core.tools import get_all_tools
    
    all_tools = get_all_tools()
    tool_names = [t.name for t in all_tools]
    
    v13_tools = [
        "execute_python",
        "check_code_interpreter_status",
        "transcribe_audio",
        "summarize_audio",
    ]
    
    for tool in v13_tools:
        if tool in tool_names:
            print(f"  ✅ {tool} registered")
        else:
            print(f"  ❌ {tool} NOT FOUND")
            return False
    
    print(f"  ✅ TOOLS REGISTRY: {len(all_tools)} tools total")
    return True


def main():
    """Run all verification tests."""
    print("\n" + "="*60)
    print("🚀 SAKURA V13 FEATURE VERIFICATION")
    print("="*60)
    
    results = []
    
    try:
        results.append(("Temporal Decay", test_temporal_decay()))
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        results.append(("Temporal Decay", False))
    
    try:
        results.append(("Adaptive Routing", test_adaptive_routing()))
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        results.append(("Adaptive Routing", False))
    
    try:
        results.append(("Code Interpreter", test_code_interpreter()))
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        results.append(("Code Interpreter", False))
    
    try:
        results.append(("Audio Tools", test_audio_tools()))
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        results.append(("Audio Tools", False))
    
    try:
        results.append(("Tools Registry", test_tools_registry()))
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        results.append(("Tools Registry", False))
    
    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  TOTAL: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 ALL V13 FEATURES VERIFIED!")
    else:
        print("\n⚠️ Some features need attention")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
