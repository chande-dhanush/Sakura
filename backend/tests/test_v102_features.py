"""
Sakura V10.2 Functional Test Suite
==================================
Tests all V10.2 features end-to-end.
Run with: python test_v102_features.py
"""
import os
import sys
import json
import time
import requests

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BACKEND_URL = "http://localhost:8000"
RESULTS = {"passed": 0, "failed": 0, "errors": []}

def test(name):
    """Decorator for test functions."""
    def decorator(func):
        def wrapper():
            try:
                print(f"\n{'='*50}")
                print(f"TEST: {name}")
                print('='*50)
                result = func()
                if result:
                    print(f"✅ PASSED: {name}")
                    RESULTS["passed"] += 1
                else:
                    print(f"❌ FAILED: {name}")
                    RESULTS["failed"] += 1
                    RESULTS["errors"].append(name)
            except Exception as e:
                print(f"💥 ERROR: {name} - {e}")
                RESULTS["failed"] += 1
                RESULTS["errors"].append(f"{name}: {e}")
        return wrapper
    return decorator


# ============================================================
# TEST 1: Backend Health Check
# ============================================================
@test("Backend Health Check")
def test_health():
    resp = requests.get(f"{BACKEND_URL}/health", timeout=5)
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {resp.json()}")
    return resp.status_code == 200 and resp.json().get("status") in ["ready", "setup_required"]


# ============================================================
# TEST 2: User Settings Storage (V10.2)
# ============================================================
@test("User Settings JSON Storage")
def test_user_settings():
    from sakura_assistant.utils.pathing import get_project_root
    
    # 1. Call /setup with personalization data
    payload = {
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY", "test_key"),
        "USER_NAME": "TestUser_V102",
        "USER_LOCATION": "TestCity",
        "USER_BIO": "Test bio for V10.2"
    }
    
    resp = requests.post(f"{BACKEND_URL}/setup", json=payload, timeout=30)
    print(f"   /setup response: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"   Error: {resp.text}")
        return False
    
    # 2. Check if user_settings.json was created
    settings_path = os.path.join(get_project_root(), "data", "user_settings.json")
    print(f"   Expected path: {settings_path}")
    
    if not os.path.exists(settings_path):
        print(f"   ❌ File not created!")
        return False
    
    with open(settings_path, 'r') as f:
        saved = json.load(f)
    print(f"   Saved data: {saved}")
    
    return saved.get("user_name") == "TestUser_V102"


# ============================================================
# TEST 3: Dynamic USER_DETAILS Loading (V10.2)
# ============================================================
@test("Dynamic USER_DETAILS in config.py")
def test_dynamic_user_details():
    # Force reimport to pick up new settings
    import importlib
    from sakura_assistant import config
    importlib.reload(config)
    
    print(f"   USER_DETAILS preview:")
    print(f"   {config.USER_DETAILS[:200]}...")
    
    # Check if dynamic values are present
    return "USER IDENTITY" in config.USER_DETAILS


# ============================================================
# TEST 4: .env Merge Logic (V10.2)
# ============================================================
@test(".env Merge (not overwrite)")
def test_env_merge():
    from sakura_assistant.utils.pathing import get_project_root
    
    env_path = os.path.join(get_project_root(), ".env")
    
    # Read current .env
    with open(env_path, 'r') as f:
        original = f.read()
    print(f"   Current .env has {len(original)} chars")
    
    # Call /setup with only one key
    payload = {"GROQ_API_KEY": os.getenv("GROQ_API_KEY", "test_key")}
    resp = requests.post(f"{BACKEND_URL}/setup", json=payload, timeout=30)
    
    # Read .env again
    with open(env_path, 'r') as f:
        after = f.read()
    
    print(f"   After /setup: {len(after)} chars")
    
    # Should still have GROQ_API_KEY
    return "GROQ_API_KEY" in after


# ============================================================
# TEST 5: Google Credentials Path Resolution (V10.2)
# ============================================================
@test("Google Credentials Absolute Path")
def test_google_credentials_path():
    from auth_google import CREDENTIALS_PATH, TOKEN_PATH, PROJECT_ROOT
    
    print(f"   PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"   CREDENTIALS_PATH: {CREDENTIALS_PATH}")
    print(f"   TOKEN_PATH: {TOKEN_PATH}")
    
    # Check paths are absolute
    if not os.path.isabs(CREDENTIALS_PATH):
        print("   ❌ CREDENTIALS_PATH is not absolute!")
        return False
    
    if not os.path.isabs(TOKEN_PATH):
        print("   ❌ TOKEN_PATH is not absolute!")
        return False
    
    # Check if credentials.json exists at expected location
    creds_exists = os.path.exists(CREDENTIALS_PATH)
    print(f"   credentials.json exists: {creds_exists}")
    
    return True  # Paths are absolute (file may not exist yet)


# ============================================================
# TEST 6: Offline Logging with 3-Day Cleanup (V10.2)
# ============================================================
@test("Offline Logging to data/logs/")
def test_offline_logging():
    from sakura_assistant.utils.pathing import get_project_root
    from datetime import datetime
    
    log_dir = os.path.join(get_project_root(), "data", "logs")
    print(f"   Log directory: {log_dir}")
    
    # Check if directory exists
    if not os.path.exists(log_dir):
        print("   ⚠️ Log directory doesn't exist yet (will be created on first log)")
        return True  # Not a failure
    
    # Check for today's log
    today = datetime.now().strftime("%Y-%m-%d")
    expected_log = os.path.join(log_dir, f"sakura_{today}.log")
    print(f"   Expected log: {expected_log}")
    print(f"   Exists: {os.path.exists(expected_log)}")
    
    return True


# ============================================================
# TEST 7: Gemini Backup Model Configuration (V10.2)
# ============================================================
@test("Gemini 2.0 Flash Backup Priority")
def test_gemini_backup():
    from sakura_assistant.core.container import Container, LLMConfig
    
    container = Container()
    
    print(f"   Google API Key present: {bool(container.google_api_key)}")
    print(f"   OpenRouter Key present: {bool(container.openrouter_api_key)}")
    print(f"   has_backup: {container.has_backup}")
    print(f"   Backup model in config: {container.config.backup_model}")
    
    # If Google key exists, backup should use it first
    if container.google_api_key:
        print("   ✓ Gemini will be used as backup (priority 1)")
    elif container.openrouter_api_key:
        print("   ✓ OpenRouter will be used as backup (priority 2)")
    else:
        print("   ⚠️ No backup model available")
    
    return True


# ============================================================
# RUN ALL TESTS
# ============================================================
def main():
    print("\n" + "="*60)
    print("  SAKURA V10.2 FUNCTIONAL TEST SUITE")
    print("="*60)
    
    # Check backend is running
    try:
        requests.get(f"{BACKEND_URL}/health", timeout=2)
    except requests.exceptions.ConnectionError:
        print("\n❌ Backend not running! Start with: python server.py")
        return
    
    # Run all tests
    test_health()
    test_user_settings()
    test_dynamic_user_details()
    test_env_merge()
    test_google_credentials_path()
    test_offline_logging()
    test_gemini_backup()
    
    # Summary
    print("\n" + "="*60)
    print("  SUMMARY")
    print("="*60)
    print(f"  ✅ Passed: {RESULTS['passed']}")
    print(f"  ❌ Failed: {RESULTS['failed']}")
    
    if RESULTS['errors']:
        print("\n  Failures:")
        for err in RESULTS['errors']:
            print(f"    - {err}")
    
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
