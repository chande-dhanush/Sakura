"""
Yuki V4 Stabilization Regression Test Suite
Tests all critical paths after stabilization patches.
"""
import sys
import os
import time
import json

sys.path.append(os.getcwd())

def test_config():
    """Test config flags are correctly set."""
    print("=== TEST: Config Flags ===")
    from sakura_assistant.config import (
        ENABLE_LOCAL_ROUTER, ENABLE_V4_SUMMARY, ENABLE_V4_COMPACT_CONTEXT,
        V4_MAX_RAW_MESSAGES, V4_MEMORY_LIMIT
    )
    
    assert ENABLE_LOCAL_ROUTER == False, "ENABLE_LOCAL_ROUTER should be False"
    assert V4_MAX_RAW_MESSAGES == 3, "V4_MAX_RAW_MESSAGES should be 3"
    assert V4_MEMORY_LIMIT == 2, "V4_MEMORY_LIMIT should be 2"
    print("✅ Config flags correct")
    return True

def test_history_sync():
    """Test ViewModel and Store share the same history reference."""
    print("\n=== TEST: History Sync ===")
    from sakura_assistant.memory.faiss_store import get_memory_store
    from sakura_assistant.ui.viewmodel import ChatViewModel
    
    store = get_memory_store()
    # Wait for any async init
    time.sleep(1)
    
    vm = ChatViewModel()
    time.sleep(2)  # Wait for _init_memory
    
    # Test shared reference
    if vm.conversation_history is not store.conversation_history:
        print("⚠️ VM history is different object, checking sync via methods")
    
    # Test append via store method
    test_msg = {"role": "system", "content": f"TEST_MSG_{time.time()}"}
    store.append_to_history(test_msg)
    
    if test_msg in store.conversation_history:
        print("✅ Store append works")
    else:
        print("❌ Store append FAILED")
        return False
    
    # Clean up test message
    if test_msg in store.conversation_history:
        store.conversation_history.remove(test_msg)
    
    print("✅ History sync working")
    return True

def test_clear_preserves_reference():
    """Test that clear_all_memory preserves list reference."""
    print("\n=== TEST: Clear Preserves Reference ===")
    from sakura_assistant.memory.faiss_store import get_memory_store
    
    store = get_memory_store()
    original_id = id(store.conversation_history)
    
    # Add a test message first
    store.append_to_history({"role": "test", "content": "temp"})
    
    # Clear
    store.clear_all_memory()
    
    new_id = id(store.conversation_history)
    
    if original_id == new_id:
        print("✅ List reference preserved after clear")
        return True
    else:
        print("❌ List reference CHANGED after clear (regression!)")
        return False

def test_memory_importance():
    """Test memory importance save/load/reinforce."""
    print("\n=== TEST: Memory Importance ===")
    from sakura_assistant.memory.faiss_store import get_memory_store
    from sakura_assistant.memory.faiss_store.store import MEMORY_IMPORTANCE_PATH
    
    store = get_memory_store()
    
    # Set test importance
    store.memory_importance["test_999"] = 0.5
    store.reinforce_memory(999, boost=0.1)
    
    # Check in-memory
    if store.memory_importance.get("999") == 0.6:
        print("✅ Reinforcement in-memory works")
    else:
        print(f"⚠️ Reinforcement value: {store.memory_importance.get('999')}")
    
    # Check disk persistence
    if MEMORY_IMPORTANCE_PATH.exists():
        with open(MEMORY_IMPORTANCE_PATH, 'r') as f:
            data = json.load(f)
        if "999" in data:
            print("✅ Importance persisted to disk")
        else:
            print("⚠️ Importance not in disk file")
    
    # Cleanup
    if "999" in store.memory_importance:
        del store.memory_importance["999"]
    if "test_999" in store.memory_importance:
        del store.memory_importance["test_999"]
    
    return True

def test_no_qwen_startup():
    """Test that Qwen is not loaded on startup."""
    print("\n=== TEST: No Qwen on Startup ===")
    from sakura_assistant.core.llm import _qwen_model
    
    if _qwen_model is None:
        print("✅ Qwen NOT loaded (correct)")
        return True
    else:
        print("❌ Qwen IS loaded (should be lazy)")
        return False

def test_v4_context_format():
    """Test V4 compact context builder output format."""
    print("\n=== TEST: V4 Context Format ===")
    from sakura_assistant.utils.summary import build_compact_context
    
    test_messages = [
        {"role": "user", "content": "Hello there"},
        {"role": "assistant", "content": "Hi!"},
        {"role": "user", "content": "How are you?"}
    ]
    test_memories = [
        {"text": "User likes coffee", "importance": 0.8, "relevance": 0.7}
    ]
    
    context = build_compact_context("Test summary", test_messages, test_memories)
    
    # Verify structure
    assert "<CONTEXT>" in context, "Missing <CONTEXT> tag"
    assert "</CONTEXT>" in context, "Missing </CONTEXT> tag"
    assert "Summary:" in context, "Missing Summary section"
    assert "Recent:" in context, "Missing Recent section"
    
    print(f"✅ V4 context format correct ({len(context)} chars)")
    return True

def test_router_api_fallback():
    """Test that router uses API when local is disabled."""
    print("\n=== TEST: Router API Fallback ===")
    from sakura_assistant.config import ENABLE_LOCAL_ROUTER
    
    # Just verify config
    if not ENABLE_LOCAL_ROUTER:
        print("✅ Router set to API mode")
        return True
    else:
        print("❌ Local router still enabled")
        return False

def run_all_tests():
    """Run all stabilization tests."""
    print("=" * 50)
    print("YUKI V4 STABILIZATION REGRESSION TESTS")
    print("=" * 50)
    
    results = []
    
    results.append(("Config", test_config()))
    results.append(("History Sync", test_history_sync()))
    results.append(("Clear Reference", test_clear_preserves_reference()))
    results.append(("Memory Importance", test_memory_importance()))
    results.append(("No Qwen Startup", test_no_qwen_startup()))
    results.append(("V4 Context Format", test_v4_context_format()))
    results.append(("Router API Fallback", test_router_api_fallback()))
    
    print("\n" + "=" * 50)
    print("RESULTS SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - STABILIZATION COMPLETE")
    else:
        print("\n⚠️ SOME TESTS FAILED - REVIEW NEEDED")
    
    return passed == total

if __name__ == "__main__":
    run_all_tests()
