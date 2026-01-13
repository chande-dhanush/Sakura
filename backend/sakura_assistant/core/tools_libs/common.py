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
    
    Allowed directories:
    - Project Root and Notes Dir
    - User's Documents, Desktop, Downloads
    
    Blocked: System files, Parent directory traversal (..).
    """
    from pathlib import Path
    
    # Fix import path for config (3 levels up: core/tools_libs -> core -> sakura_assistant -> config)
    try:
        from ...config import get_project_root, get_note_root
    except ImportError:
        # Fallback if running relative
        from sakura_assistant.config import get_project_root, get_note_root
    
    # Normalize path
    abs_path = Path(path).resolve()
    
    # Define allowed directories
    ALLOWED_PATHS = [
        Path(get_project_root()).resolve(),
        Path(get_note_root()).resolve(),
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "Downloads",
    ]
    
    # 1. Check for directory traversal
    if ".." in path:
         raise ValueError(f"❌ Security Violation: Directory traversal detected in '{path}'")
    
    # 2. Check if path is within any allowed directory
    for allowed in ALLOWED_PATHS:
        try:
            abs_path.relative_to(allowed)
            return str(abs_path)
        except ValueError:
            continue
    
    raise ValueError(f"❌ Security Violation: Access to '{path}' denied (Outside Sandbox).")

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
                creds = None
                
        # Fallback to interactive login if still no valid creds
        if not creds:
             cred_path = os.path.join(get_project_root(), 'credentials.json')
             if os.path.exists(cred_path):
                 try:
                     from google_auth_oauthlib.flow import InstalledAppFlow
                     print(f"🔄 Initiating Google Auth Flow from {cred_path}...")
                     flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
                     creds = flow.run_local_server(port=0)
                     # Save the credentials for the next run
                     with open(token_path, 'w') as token:
                         token.write(creds.to_json())
                     print("✅ New token.json saved.")
                 except Exception as flow_err:
                     print(f"❌ OAuth Flow failed: {flow_err}")
                     return None
             else:
                 print(f"❌ No credentials.json found at {cred_path}")
                 return None

    return creds
