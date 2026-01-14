"""
Sakura V13 Code Interpreter Tool
================================
Execute Python code in an isolated Docker container.

Security:
- No network access
- 512MB RAM limit
- 30s timeout
- Non-root user
- Whitelisted packages only

Pre-installed packages: pandas, numpy, matplotlib, seaborn, scipy, sympy
"""

import os
import uuid
import tempfile
import subprocess
import json
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

# Configuration
DOCKER_IMAGE = "sakura-python-sandbox:latest"
DEFAULT_TIMEOUT = 30
MAX_OUTPUT_CHARS = 8000  # Prevent context overflow
SANDBOX_MEMORY_LIMIT = "512m"

# Path to uploads directory (shared with sandbox)
def get_uploads_dir() -> Path:
    """Get the uploads directory path."""
    from sakura_assistant.utils.pathing import get_project_root
    uploads = Path(get_project_root()) / "uploads"
    uploads.mkdir(exist_ok=True)
    return uploads


def _check_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _check_sandbox_image() -> bool:
    """Check if the sandbox image exists, build if needed."""
    try:
        result = subprocess.run(
            ["docker", "images", "-q", DOCKER_IMAGE],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.stdout.strip():
            return True
        
        # Image doesn't exist, try to build it
        dockerfile_path = Path(__file__).parent.parent.parent.parent / "docker" / "python-sandbox.Dockerfile"
        if not dockerfile_path.exists():
            return False
        
        print(f"🔧 Building sandbox image from {dockerfile_path}...")
        build_result = subprocess.run(
            [
                "docker", "build",
                "-f", str(dockerfile_path),
                "-t", DOCKER_IMAGE,
                str(dockerfile_path.parent)
            ],
            capture_output=True,
            text=True,
            timeout=300  # 5 min build timeout
        )
        return build_result.returncode == 0
        
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"❌ Docker image check failed: {e}")
        return False


def _sanitize_code(code: str) -> str:
    """
    Basic sanitization of code.
    Note: The sandbox provides the real security, this is just a first pass.
    """
    # Remove any attempts to escape the sandbox
    dangerous_patterns = [
        "os.system",
        "subprocess",
        "__import__",
        "eval(",
        "exec(",
        "open('/",  # Attempt to read system files
        "open(\"/"
    ]
    
    for pattern in dangerous_patterns:
        if pattern in code:
            # Log but don't block - Docker sandbox is the real protection
            print(f"⚠️ Code contains potentially dangerous pattern: {pattern}")
    
    return code


@tool
def execute_python(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
    data_file: Optional[str] = None
) -> str:
    """
    Execute Python code in an isolated Docker sandbox.
    
    Use this for:
    - Data analysis (pandas, numpy)
    - Calculations and math (scipy, sympy)
    - Creating visualizations (matplotlib, seaborn)
    - Processing uploaded files (CSV, JSON, etc.)
    
    Args:
        code: Python code to execute. Print outputs to see results.
        timeout: Max execution time in seconds (default 30, max 60).
        data_file: Optional filename from uploads/ to mount (e.g., "data.csv").
    
    Returns:
        stdout/stderr from execution, or error message.
    
    Example:
        code="import pandas as pd; df = pd.DataFrame({'a': [1,2,3]}); print(df.sum())"
    
    Available packages: pandas, numpy, matplotlib, seaborn, scipy, sympy
    
    IMPORTANT: To see output, use print() statements.
    For plots, save to /code/output.png and it will be returned.
    """
    # Clamp timeout
    timeout = min(max(timeout, 5), 60)
    
    # Check Docker availability
    if not _check_docker_available():
        return "Error: Docker is not available. Please ensure Docker Desktop is running."
    
    # Ensure sandbox image exists
    if not _check_sandbox_image():
        return "Error: Failed to build or find sandbox image. Check Docker logs."
    
    # Sanitize code
    code = _sanitize_code(code)
    
    # Create temporary directory for code and output
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Write code to file
        script_path = tmpdir_path / "script.py"
        script_path.write_text(code, encoding="utf-8")
        
        # Prepare Docker command
        docker_cmd = [
            "docker", "run",
            "--rm",  # Remove container after execution
            "--network", "none",  # No network access
            "--memory", SANDBOX_MEMORY_LIMIT,
            "--cpus", "1",  # Limit CPU
            "--read-only",  # Read-only root filesystem
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",  # Writable /tmp
            "-v", f"{tmpdir_path}:/code:rw",  # Mount code directory
        ]
        
        # Mount data file if specified
        if data_file:
            uploads_dir = get_uploads_dir()
            data_path = uploads_dir / data_file
            if data_path.exists():
                docker_cmd.extend(["-v", f"{data_path}:/data/{data_file}:ro"])
            else:
                return f"Error: Data file '{data_file}' not found in uploads."
        
        # Add image and command
        docker_cmd.extend([
            DOCKER_IMAGE,
            "python", "/code/script.py"
        ])
        
        try:
            # Execute with timeout
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir
            )
            
            # Collect output
            output = ""
            
            if result.stdout:
                output += result.stdout
            
            if result.stderr:
                if output:
                    output += "\n--- STDERR ---\n"
                output += result.stderr
            
            if result.returncode != 0 and not output:
                output = f"Execution failed with return code {result.returncode}"
            
            if not output:
                output = "(No output - did you forget to print() your results?)"
            
            # Check for generated plot
            plot_path = tmpdir_path / "output.png"
            if plot_path.exists():
                # Save plot to uploads for potential display
                import shutil
                output_name = f"plot_{uuid.uuid4().hex[:8]}.png"
                dest_path = get_uploads_dir() / output_name
                shutil.copy(plot_path, dest_path)
                output += f"\n\n📊 Plot saved: {output_name}"
            
            # Truncate if too long
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + f"\n\n... (truncated, {len(output) - MAX_OUTPUT_CHARS} chars omitted)"
            
            return output
            
        except subprocess.TimeoutExpired:
            return f"Error: Execution timed out after {timeout} seconds."
        
        except Exception as e:
            return f"Error executing code: {str(e)}"


@tool
def check_code_interpreter_status() -> str:
    """
    Check if the Code Interpreter is ready to use.
    
    Returns status of Docker and sandbox image.
    """
    status = {
        "docker_available": _check_docker_available(),
        "sandbox_image_ready": False,
        "uploads_dir": str(get_uploads_dir()),
        "available_packages": [
            "pandas", "numpy", "matplotlib", 
            "seaborn", "scipy", "sympy"
        ]
    }
    
    if status["docker_available"]:
        status["sandbox_image_ready"] = _check_sandbox_image()
    
    if status["docker_available"] and status["sandbox_image_ready"]:
        return f"""✅ Code Interpreter is ready!

Docker: Running
Sandbox Image: {DOCKER_IMAGE}
Uploads Directory: {status['uploads_dir']}
Available Packages: {', '.join(status['available_packages'])}

Use execute_python() to run code."""
    
    elif not status["docker_available"]:
        return "❌ Docker is not available. Please start Docker Desktop."
    
    else:
        return "⚠️ Sandbox image not ready. It will be built on first use."


# Export tools for registration
CODE_INTERPRETER_TOOLS = [execute_python, check_code_interpreter_status]
