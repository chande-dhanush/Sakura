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

CREDENTIALS_PATH = os.path.join(PROJECT_ROOT, 'credentials.json')
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

