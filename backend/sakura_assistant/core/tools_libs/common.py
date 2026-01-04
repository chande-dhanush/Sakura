import os
import sys
import functools
import socket
from typing import Any

# CONSTANTS
USER_TIMEZONE = 'Asia/Kolkata'
socket.setdefaulttimeout(15) # Global timeout for safety

def log_api_call(tool_name: str, args: Any):
    print(f"[DEBUG] Calling {tool_name} with arguments: {args}")

def log_api_result(tool_name: str, result: str):
    print(f"[DEBUG] Tool {tool_name} completed successfully.")

def _validate_path(path: str) -> str:
    """
    Enforce sandbox restrictions.
    Allowed: Project Root, Notes Dir.
    Blocked: System files, Parent directory traversal (..).
    """
    # Fix import path for config (3 levels up: core/tools_libs -> core -> sakura_assistant -> config)
    try:
        from ...config import get_project_root, get_note_root
    except ImportError:
        # Fallback if running relative
        from sakura_assistant.config import get_project_root, get_note_root
    
    # Normalize
    abs_path = os.path.abspath(path)
    project_root = os.path.abspath(get_project_root())
    note_root = os.path.abspath(get_note_root())
    
    # 1. Check for directory traversal
    if ".." in path:
         raise ValueError(f"❌ Security Violation: Directory traversal detected in '{path}'")
         
    # 2. Check prefix (Allow Project Root OR Notes Root)
    if not abs_path.startswith(project_root) and not abs_path.startswith(note_root):
        raise ValueError(f"❌ Security Violation: Access to '{path}' denied (Outside Sandbox).")
        
    return abs_path

def retry_with_auth(func):
    """Decorator to retry Google API calls with re-auth if needed."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "invalid_grant" in str(e) or "Token has been expired" in str(e):
                print("🔄 Token expired. Please re-authenticate.")
                return "❌ Auth token expired. Please restart to re-login."
            return func(*args, **kwargs) # Retry once or fail
    return wrapper

# --- Google Auth Helper ---

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]

def get_google_creds():
    """Get valid Google Credentials."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        print("❌ Google Libs not available.")
        return None

    try:
        from ...config import get_project_root
    except ImportError:
        from sakura_assistant.config import get_project_root

    creds = None
    token_path = os.path.join(get_project_root(), 'token.json')
    
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            print(f"⚠️ Error loading token from {token_path}: {e}")
            creds = None
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                # print("🔄 Refreshing Google Token...")
                creds.refresh(Request())
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                print(f"⚠️ Token refresh failed: {e}")
        else:
            # print(f"❌ No valid token found at {token_path}")
            pass
            
    return creds
