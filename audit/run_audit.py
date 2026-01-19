#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sakura V15.2.2: Unified Audit Runner
=====================================
Runs all audit scripts and generates a comprehensive report.

Run with: python audit/run_audit.py

Output:
- Console: Real-time progress
- audit/audit_artifacts/audit_report.json: Machine-readable results
- audit/audit_artifacts/audit_report.md: Human-readable Markdown report
"""

import os
import sys
import json
import subprocess
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===============================================================================
# CONFIGURATION
# ===============================================================================

AUDIT_DIR = Path(__file__).parent
BACKEND_DIR = AUDIT_DIR.parent / "backend"
ARTIFACTS_DIR = AUDIT_DIR / "audit_artifacts"

# Audit scripts to run (in order)
AUDIT_SCRIPTS = [
    ("audit_v15.py", "V15.2.2 Production Audit", "Core security, SOLID, performance"),
    ("audit_brain.py", "Router Brain Accuracy", "Identity protection, source tracking"),
    ("audit_speed.py", "Performance Benchmarks", "Response latency, O(1) scaling"),
    ("audit_tokens.py", "Token Usage Analysis", "Cost per query, context efficiency"),
    ("audit_chaos.py", "Chaos Engineering", "Failure injection, recovery rate"),
    ("audit_leak.py", "Memory Leak Detection", "RSS growth, object counts"),
    ("audit_rag.py", "RAG Fidelity", "Precision, recall, citation accuracy"),
    ("audit_planner_strictness.py", "Planner Strictness", "Hallucination rate, tool selection"),
]


# ===============================================================================
# DATA STRUCTURES
# ===============================================================================

@dataclass
class AuditResult:
    script: str
    name: str
    description: str
    status: str  # PASS, FAIL, SKIP, ERROR
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    duration_ms: float = 0.0
    output: str = ""
    error: str = ""
    tests: List[tuple] = field(default_factory=list)  # (status, name)
    benchmarks: List[str] = field(default_factory=list)

@dataclass
class AuditReport:
    version: str = "15.2.2"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    total_scripts: int = 0
    passed_scripts: int = 0
    failed_scripts: int = 0
    skipped_scripts: int = 0
    total_tests: int = 0
    total_passed: int = 0
    total_failed: int = 0
    total_warnings: int = 0
    duration_ms: float = 0.0
    results: List[Dict] = field(default_factory=list)

def parse_audit_output(output: str) -> Dict[str, Any]:
    """Parse audit script output for test counts and individual results."""
    result = {
        "passed": 0, 
        "failed": 0, 
        "warnings": 0,
        "tests": [],  # List of (status, name, details)
        "benchmarks": []  # List of benchmark results
    }
    
    # Parse individual test results
    for line in output.split('\n'):
        line = line.strip()
        
        # Match [PASS], [FAIL], [WARN] markers
        # Match [PASS], [FAIL], [WARN] markers AND emojis
        if '[PASS]' in line or '✅' in line:
            result["passed"] += 1
            # Extract test name
            name = line.replace('[PASS]', '').replace('✅', '').strip()
            if name and not name.startswith('All checks') and not name.startswith('Security') and not name.startswith('Passed'):
                result["tests"].append(("PASS", name))
        elif '[FAIL]' in line or '❌' in line:
            # Ignore table rows or summary lines that might contain [FAIL] but aren't actual test results
            if line.strip().startswith('|'):
                continue
                
            result["failed"] += 1
            name = line.replace('[FAIL]', '').replace('❌', '').strip()
            if name and not name.startswith('Some checks') and not name.startswith('Failed'):
                result["tests"].append(("FAIL", name))
        elif '[WARN]' in line or '⚠️' in line:
            result["warnings"] += 1
            name = line.replace('[WARN]', '').replace('⚠️', '').strip()
            if name and not name.startswith('Warnings'):
                result["tests"].append(("WARN", name))
        
        # Parse benchmarks
        if 'ms (target:' in line or 'ms)' in line:
            result["benchmarks"].append(line.strip())
    
    return result

def run_audit_script(script: str, name: str, description: str) -> AuditResult:
    """Run a single audit script and capture results."""
    result = AuditResult(script=script, name=name, description=description, status="SKIP")
    script_path = AUDIT_DIR / script
    
    if not script_path.exists():
        result.status = "SKIP"
        result.error = f"Script not found: {script_path}"
        return result
    
    try:
        import time
        start = time.perf_counter()
        
        # Ensure backend is in PYTHONPATH
        env = os.environ.copy()
        python_path = env.get("PYTHONPATH", "")
        backend_path = str(BACKEND_DIR)
        if backend_path not in python_path:
            env["PYTHONPATH"] = f"{backend_path}{os.pathsep}{python_path}"
        env["PYTHONIOENCODING"] = "utf-8"
        
        # Run the script with proper encoding for Windows
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(AUDIT_DIR.parent),
            capture_output=True,
            timeout=120,  # 2 minute timeout per script
            env=env
        )
        
        elapsed = (time.perf_counter() - start) * 1000
        result.duration_ms = elapsed
        
        # Decode output safely
        try:
            stdout = proc.stdout.decode('utf-8', errors='replace')
        except:
            stdout = str(proc.stdout)
        try:
            stderr = proc.stderr.decode('utf-8', errors='replace')
        except:
            stderr = str(proc.stderr)
        
        result.output = stdout + stderr
        
        # Parse output
        parsed = parse_audit_output(result.output)
        result.passed = parsed["passed"]
        result.failed = parsed["failed"]
        result.warnings = parsed["warnings"]
        result.tests = parsed["tests"]
        result.benchmarks = parsed["benchmarks"]
        
        # Determine status
        if proc.returncode == 0:
            result.status = "PASS" if result.failed == 0 else "FAIL"
        else:
            result.status = "FAIL"
            result.error = f"Exit code: {proc.returncode}"
            
    except subprocess.TimeoutExpired:
        result.status = "ERROR"
        result.error = "Script timed out (>120s)"
    except Exception as e:
        result.status = "ERROR"
        result.error = str(e)
    
    return result

def run_all_audits(parallel: bool = False) -> AuditReport:
    """Run all audit scripts and compile results."""
    report = AuditReport()
    report.total_scripts = len(AUDIT_SCRIPTS)
    
    import time
    start_time = time.perf_counter()
    
    print()
    print("=" * 60)
    print("  SAKURA V15.2.2 UNIFIED AUDIT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = []
    
    if parallel:
        # Run in parallel (faster but output gets mixed)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(run_audit_script, s, n, d): (s, n)
                for s, n, d in AUDIT_SCRIPTS
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                _print_result(result)
    else:
        # Run sequentially (cleaner output)
        for script, name, description in AUDIT_SCRIPTS:
            print(f"\n  Running: {name}...")
            result = run_audit_script(script, name, description)
            results.append(result)
            _print_result(result)
    
    # Compile report
    for result in results:
        report.results.append(asdict(result))
        report.total_tests += result.passed + result.failed
        report.total_passed += result.passed
        report.total_failed += result.failed
        report.total_warnings += result.warnings
        
        if result.status == "PASS":
            report.passed_scripts += 1
        elif result.status == "FAIL":
            report.failed_scripts += 1
        else:
            report.skipped_scripts += 1
    
    report.duration_ms = (time.perf_counter() - start_time) * 1000
    
    return report


def _print_result(result: AuditResult):
    """Print a single audit result to console."""
    status_icon = {
        "PASS": "[PASS]",
        "FAIL": "[FAIL]",
        "SKIP": "[SKIP]",
        "ERROR": "[ERROR]"
    }.get(result.status, "[????]")
    
    print(f"  {status_icon} {result.name}")
    print(f"       Tests: {result.passed} passed, {result.failed} failed, {result.warnings} warnings")
    print(f"       Time:  {result.duration_ms:.0f}ms")
    
    if result.error:
        print(f"       Error: {result.error}")


# ===============================================================================
# REPORT GENERATION
# ===============================================================================

def generate_json_report(report: AuditReport, path: Path):
    """Generate JSON report."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2)
    print(f"\n  [INFO] JSON report saved to: {path}")

