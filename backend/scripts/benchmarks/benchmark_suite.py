import subprocess
import time
import urllib.request
import os
import signal
from pathlib import Path

def run_benchmarks():
    print("=== Sakura Benchmark Suite ===")
    script_dir = Path(__file__).parent
    backend_dir = script_dir.parent.parent
    server_path = backend_dir / "server.py"
    
    # 1. Startup Latency Benchmark
    print("[*] Benchmarking server startup time...")
    start_time = time.perf_counter()
    
    # Start server as subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend_dir)
    env["SAKURA_PORT"] = "3211"
    proc = subprocess.Popen(
        ["python", "server.py"],
        cwd=str(backend_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    success = False
    startup_time = 0.0
    
    # Poll endpoint until ready or timeout (20s)
    for _ in range(40):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen("http://127.0.0.1:3211/health", timeout=1) as response:
                if response.status == 200:
                    startup_time = time.perf_counter() - start_time
                    print(f"[+] Server started successfully in {startup_time:.2f} seconds!")
                    success = True
                    break
        except Exception:
            # Check if subprocess died
            if proc.poll() is not None:
                print("[!] Server process terminated unexpectedly.")
                break
                
    if not success:
        print("[!] Server failed to start within timeout.")
        # Try cleaning up
        proc.terminate()
        return
        
    # 2. Idle Memory Footprint Benchmark
    print("[*] Benchmarking idle memory usage...")
    memory_mb = 0.0
    try:
        import psutil
        process = psutil.Process(proc.pid)
        # Sum memory of parent and child processes
        mem_bytes = process.memory_info().rss
        for child in process.children(recursive=True):
            mem_bytes += child.memory_info().rss
        memory_mb = mem_bytes / (1024 * 1024)
        print(f"[+] Idle Memory Footprint: {memory_mb:.2f} MB")
    except ImportError:
        # Fallback to Tasklist on Windows
        try:
            output = subprocess.check_output(f'tasklist /FI "PID eq {proc.pid}"', shell=True).decode()
            print("[+] tasklist output:")
            print(output.strip())
        except Exception as e:
            print(f"[!] Could not measure memory: {e}")
            
    # Terminate process
    print("[*] Shutting down benchmark server...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        
    # Append results to baseline_metrics.md
    report_path = backend_dir.parent / "docs" / "refactor_logs" / "baseline_metrics.md"
    if report_path.exists():
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Append benchmark section
        bench_section = (
            "\n## 4. Benchmark Performance Metrics\n"
            f"- **Server Startup Time (Health Ready):** {startup_time:.2f}s\n"
            f"- **Idle Backend RAM Usage:** {memory_mb:.2f} MB\n"
        )
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(content + bench_section)
        print(f"[+] Appended benchmark results to {report_path}")
    else:
        print(f"[!] Could not find baseline report to append results at {report_path}")

if __name__ == "__main__":
    run_benchmarks()
