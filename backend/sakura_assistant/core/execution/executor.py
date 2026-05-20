"""
Sakura Tool Executor - V20.0 (Sakura Lite - Path Validation Only)
================================================================
"""

import os
import re
import unicodedata

class SecurityError(Exception):
    """Raised when a security policy is violated."""
    pass

DANGEROUS_PATTERNS = [
    r"\.\.", r"/etc/", r"\\windows\\", r"c:\\windows", r"program files",
    r"\.ssh", r"\.bashrc", r"autostart", r"cron", r"passwd",
    r"\.zshrc", r"\.profile", r"\.bash_profile",
    r"LaunchAgent", r"LaunchDaemon",
    r"cron\.d", r"crontab", r"systemd", r"\.service$",
    r"\.aws", r"\.kube", r"\.docker",
    r"\.git-credentials", r"\.netrc", r"\.npmrc",
    r"System32", r"/usr/bin", r"/usr/local/bin",
    r"\.mozilla", r"\.chrome", r"AppData.*Local.*Google",
    r"\.config/", r"\.local/share",
]

def _sanitize_path(path: str) -> str:
    """
    V19.5 Security Sandbox.
    Prevents path traversal and normalizes unicode.
    """
    # 1. Normalize Unicode (NFKC) to prevent homograph attacks
    path = unicodedata.normalize('NFKC', path)
    
    # 2. Block dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            print(f"   [Security] Blocked path traversal attempt: {path}")
            raise SecurityError(f"Blocked dangerous path: {path[:50]}")
            
    # 3. Secure normalization
    safe_path = os.path.normpath(os.path.abspath(path))
    return safe_path

def validate_path(path: str) -> str:
    """Legacy alias for _sanitize_path."""
    return _sanitize_path(path)
