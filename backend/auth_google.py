import os
import sys

# Add parent to path if running as standalone script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Use absolute paths - CWD varies depending on how app is launched
try:
    from sakura_assistant.utils.pathing import get_project_root
    PROJECT_ROOT = get_project_root()
except ImportError:
    # Fallback for standalone script execution
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# V10.3: Multi-location fallback for credentials.json
# In frozen mode, credentials might be in different locations
def _resolve_credentials_path():
    """Find credentials.json with fallback locations and detailed logging."""
    possible_paths = [
        os.path.join(PROJECT_ROOT, 'credentials.json'),  # APPDATA or project root
    ]
    
    # If frozen (sidecar), check additional locations
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        possible_paths.extend([
            os.path.join(exe_dir, 'credentials.json'),           # Next to .exe
            os.path.join(exe_dir, '..', 'credentials.json'),     # Parent of .exe
        ])
    else:
        # Dev mode: check script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths.append(os.path.join(script_dir, 'credentials.json'))
    
    # Log where we're looking (helps debug frozen mode)
    print(f"[AUTH] Searching for credentials.json in:")
    for i, path in enumerate(possible_paths, 1):
        exists = os.path.exists(path)
        status = "FOUND" if exists else "not found"
        print(f"   {i}. {path} [{status}]")
        if exists:
            return path
    
    # Return default (will fail later with helpful error)
    return possible_paths[0]

CREDENTIALS_PATH = _resolve_credentials_path()
TOKEN_PATH = os.path.join(PROJECT_ROOT, 'token.json')

# Scopes must match tools.py
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]

def authenticate():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("🚀 Starting new authentication flow...")
            if not os.path.exists(CREDENTIALS_PATH):
                print(f"❌ Error: 'credentials.json' not found!")
                print(f"   Expected location: {CREDENTIALS_PATH}")
                print("1. Go to Google Cloud Console.")
                print("2. Create OAuth 2.0 Client ID (Desktop App).")
                print("3. Download JSON and rename it to 'credentials.json'.")
                print(f"4. Place it in: {PROJECT_ROOT}")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
            print(f"✅ Authentication successful! Token saved to: {TOKEN_PATH}")
    
    return creds

if __name__ == '__main__':
    authenticate()

