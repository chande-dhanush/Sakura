"""
Sakura V9.1 - Complete System Reset
====================================
Wipes ALL persistent data and gives Yuki a fresh start.

Usage:
    python tools/system_reset.py

PROTECTED (never deleted):
    - .env, config.json, credentials.json, token.json
    - requirements.txt, DOCUMENTATION.md, README.md
    - Source code (sakura_assistant/)
    - Notes/ folder
"""
import os
import shutil
import glob

# Base paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
SAKURA_DATA = os.path.join(PROJECT_ROOT, "sakura_assistant", "data")

# Files to delete
FILES_TO_DELETE = [
    # Conversation & History
    os.path.join(DATA_DIR, "conversation_history.json"),
    os.path.join(DATA_DIR, "memory.db"),
    os.path.join(DATA_DIR, "files.db"),
    
    # V7+ World Graph
    os.path.join(DATA_DIR, "world_graph.json"),
    
    # V8 Episodic Memory
    os.path.join(DATA_DIR, "user_episodes.json"),
    
    # Legacy
    os.path.join(DATA_DIR, "memory_scores.json"),
]

# Directories to delete entirely
DIRS_TO_DELETE = [
    # Vector stores
    os.path.join(DATA_DIR, "vectorstore"),
    os.path.join(DATA_DIR, "chroma_store"),
    os.path.join(DATA_DIR, "faiss_store"),
    
    # User content
    os.path.join(DATA_DIR, "user_files"),
    os.path.join(DATA_DIR, "uploads"),
    os.path.join(DATA_DIR, "processed"),
    os.path.join(DATA_DIR, "tmp"),
    
    # Metadata
    os.path.join(DATA_DIR, "metadata"),
    
    # Sakura internal data
    os.path.join(SAKURA_DATA, "logs"),
]

# Directories to recreate after deletion
DIRS_TO_RECREATE = [
    os.path.join(DATA_DIR, "vectorstore"),
    os.path.join(DATA_DIR, "chroma_store"),
    os.path.join(DATA_DIR, "user_files"),
    os.path.join(DATA_DIR, "uploads"),
    os.path.join(DATA_DIR, "processed"),
    os.path.join(DATA_DIR, "metadata"),
    os.path.join(SAKURA_DATA, "logs"),
]

def perform_reset():
    print("=" * 50)
    print(" SAKURA V9.1 - COMPLETE SYSTEM RESET")
    print("=" * 50)
    
    deleted_count = 0
    
    # 1. Delete specific files
    print("\n Deleting files...")
    for path in FILES_TO_DELETE:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"   {os.path.basename(path)}")
                deleted_count += 1
            except Exception as e:
                print(f"   {os.path.basename(path)}: {e}")
    
    # 2. Delete directories
    print("\n Deleting directories...")
    for path in DIRS_TO_DELETE:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                print(f"   {os.path.relpath(path, PROJECT_ROOT)}")
                deleted_count += 1
            except Exception as e:
                print(f"   {os.path.relpath(path, PROJECT_ROOT)}: {e}")
    
    # 3. Cleanup patterns (backups, caches)
    print("\n Cleaning backups and caches...")
    patterns = [
        os.path.join(DATA_DIR, "*.bak"),
        os.path.join(DATA_DIR, "*_backup*"),
        os.path.join(DATA_DIR, "*.cache"),
        os.path.join(DATA_DIR, "*.tmp"),
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                print(f"   {os.path.basename(f)}")
                deleted_count += 1
            except Exception as e:
                print(f"   {os.path.basename(f)}: {e}")
    
    # 4. Recreate empty directories
    print("\n Recreating directories...")
    for directory in DIRS_TO_RECREATE:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"   {os.path.relpath(directory, PROJECT_ROOT)}")
        except Exception as e:
            print(f"   {os.path.relpath(directory, PROJECT_ROOT)}: {e}")
    
    print("\n" + "=" * 50)
    print(f" RESET COMPLETE - Deleted {deleted_count} items")
    print(" Yuki is reborn. Run 'python server.py' to start fresh!")
    print("=" * 50)

if __name__ == "__main__":
    # Confirmation prompt
    print("\n⚠️  WARNING: This will delete ALL conversation history, memories,")
    print("    WorldGraph, and uploaded documents. This cannot be undone.")
    print()
    confirm = input("Type 'RESET' to confirm: ")
    
    if confirm.strip().upper() == "RESET":
        perform_reset()
    else:
        print(" Reset cancelled.")

