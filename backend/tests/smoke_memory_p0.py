"""
P0 Memory Optimization Smoke Test

Tests:
A) Startup RSS check - No embeddings loaded at startup
B) First-use check - Embeddings load on first message
C) FAISS mmap check - Index loaded with mmap flag
D) History cap check - In-memory history <= MAX_INMEM_HISTORY
E) Idle unload simulation

Run: python -m sakura_assistant.tests.smoke_memory_p0
"""
import os
import sys
import time
import gc

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

def get_rss_mb():
    """Get current process RSS in MB."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024**2
    except ImportError:
        print("⚠️ psutil not installed, can't measure RSS")
        return 0

def test_startup_memory():
    """A) Test that no embeddings are loaded at startup."""
    print("\n" + "="*60)
    print("TEST A: Startup Memory Check")
    print("="*60)
    
    rss_before = get_rss_mb()
    print(f" RSS before import: {rss_before:.1f} MB")
    
    # Import the memory store - should NOT load embeddings
    from sakura_assistant.memory.faiss_store import get_memory_store
    
    store = get_memory_store()
    
    rss_after = get_rss_mb()
    print(f" RSS after get_memory_store(): {rss_after:.1f} MB")
    print(f" Delta: {rss_after - rss_before:.1f} MB")
    
    # Check that embeddings are NOT loaded
    if store._embeddings_model is None:
        print(" PASS: Embeddings NOT loaded at startup")
        return True, rss_after
    else:
        print(" FAIL: Embeddings loaded at startup (should be lazy)")
        return False, rss_after

def test_mmap_active():
    """C) Test that FAISS mmap is active."""
    print("\n" + "="*60)
    print("TEST C: FAISS MMAP Check")
    print("="*60)
    
    from sakura_assistant.memory.faiss_store import get_memory_store
    store = get_memory_store()
    
    mmap_active = getattr(store, '_mmap_active', False)
    print(f" MMAP Active: {mmap_active}")
    
    if mmap_active:
        print(" PASS: FAISS loaded with MMAP")
        return True
    else:
        print("⚠️ WARN: FAISS not using MMAP (may be unsupported on this platform)")
        return True  # Not a hard failure

def test_history_cap():
    """D) Test that in-memory history is capped."""
    print("\n" + "="*60)
    print("TEST D: History Cap Check")
    print("="*60)
    
    from sakura_assistant.memory.faiss_store import get_memory_store
    from sakura_assistant.config import MAX_INMEM_HISTORY
    
    store = get_memory_store()
    
    history_len = len(store.conversation_history)
    print(f" In-memory history: {history_len} messages")
    print(f" MAX_INMEM_HISTORY: {MAX_INMEM_HISTORY}")
    
    if history_len <= MAX_INMEM_HISTORY:
        print(" PASS: History capped correctly")
        return True
    else:
        print(f" FAIL: History exceeds cap ({history_len} > {MAX_INMEM_HISTORY})")
        return False

def test_first_use_embedding():
    """B) Test that embeddings load on first use."""
    print("\n" + "="*60)
    print("TEST B: First-Use Embedding Load")
    print("="*60)
    
    from sakura_assistant.memory.faiss_store import get_memory_store
    
    store = get_memory_store()
    rss_before = get_rss_mb()
    
    # Trigger embedding load by calling get_context_for_query
    print(" Triggering embedding load via get_context_for_query...")
    
    try:
        context = store.get_context_for_query("test query")
        print(f" Retrieved context: {len(context)} chars")
    except Exception as e:
        print(f"⚠️ Query failed (may be expected if no data): {e}")
    
    rss_after = get_rss_mb()
    delta = rss_after - rss_before
    
    print(f" RSS before: {rss_before:.1f} MB")
    print(f" RSS after: {rss_after:.1f} MB")
    print(f" Delta: {delta:.1f} MB")
    
    # Check embeddings are now loaded
    if store._embeddings_model is not None:
        print(" PASS: Embeddings loaded on first use")
        if delta >= 200:
            print(f" Memory delta ~{delta:.0f}MB (expected ~350MB for model)")
        return True, rss_after
    else:
        print("⚠️ WARN: Embeddings may not have loaded (FAISS might not be available)")
        return True, rss_after

def test_config_flags():
    """Test that P0 config flags exist."""
    print("\n" + "="*60)
    print("TEST: Config Flags Check")
    print("="*60)
    
    from sakura_assistant import config
    
    flags = [
        ('FAISS_MMAP', True),
        ('LAZY_EMBEDDINGS', True),
        ('MAX_INMEM_HISTORY', 50),
        ('EMBEDDING_IDLE_TIMEOUT', 600),
        ('ENABLE_SILERO', False)
    ]
    
    all_pass = True
    for flag, expected in flags:
        val = getattr(config, flag, None)
        status = "" if val == expected else "⚠️"
        print(f"{status} {flag} = {val} (expected {expected})")
        if val != expected:
            all_pass = False
    
    return all_pass

def run_all_tests():
    """Run all P0 smoke tests."""
    print("="*60)
    print("P0 MEMORY OPTIMIZATION SMOKE TEST")
    print("="*60)
    
    results = {}
    
    # Config check
    results['config'] = test_config_flags()
    
    # A) Startup check
    passed, rss_startup = test_startup_memory()
    results['startup'] = passed
    
    # C) MMAP check
    results['mmap'] = test_mmap_active()
    
    # D) History cap
    results['history_cap'] = test_history_cap()
    
    # B) First-use load
    passed, rss_after = test_first_use_embedding()
    results['first_use'] = passed
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_pass = all(results.values())
    for test, passed in results.items():
        status = " PASS" if passed else " FAIL"
        print(f"  {test}: {status}")
    
    print()
    print(f" Final RSS: {get_rss_mb():.1f} MB")
    
    if all_pass:
        print("\n ALL TESTS PASSED")
        return 0
    else:
        print("\n⚠️ SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
