# audit_aggregate.py
import json, glob, os
from pathlib import Path
from datetime import datetime

RESULTS_DIR = "audit/results"
os.makedirs(RESULTS_DIR, exist_ok=True)
all_results = []

for f in sorted(glob.glob(f"{RESULTS_DIR}/*.json")):
    if "FULL_AUDIT_REPORT" in f: continue
    with open(f, encoding="utf-8-sig") as fh:
        try:
            data = json.load(fh)
            all_results.append(data)
        except Exception as e:
            print(f"Error loading {f}: {e}")
            continue

total_checks = sum(len(r.get("checks", [])) for r in all_results)
passed = sum(
    1 for r in all_results 
    for c in r.get("checks", []) 
    if c.get("passed") is True
)
failed = sum(
    1 for r in all_results 
    for c in r.get("checks", []) 
    if c.get("passed") is False
)
warnings = sum(
    1 for r in all_results 
    for c in r.get("checks", []) 
    if c.get("passed") not in (True, False)
)

critical_fails = [
    c.get("name") for r in all_results 
    for c in r.get("checks", []) 
    if c.get("passed") is False and c.get("severity") == "CRITICAL"
]
high_fails = [
    c.get("name") for r in all_results 
    for c in r.get("checks", []) 
    if c.get("passed") is False and c.get("severity") == "HIGH"
]

summary = {
    "project": "Sakura V19.5",
    "audit_date": datetime.now().isoformat(),
    "total_checks": total_checks,
    "passed": passed,
    "failed": failed,
    "warnings": warnings,
    "pass_rate": f"{round(passed/total_checks*100, 1)}%" if total_checks else "0%",
    "critical_failures": critical_fails,
    "high_failures": high_fails,
    "categories": {r.get("category", "unknown"): {
        "passed": sum(1 for c in r.get("checks",[]) if c.get("passed") is True),
        "failed": sum(1 for c in r.get("checks",[]) if c.get("passed") is False),
        "total": len(r.get("checks",[]))
    } for r in all_results},
    "full_results": all_results
}

with open(f"{RESULTS_DIR}/FULL_AUDIT_REPORT.json", "w") as f:
    json.dump(summary, f, indent=2)

print(json.dumps(summary, indent=2))
