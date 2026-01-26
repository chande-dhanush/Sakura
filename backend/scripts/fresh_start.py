#!/usr/bin/env python3
"""
Sakura V15: Fresh Start Script
==============================
Resets all data files to a clean state while preserving config.

Run this script to start with a blank slate:
    python scripts/fresh_start.py
"""

import os
import shutil
import json
from datetime import datetime
from pathlib import Path

# Get project root
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

# Files to clear (will be recreated empty or with defaults)
FILES_TO_CLEAR = [
    "conversation_history.json",
    "conversation_history.json.sha256",
    "world_graph.json",
    "dream_journal.jsonl",
    "desire_state.json",
    "planned_initiations.json",
    ".last_crystallization",
    "flight_recorder.jsonl",
    "memory_importance.json",
    "memory_metadata.json",
    "memory_metadata.json.sha256",
    "faiss_index.bin",
]

# Directories to clear
DIRS_TO_CLEAR = [
    "backup",
    "chroma_store",
    "smart_cache",
    "processed",
    "logs",
]


def backup_before_clear():
    """Create a backup of important files before clearing."""
    backup_dir = DATA_DIR / "pre_reset_backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Backup world graph
    wg_path = DATA_DIR / "world_graph.json"
    if wg_path.exists():
        shutil.copy(wg_path, backup_dir / "world_graph.json")
        print(f"  Backed up world_graph.json")
    
    # Backup conversation history
    ch_path = DATA_DIR / "conversation_history.json"
    if ch_path.exists():
        shutil.copy(ch_path, backup_dir / "conversation_history.json")
        print(f"  Backed up conversation_history.json")
    
    return backup_dir


def clear_files():
    """Clear individual files."""
    for filename in FILES_TO_CLEAR:
        filepath = DATA_DIR / filename
        if filepath.exists():
            filepath.unlink()
            print(f"  Deleted: {filename}")


def clear_directories():
    """Clear contents of directories (but keep the directories)."""
    for dirname in DIRS_TO_CLEAR:
        dirpath = DATA_DIR / dirname
        if dirpath.exists() and dirpath.is_dir():
            # Count items before clearing
            item_count = len(list(dirpath.rglob("*")))
            shutil.rmtree(dirpath)
            dirpath.mkdir(exist_ok=True)
            print(f"  Cleared: {dirname}/ ({item_count} items)")


def create_default_files():
    """Create default empty/minimal files."""
    
    # Empty conversation history
    (DATA_DIR / "conversation_history.json").write_text("[]")
    print("  Created: conversation_history.json (empty)")
    
    # Default world graph with user identity
    default_world_graph = {
        "entities": {
            "user:self": {
                "id": "user:self",
                "type": "user",
                "name": "User",
                "attributes": {},
                "lifecycle": "promoted",
                "source": "system",
                "confidence": 1.0,
                "summary": "The user of this assistant.",
                "reference_count": 0,
                "created_at": datetime.now().isoformat(),
                "last_referenced": datetime.now().isoformat()
            }
        },
        "actions": [],
        "current_turn": 0,
        "current_session": "fresh_start"
    }
    (DATA_DIR / "world_graph.json").write_text(json.dumps(default_world_graph, indent=2))
    print("  Created: world_graph.json (default identity)")
    
    # Empty desire state
    default_desire = {
        "social_battery": 1.0,
        "loneliness": 0.0,
        "curiosity": 0.3,
        "duty": 0.0,
        "last_interaction": datetime.now().timestamp(),
        "last_user_message": datetime.now().timestamp(),
        "last_sakura_initiation": 0.0,
        "messages_today": 0,
        "initiations_today": 0
    }
    (DATA_DIR / "desire_state.json").write_text(json.dumps(default_desire, indent=2))
    print("  Created: desire_state.json (fresh)")
    
    # Empty planned initiations
    (DATA_DIR / "planned_initiations.json").write_text('{"messages": [], "generated": null}')
    print("  Created: planned_initiations.json (empty)")
    
    # Memory importance
    (DATA_DIR / "memory_importance.json").write_text("{}")
    print("  Created: memory_importance.json (empty)")


def main():
    print("=" * 60)
    print(" SAKURA V15: FRESH START")
    print("=" * 60)
    print()
    
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)
        print(f"Created data directory: {DATA_DIR}")
    
    print(" Creating backup...")
    backup_dir = backup_before_clear()
    print(f"  Backup saved to: {backup_dir}")
    print()
    
    print("️  Clearing files...")
    clear_files()
    print()
    
    print(" Clearing directories...")
    clear_directories()
    print()
    
    print(" Creating default files...")
    create_default_files()
    print()
    
    print("=" * 60)
    print(" Fresh start complete!")
    print()
    print("Next steps:")
    print("  1. Start the server: python server.py")
    print("  2. Chat with Sakura to populate memory")
    print("  3. Check desire state: GET /api/desire")
    print("=" * 60)


if __name__ == "__main__":
    main()
