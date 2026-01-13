"""
Sakura War Room Audit: Memory Leak Detection
=============================================
Critical for 24/7 desktop applications (Tauri).

Tests:
- Memory stability over 500+ simulated turns
- Garbage collection effectiveness
- Long-running session degradation

Output: audit_artifacts/memory_report.txt
"""
import os
import sys
import gc
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "audit_artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)


def get_memory_mb():
    """Get current process memory in MB."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        # Fallback for systems without psutil
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def audit_memory_leak_lightweight():
    """
    Lightweight memory audit using core components only.
    
    Avoids LLM calls to make test fast and repeatable.
    """
    print("💧 Starting Memory Leak Audit (Lightweight Mode)...")
    
    from sakura_assistant.core.world_graph import WorldGraph, EntityType, EntitySource
    from sakura_assistant.core.tools import get_all_tools
    
    # Force garbage collection before starting
    gc.collect()
    start_mem = get_memory_mb()
    print(f"  Start Memory: {start_mem:.2f} MB")
    
    measurements = []
    
    # 1. World Graph stress test
    print("\n  Phase 1: World Graph Stress (500 entities)...")
    graph = WorldGraph()
    
    for i in range(500):
        graph.get_or_create_entity(
            type=EntityType.TOPIC,
            name=f"StressEntity_{i}",
            source=EntitySource.TOOL_RESULT
        )
        graph.record_action(
            tool="test_tool",
            args={"iteration": i},
            result=f"Result for iteration {i}",
            success=True
        )
        
        if i % 100 == 0:
            gc.collect()
            mem = get_memory_mb()
            measurements.append({"phase": "graph", "iteration": i, "memory_mb": mem})
            print(f"    Iteration {i}: {mem:.2f} MB")
    
    # 2. Tool instantiation stress
    print("\n  Phase 2: Tool Instantiation Stress (100 cycles)...")
    for i in range(100):
        tools = get_all_tools()
        tool_map = {t.name: t for t in tools}
        del tools, tool_map
        
        if i % 25 == 0:
            gc.collect()
            mem = get_memory_mb()
            measurements.append({"phase": "tools", "iteration": i, "memory_mb": mem})
            print(f"    Cycle {i}: {mem:.2f} MB")
    
    # 3. Context generation stress
    print("\n  Phase 3: Context Generation Stress (200 queries)...")
    for i in range(200):
        # Simulate context generation (the hot path for each request)
        context = graph.get_context_for_planner(f"Test query number {i}")
        _ = graph.get_context_for_responder()
        _ = graph.resolve_reference("that")
        
        if i % 50 == 0:
            gc.collect()
            mem = get_memory_mb()
            measurements.append({"phase": "context", "iteration": i, "memory_mb": mem})
            print(f"    Query {i}: {mem:.2f} MB")
    
    # Final measurement
    gc.collect()
    gc.collect()  # Double collect for thorough cleanup
    time.sleep(0.1)  # Allow GC to complete
    
    end_mem = get_memory_mb()
    growth = end_mem - start_mem
    growth_percent = (growth / start_mem) * 100 if start_mem > 0 else 0
    
    print(f"\n🏁 End Memory: {end_mem:.2f} MB")
    print(f"📈 Total Growth: {growth:.2f} MB ({growth_percent:.1f}%)")
    
    return {
        "start_mb": start_mem,
        "end_mb": end_mem,
        "growth_mb": growth,
        "growth_percent": growth_percent,
        "measurements": measurements,
        "entities_created": 500,
        "actions_recorded": 500,
        "tool_cycles": 100,
        "context_queries": 200,
    }


def audit_memory_leak_full():
    """
    Full memory audit with actual LLM calls.
    
    Warning: This uses API quota and may be slow.
    """
    print("💧 Starting Memory Leak Audit (Full Mode)...")
    
    try:
        from sakura_assistant.core.llm import SmartAssistant
    except ImportError:
        print("  ⚠️ SmartAssistant not available, using lightweight mode")
        return audit_memory_leak_lightweight()
    
    gc.collect()
    start_mem = get_memory_mb()
    print(f"  Start Memory: {start_mem:.2f} MB")
    
    try:
        assistant = SmartAssistant()
    except Exception as e:
        print(f"  ⚠️ Failed to initialize assistant: {e}")
        print("  Falling back to lightweight mode...")
        return audit_memory_leak_lightweight()
    
    # Warmup
    try:
        assistant.run("Hello", [])
    except Exception as e:
        print(f"  ⚠️ Warmup failed: {e}, continuing with lightweight mode")
        return audit_memory_leak_lightweight()
    
    gc.collect()
    warm_mem = get_memory_mb()
    print(f"  Post-warmup Memory: {warm_mem:.2f} MB")
    
    measurements = []
    
    # Stress loop with cheap requests
    test_queries = [
        "what time is it",
        "hello",
        "thanks",
        "calculate 5 + 5",
    ]
    
    for i in range(50):  # Reduced for API quota
        query = test_queries[i % len(test_queries)]
        try:
            assistant.run(query, [])
        except Exception:
            pass  # Ignore individual failures
        
        if i % 10 == 0:
            gc.collect()
            mem = get_memory_mb()
            measurements.append({"iteration": i, "memory_mb": mem})
            print(f"    Request {i}: {mem:.2f} MB")
    
    gc.collect()
    end_mem = get_memory_mb()
    growth = end_mem - warm_mem
    
    print(f"\n🏁 End Memory: {end_mem:.2f} MB")
    print(f"📈 Growth since warmup: {growth:.2f} MB")
    
    return {
        "start_mb": start_mem,
        "warm_mb": warm_mem,
        "end_mb": end_mem,
        "growth_mb": growth,
        "measurements": measurements,
        "requests_made": 50,
    }


def generate_memory_report(results):
    """Generate the evidence report."""
    
    report_path = os.path.join(ARTIFACTS_DIR, "memory_report.txt")
    
    # Determine pass/fail
    growth_mb = results.get("growth_mb", 0)
    growth_pct = results.get("growth_percent", 0)
    
    # Criteria: <50MB growth OR <10% growth
    passed = growth_mb < 50 and growth_pct < 10
    grade = "A" if growth_mb < 10 else "B" if growth_mb < 25 else "C" if growth_mb < 50 else "F"
    
    with open(report_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("SAKURA WAR ROOM: MEMORY LEAK AUDIT\n")
        f.write("=" * 60 + "\n\n")
        
        f.write("METHODOLOGY:\n")
        f.write("- Created 500 entities + 500 actions in World Graph\n")
        f.write("- Cycled tool instantiation 100 times\n")
        f.write("- Generated 200 context queries\n")
        f.write("- Measured RSS memory throughout\n\n")
        
        f.write("-" * 40 + "\n")
        f.write("RESULTS:\n")
        f.write("-" * 40 + "\n")
        f.write(f"  Start Memory: {results.get('start_mb', 0):.2f} MB\n")
        f.write(f"  End Memory: {results.get('end_mb', 0):.2f} MB\n")
        f.write(f"  Total Growth: {growth_mb:.2f} MB\n")
        f.write(f"  Growth %: {growth_pct:.1f}%\n\n")
        
        if results.get("measurements"):
            f.write("-" * 40 + "\n")
            f.write("MEMORY TIMELINE:\n")
            f.write("-" * 40 + "\n")
            for m in results["measurements"]:
                phase = m.get("phase", "run")
                f.write(f"  {phase:>10} iter {m.get('iteration', 0):>4}: {m['memory_mb']:.2f} MB\n")
        
        f.write("\n" + "=" * 60 + "\n")
        f.write(f"VERDICT: {'[PASS]' if passed else '[FAIL]'}\n")
        f.write(f"GRADE: {grade}\n")
        f.write(f"Criteria: Growth < 50MB AND < 10%\n")
        f.write("=" * 60 + "\n")
    
    print(f"\n✅ Report saved to {report_path}")
    
    # Also generate a simple graph if matplotlib available
    try:
        import matplotlib.pyplot as plt
        
        measurements = results.get("measurements", [])
        if measurements:
            mems = [m["memory_mb"] for m in measurements]
            iters = list(range(len(mems)))
            
            plt.figure(figsize=(10, 6))
            plt.plot(iters, mems, marker='o', linewidth=2)
            plt.title('Sakura Memory Usage Over Time', fontsize=14)
            plt.xlabel('Measurement Point', fontsize=12)
            plt.ylabel('Memory (MB)', fontsize=12)
            plt.grid(True, alpha=0.3)
            
            # Add trend line
            if len(mems) >= 2:
                z = [i for i in range(len(mems))]
                import statistics
                slope = (mems[-1] - mems[0]) / len(mems) if len(mems) > 1 else 0
                trend_label = f"Trend: +{slope:.2f} MB/point" if slope > 0 else f"Trend: {slope:.2f} MB/point"
                plt.annotate(trend_label, xy=(0.7, 0.9), xycoords='axes fraction')
            
            output_path = os.path.join(ARTIFACTS_DIR, "memory_trend.png")
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            print(f"✅ Memory trend graph saved to {output_path}")
            plt.close()
            
    except ImportError:
        pass
    
    return passed


if __name__ == "__main__":
    print("=" * 60)
    print("SAKURA WAR ROOM: MEMORY LEAK AUDIT")
    print("=" * 60)
    
    # Check if psutil is available
    try:
        import psutil
        print("✓ psutil available for accurate memory tracking\n")
    except ImportError:
        print("⚠️ psutil not installed, using fallback memory tracking\n")
        print("   Install with: pip install psutil\n")
    
    # Run lightweight by default (no API calls)
    results = audit_memory_leak_lightweight()
    passed = generate_memory_report(results)
    
    print("\n" + "=" * 60)
    print(f"MEMORY AUDIT {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
