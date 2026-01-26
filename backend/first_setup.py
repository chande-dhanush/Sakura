#!/usr/bin/env python
"""
Sakura V10 - First-Time Setup Script
Run this after installing dependencies to configure:
1. Google OAuth (Gmail/Calendar access)
2. Wake Word Templates (Voice activation)
"""
import os
import sys

# Ensure we're in the backend directory
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.insert(0, script_dir)


def setup_google_auth():
    """Step 1: Google OAuth Setup"""
    print("\n" + "="*50)
    print(" STEP 1: Google OAuth Setup (Gmail/Calendar)")
    print("="*50)
    
    if os.path.exists("token.json"):
        print(" Google OAuth already configured (token.json exists)")
        choice = input("   Re-authenticate? (y/n): ").strip().lower()
        if choice != 'y':
            return True
    
    if not os.path.exists("credentials.json"):
        print("\n 'credentials.json' not found!")
        print("\nTo get this file:")
        print("1. Go to: https://console.cloud.google.com/apis/credentials")
        print("2. Create OAuth 2.0 Client ID (Desktop App)")
        print("3. Download JSON → rename to 'credentials.json'")
        print("4. Place it in the 'backend/' folder")
        print("5. Run this script again")
        return False
    
    print("\n Opening browser for Google authentication...")
    print("   (Allow access to Gmail, Calendar, and Tasks)")
    
    try:
        from auth_google import authenticate
        authenticate()
        print(" Google OAuth configured successfully!")
        return True
    except Exception as e:
        print(f" Error: {e}")
        return False


def setup_wake_word():
    """Step 2: Wake Word Template Recording"""
    print("\n" + "="*50)
    print(" STEP 2: Wake Word Setup (Voice Activation)")
    print("="*50)
    
    try:
        from sakura_assistant.utils.wake_word import (
            get_template_count, record_wake_template, save_template, TEMPLATE_DIR
        )
    except ImportError as e:
        print(f" Could not import wake_word module: {e}")
        print("   Make sure all dependencies are installed.")
        return False
    
    count = get_template_count()
    print(f" Current templates: {count}")
    
    if count >= 3:
        print(" Wake word already configured (≥3 templates)")
        choice = input("   Record more templates? (y/n): ").strip().lower()
        if choice != 'y':
            return True
    
    print("\n For best results, record 3-5 templates of you saying 'Sakura'")
    print("   Say it naturally at your normal volume.")
    print(f"   Templates saved to: {TEMPLATE_DIR}\n")
    
    while True:
        choice = input("Record a template? (y/n): ").strip().lower()
        if choice != 'y':
            break
        
        input("Press Enter when ready, then say 'Sakura'...")
        
        mfcc = record_wake_template(duration=1.5)
        if mfcc is not None:
            name = f"sakura_{get_template_count() + 1}"
            if save_template(mfcc, name):
                print(f" Saved template: {name}")
            else:
                print(" Failed to save template")
        else:
            print(" Recording failed - check your microphone")
    
    final_count = get_template_count()
    if final_count >= 2:
        print(f"\n Wake word configured with {final_count} templates!")
        return True
    else:
        print(f"\n⚠️ Only {final_count} template(s). Voice activation may be unreliable.")
        print("   Re-run setup to add more templates.")
        return False


def main():
    print(" Sakura V10 - First-Time Setup")
    print("================================\n")
    
    # Step 1: Google Auth
    google_ok = setup_google_auth()
    
    # Step 2: Wake Word
    wake_ok = setup_wake_word()
    
    # Summary
    print("\n" + "="*50)
    print(" SETUP SUMMARY")
    print("="*50)
    print(f"Google OAuth:  {' Configured' if google_ok else ' Not configured'}")
    print(f"Wake Word:     {' Configured' if wake_ok else '⚠️ No templates'}")
    
    if google_ok and wake_ok:
        print("\n All done! You can now run Sakura:")
        print("   cd frontend")
        print("   npm run tauri dev")
    else:
        print("\n⚠️ Some features are not configured.")
        print("   Re-run this script after fixing the issues above.")


if __name__ == "__main__":
    main()