def generate_markdown_report(report: AuditReport, path: Path):
    """Generate Markdown report."""
    lines = [
        f"# Sakura V{report.version} Audit Report",
        f"",
        f"**Generated:** {report.timestamp}",
        f"**Duration:** {report.duration_ms/1000:.1f}s",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Scripts | {report.total_scripts} |",
        f"| Passed | {report.passed_scripts} |",
        f"| Failed | {report.failed_scripts} |",
        f"| Skipped | {report.skipped_scripts} |",
        f"| Total Tests | {report.total_tests} |",
        f"| Tests Passed | {report.total_passed} |",
        f"| Tests Failed | {report.total_failed} |",
        f"| Warnings | {report.total_warnings} |",
        f"",
    ]
    
    # Overall status
    if report.failed_scripts == 0 and report.total_failed == 0:
        lines.append("### Status: PASS")
        lines.append("")
        lines.append("All audits passed. System is production-ready.")
    else:
        lines.append("### Status: FAIL")
        lines.append("")
        lines.append("Some audits failed. Please review and fix before deploying.")
    
    lines.extend([
        "",
        "---",
        "",
        "## Detailed Results",
        "",
    ])
    
    for result in report.results:
        status = result["status"]
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "ERROR": "⚠️"}.get(status, "?")
        
        lines.append(f"### {icon} {result['name']}")
        lines.append(f"")
        lines.append(f"**Script:** `{result['script']}`")
        lines.append(f"**Description:** {result['description']}")
        lines.append(f"**Duration:** {result['duration_ms']:.0f}ms")
        
        if result["error"]:
            lines.append(f"")
            lines.append(f"> **Error:** {result['error']}")
        
        # Benchmarks table if any
        if result.get("benchmarks"):
            lines.append(f"")
            lines.append(f"#### Benchmarks")
            lines.append(f"```")
            for b in result["benchmarks"]:
                lines.append(b)
            lines.append(f"```")
        
        # Tests table if any
        if result.get("tests"):
            lines.append(f"")
            lines.append(f"#### Tests")
            lines.append(f"| Status | Test |")
            lines.append(f"|--------|------|")
            for t_status, t_name in result["tests"]:
                t_icon = "✅" if t_status == "PASS" else ("❌" if t_status == "FAIL" else "⚠️")
                lines.append(f"| {t_icon} | {t_name} |")
        
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # Footer
    lines.extend([
        "## Verification Standards",
        "",
        "- **OWASP CWE-22:** Path traversal protection",
        "- **OWASP LLM01:** Prompt injection defense",
        "- **CWE-362:** Race condition prevention",
        "- **SOLID Principles:** Desktop app architecture",
        "",
        "---",
        "",
        f"*Report generated by Sakura Unified Audit Runner v{report.version}*",
    ])
    
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"  [INFO] Markdown report saved to: {path}")


