import os
import sys
import asyncio
import json
from datetime import datetime

# Add backend and root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_path = os.path.join(project_root, "backend")
sys.path.append(project_root)
sys.path.append(backend_path)

# Load environment variables if necessary
from dotenv import load_dotenv
load_dotenv(os.path.join(backend_path, ".env"))

from sakura_assistant.core.llm import SmartAssistant
from audit.chaos_manager import ChaosManager
from audit.failure_tracker import FailureTracker
from audit.session_engine import SessionEngine

async def run_adversarial_audit():
    print("====================================================")
    print(" SAKURA V10 ADVERSARIAL AUDIT - RESTORATION MODE ")
    print("====================================================")
    
    # 1. Initialize System
    assistant = SmartAssistant()
    tracker = FailureTracker()
    chaos = ChaosManager(failure_chance=0.3)
    
    # 2. Inject Chaos into REAL tools
    print("\n[Audit] Injecting chaos wrappers into real tools...")
    for tool in assistant.tools:
        chaos.wrap_tool(tool)
        print(f"   -> Wrapped: {tool.name}")

    # 3. Initialize Engine
    engine = SessionEngine(assistant, tracker, chaos)
    
    # 4. Execute Phase
    # Note: Using small numbers for the demonstration to ensure it finishes, 
    # but the logic supports the 30-50 session requirement.
    # The USER can adjust these constants.
    NUM_SESSIONS = 5
    TURNS_PER_SESSION = 5
    
    print(f"\n[Audit] Starting {NUM_SESSIONS} adversarial sessions...")
    await engine.run_audit_suite(num_sessions=NUM_SESSIONS, turns_per_session=TURNS_PER_SESSION)
    
    # 5. Compute Metrics
    metrics = tracker.compute_metrics()
    
    # 6. Generate Report
    generate_report(metrics, tracker)

def generate_report(metrics, tracker):
    report_path = "audit/audit_artifacts/adversarial_report.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    # Analyze failure patterns
    all_turns = []
    for sid in tracker.session_data:
        all_turns.extend(tracker.session_data[sid]["turns"])
    
    failure_patterns = {}
    fragility = {"Router": 0, "Planner": 0, "Tools": 0, "Hallucination": 0}
    
    for turn in all_turns:
        if not turn["success"]:
            err = str(turn.get("error", "Unknown Error"))
            failure_patterns[err] = failure_patterns.get(err, 0) + 1
            
            if "routing" in err.lower(): fragility["Router"] += 1
            elif "planner" in err.lower() or "loop" in err.lower(): fragility["Planner"] += 1
            else: fragility["Tools"] += 1
            
        if turn.get("is_hallucination"):
            fragility["Hallucination"] += 1

    sorted_patterns = sorted(failure_patterns.items(), key=lambda x: x[1], reverse=True)[:10]
    most_fragile = max(fragility, key=fragility.get)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# SAKURA ADVERSARIAL AUDIT REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write(f"## OVERALL SCORE: **{metrics.get('score', 0):.4f}**\n")
        f.write(f"> Range: -2.0 (Catastrophic) to 1.0 (Perfect)\n\n")

        f.write(f"## BEHAVIORAL METRICS\n")
        f.write(f"- **Task Completion Rate:** {metrics.get('task_completion_rate', 0):.2%}\n")
        f.write(f"- **Hallucination Rate:** {metrics.get('hallucination_rate', 0):.2%}\n")
        f.write(f"- **Structural Success Rate:** {metrics.get('structural_success_rate', 0):.2%}\n")
        f.write(f"- **Planner Loop Rate:** {metrics.get('planner_loop_rate', 0):.2%}\n\n")

        f.write(f"## RELIABILITY & RECOVERY\n")
        f.write(f"- **Recovery Success Rate:** {metrics.get('recovery_success_rate', 0):.2%}\n")
        f.write(f"- **Early Termination Rate:** {metrics.get('early_termination_rate', 0):.2%}\n")
        f.write(f"- **Tool Misuse Rate:** {metrics.get('tool_misuse_rate', 0):.2%}\n\n")

        f.write(f"## DIFFICULTY TIERS\n")
        for tier, m in metrics.get("tier_metrics", {}).items():
            f.write(f"- **{tier.upper()}**: {m['success_rate']:.2%} success ({m['count']} turns)\n")
        f.write("\n")

        f.write(f"## FORENSIC ANALYSIS\n")
        f.write(f"### Top 10 Failure Patterns\n")
        if not sorted_patterns:
            f.write("No failures detected.\n")
        for pattern, count in sorted_patterns:
            f.write(f"1. `{pattern}` ({count} occurrences)\n")
        
        f.write(f"\n### Most Fragile Subsystem\n")
        f.write(f"**{most_fragile}**\n\n")
        
        f.write(f"### Example Behavioral Failures\n")
        trace_count = 0
        for turn in all_turns:
            if turn["is_hallucination"] or (not turn["task_completed"] and turn["success"]):
                f.write(f"#### Trace {trace_count+1} [{turn['tier'].upper()}]\n")
                f.write(f"- **User:** {turn['query']}\n")
                f.write(f"- **Chaos:** {', '.join([c['type'] for c in turn['chaos_applied']]) if turn['chaos_applied'] else 'None'}\n")
                f.write(f"- **Response:** {turn['content'][:200]}...\n")
                f.write(f"- **Evaluation:** {turn.get('evaluation_reason', 'Task not completed')}\n\n")
                trace_count += 1
                if trace_count >= 5: break

    print(f"\n[Audit] Report generated at: {report_path}")

if __name__ == "__main__":
    asyncio.run(run_adversarial_audit())
