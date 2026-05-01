#!/usr/bin/env python3
"""Sakura V19.5 Master Audit Runner"""
import subprocess
import sys
import os
from pathlib import Path

# Fix Windows Unicode
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

SCRIPTS = [
    "audit_v15.py", "audit_brain.py", "audit_speed.py", "audit_tokens.py",
    "audit_chaos.py", "audit_leak.py", "audit_rag.py", "audit_planner_strictness.py",
    "audit_security.py", "audit_prompt_injection.py", "audit_reliability.py",
    "audit_performance.py", "audit_observability.py", "audit_ai_behavior.py",
    "audit_integration.py"
]

def run_audit(script):
    """Run single audit with timeout"""
    print(f"\n🧪 {script}")
    try:
        result = subprocess.run(
            [sys.executable, f"{script}"], 
            cwd=".", timeout=120, capture_output=True, text=True, encoding='utf-8'
        )
        output = result.stdout + "\n" + result.stderr
        if result.returncode == 0:
            print("✅ PASS")
            return "PASS", output
        else:
            print(f"❌ FAIL: {result.stderr[:200]}...")
            return "FAIL", output
    except subprocess.TimeoutExpired:
        print("⏰ TIMEOUT")
        return "TIMEOUT", "Execution timed out after 120s"
    except Exception as e:
        print(f"💥 ERROR: {e}")
        return "ERROR", str(e)

def filter_output(text):
    """Remove repetitive status noise from the report"""
    noisy_patterns = [
        "[State] Message queued:",
        "[State] Visibility:",
        "[WorldGraph] Recorded action:",
        "[WorldGraph] Created entity:",
        "[WorldGraph] Deleted entity:",
        "[WorldGraph] Update response:",
    ]
    lines = text.splitlines()
    filtered = []
    skipped_count = 0
    for line in lines:
        if any(p in line for p in noisy_patterns):
            skipped_count += 1
            continue
        filtered.append(line)
    
    if skipped_count > 0:
        filtered.append(f"\n[INFO] Trimmed {skipped_count} lines of repetitive status messages.")
    return "\n".join(filtered)

results = {"pass": 0, "fail": 0, "error": 0, "timeout": 0, "total": len(SCRIPTS)}
report_data = []

for script in SCRIPTS:
    status, output = run_audit(script)
    results[status.lower()] += 1
    report_data.append((script, status, filter_output(output)))

# ==================================================
# GENERATE REPORT
# ==================================================
report_path = Path("audit_artifacts/audit_report.md")
report_path.parent.mkdir(exist_ok=True)

with open(report_path, "w", encoding="utf-8") as f:
    f.write("# Sakura V19.5 Master Audit Report\n\n")
    f.write(f"**Date:** {Path('.').absolute()}\n")
    f.write(f"**Status:** {'✅ PASS' if results['pass'] == results['total'] else '❌ FAIL'}\n\n")
    
    f.write("## Summary\n\n")
    f.write("| Script | Status |\n")
    f.write("| :--- | :--- |\n")
    for script, status, _ in report_data:
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "💥"
        f.write(f"| {script} | {icon} {status} |\n")
    
    f.write(f"\n**Total:** {results['pass']}/{results['total']} PASS\n")
    
    grade = "A+" if results['pass'] == results['total'] else "A" if results['pass'] >= 13 else "B"
    f.write(f"**Grade:** {grade}\n\n")

    f.write("## Detailed Results\n\n")
    f.write("> [!NOTE]\n")
    f.write("> Repetitive status messages (Message queued, Visibility updates, etc.) have been trimmed for readability.\n\n")
    
    for script, status, output in report_data:
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "💥"
        f.write(f"### {icon} {script}\n")
        f.write("```text\n")
        f.write(output.strip() + "\n")
        f.write("```\n\n")

print("\n" + "="*50)
print("SAKURA V19.5 AUDIT SUMMARY")
print("="*50)
print(f"✅ PASS:  {results['pass']}/{results['total']}")
print(f"❌ FAIL:  {results['fail']}")
print(f"💥 ERROR:{results['error']}")
print(f"⏰ TIMEOUT: {results['timeout']}")

grade = "A+" if results['pass'] == results['total'] else "A" if results['pass'] >= 13 else "B"
print(f"🎓 GRADE: {grade}")

if results['pass'] == results['total']:
    print("🚀 PRODUCTION READY — SHIP IT!")
    print(f"📄 Trimmed Report generated: {report_path}")
else:
    print("🔧 Fix remaining failures")