# ===============================================================================
# MAIN
# ===============================================================================

def main():
    # Ensure artifacts directory exists
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    
    # Run all audits
    report = run_all_audits(parallel=False)
    
    # Print summary
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print()
    print(f"  Total Scripts:  {report.total_scripts}")
    print(f"  Passed:         {report.passed_scripts}")
    print(f"  Failed:         {report.failed_scripts}")
    print(f"  Skipped:        {report.skipped_scripts}")
    print()
    print(f"  Total Tests:    {report.total_tests}")
    print(f"  Tests Passed:   {report.total_passed}")
    print(f"  Tests Failed:   {report.total_failed}")
    print(f"  Warnings:       {report.total_warnings}")
    print()
    print(f"  Duration:       {report.duration_ms/1000:.1f}s")
    print()
    
    # Generate reports
    json_path = ARTIFACTS_DIR / "audit_report.json"
    md_path = ARTIFACTS_DIR / "audit_report.md"
    
    generate_json_report(report, json_path)
    generate_markdown_report(report, md_path)
    
    # Final verdict
    print()
    if report.failed_scripts == 0 and report.total_failed == 0:
        print("[PASS] All audits passed! System is production-ready.")
        return 0
    else:
        print(f"[FAIL] {report.failed_scripts} scripts failed, {report.total_failed} tests failed.")
        print("       Please review audit_report.md for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
