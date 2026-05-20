import json
from pathlib import Path
from collections import defaultdict

def generate_baseline():
    script_dir = Path(__file__).parent
    # Flight recorder is at backend/data/flight_recorder.jsonl
    log_path = script_dir.parent / "data" / "flight_recorder.jsonl"
    report_path = script_dir.parent.parent / "docs" / "refactor_logs" / "baseline_metrics.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not log_path.exists():
        print(f"Error: Log file not found at {log_path}")
        return
        
    traces = {}
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                tid = entry.get('trace_id')
                if not tid:
                    continue
                if tid not in traces:
                    traces[tid] = {
                        'query': '',
                        'success': True,
                        'total_ms': 0,
                        'llm_calls': 0,
                        'tokens': {'prompt': 0, 'completion': 0, 'total': 0},
                        'spans': [],
                        'route': 'CHAT'  # Default fallback
                    }
                
                t = traces[tid]
                event = entry.get('event')
                if event == 'trace_start':
                    t['query'] = entry.get('query', '')
                elif event == 'trace_end':
                    t['total_ms'] = entry.get('total_ms', 0)
                    t['success'] = entry.get('success', True)
                    t['llm_calls'] = entry.get('llm_calls', 0)
                    t['tokens'] = entry.get('tokens', {'prompt': 0, 'completion': 0, 'total': 0})
                elif event == 'span':
                    stage = entry.get('stage')
                    content = entry.get('content', '')
                    t['spans'].append(entry)
                    if stage == 'Router' and 'Classified as' in content:
                        for r in ['PLAN', 'DIRECT', 'CHAT', 'RESEARCH', 'MEMORY_RECALL']:
                            if r in content:
                                t['route'] = r
                                break
            except json.JSONDecodeError:
                continue

    # Filter completed traces
    completed = [t for t in traces.values() if t['total_ms'] > 0]
    total_traces = len(completed)
    
    if total_traces == 0:
        print("No completed traces found in flight recorder logs.")
        return

    # Calculations
    route_counts = defaultdict(int)
    route_latencies = defaultdict(list)
    route_successes = defaultdict(int)
    total_llm_calls = 0
    total_tokens = 0
    total_completion_tokens = 0
    
    tool_runs = 0
    tool_failures = 0
    
    for t in completed:
        r = t['route']
        route_counts[r] += 1
        route_latencies[r].append(t['total_ms'])
        if t['success']:
            route_successes[r] += 1
            
        total_llm_calls += t['llm_calls']
        total_tokens += t['tokens'].get('total', 0)
        total_completion_tokens += t['tokens'].get('completion', 0)
        
        for span in t['spans']:
            if span.get('stage') == 'ToolExecution' or span.get('stage') == 'Executor' and 'tool' in str(span.get('metadata', {})):
                tool_runs += 1
                if span.get('status') == 'ERROR':
                    tool_failures += 1

    avg_llm_calls = total_llm_calls / total_traces
    avg_tokens = total_tokens / total_traces
    avg_completion_tokens = total_completion_tokens / total_traces
    tool_fail_rate = (tool_failures / tool_runs * 100) if tool_runs > 0 else 0.0

    # Build report
    report = []
    report.append("# Sakura Legacy Baseline Metrics Report")
    report.append(f"**Total Parsed Traces:** {total_traces}\n")
    
    report.append("## 1. Route Performance Breakdown")
    report.append("| Route | Frequency | Avg Latency (s) | Success Rate |")
    report.append("| :--- | :--- | :--- | :--- |")
    
    for r in sorted(route_counts.keys()):
        count = route_counts[r]
        freq = (count / total_traces) * 100
        avg_lat = sum(route_latencies[r]) / len(route_latencies[r]) / 1000
        succ_rate = (route_successes[r] / count) * 100
        report.append(f"| {r} | {count} ({freq:.1f}%) | {avg_lat:.2f}s | {succ_rate:.1f}% |")
        
    report.append("\n## 2. LLM Inference Metrics")
    report.append(f"- **Average LLM Calls per Request:** {avg_llm_calls:.2f}")
    report.append(f"- **Average Prompt + Completion Tokens:** {avg_tokens:.1f}")
    report.append(f"- **Average Response (Completion) Tokens:** {avg_completion_tokens:.1f}\n")
    
    report.append("## 3. Tool Execution Stability")
    report.append(f"- **Total Tool Runs:** {tool_runs}")
    report.append(f"- **Failed Tool Runs:** {tool_failures}")
    report.append(f"- **Tool Failure Rate:** {tool_fail_rate:.2f}%\n")
    
    # Save the report
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
        
    print(f"Successfully generated baseline report at {report_path}")

if __name__ == "__main__":
    generate_baseline()
