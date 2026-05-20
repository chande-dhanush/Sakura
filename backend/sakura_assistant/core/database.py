import sqlite3
import json
import threading
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# RLock to make SQLite operations thread-safe and async-safe across the app
_db_lock = threading.RLock()
_db_connection = None
_db_path_override = None

def set_db_path(path: str):
    global _db_path_override, _db_connection
    with _db_lock:
        _db_path_override = path
        if _db_connection:
            try:
                _db_connection.close()
            except:
                pass
            _db_connection = None

def get_db_path() -> Path:
    global _db_path_override
    if _db_path_override:
        return Path(_db_path_override)
    from ..utils.pathing import get_project_root
    return Path(get_project_root()) / "data" / "sakura.db"

def get_db_connection() -> sqlite3.Connection:
    """Get the global thread-safe sqlite3 connection in WAL mode."""
    global _db_connection
    if _db_connection is None:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Timeout 30 seconds for concurrent lock resolution
        _db_connection = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=30.0
        )
        # Enable WAL mode for high concurrency
        _db_connection.execute("PRAGMA journal_mode=WAL;")
        _db_connection.execute("PRAGMA synchronous=NORMAL;")
        _db_connection.row_factory = sqlite3.Row
        init_db(_db_connection)
    return _db_connection

def init_db(conn: sqlite3.Connection):
    """Initialize SQLite tables if they do not exist."""
    with _db_lock:
        # 1. Settings / Config Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        # 2. Conversations Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                hash TEXT
            );
        """)

        # 3. Planned Initiations Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS planned_initiations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT,
                created_at TEXT,
                scheduled_for TEXT,
                status TEXT DEFAULT 'pending'
            );
        """)

        # 4. World Graph Entities Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                type TEXT,
                name TEXT,
                attributes TEXT,
                lifecycle TEXT,
                source TEXT,
                mutable_by TEXT,
                created_at TEXT,
                last_referenced TEXT,
                reference_count INTEGER,
                familiarity REAL,
                sentiment REAL,
                confidence REAL,
                not_claims TEXT,
                summary TEXT
            );
        """)

        # 5. World Graph Actions Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                turn INTEGER,
                timestamp TEXT,
                action_type TEXT,
                tool TEXT,
                args TEXT,
                result TEXT,
                success INTEGER,
                focus_entity TEXT,
                entities_involved TEXT,
                depends_on TEXT,
                user_intent TEXT,
                user_satisfaction REAL,
                significance REAL,
                key_facts TEXT,
                summary TEXT,
                session_id TEXT
            );
        """)

        # 6. World Graph Responses Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                turn INTEGER PRIMARY KEY,
                content TEXT,
                timestamp REAL,
                mode TEXT,
                tool_context TEXT
            );
        """)

        # 7. Memory Items Table (FAISS Metadata)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_items (
                faiss_index INTEGER PRIMARY KEY,
                text TEXT,
                timestamp TEXT,
                role TEXT,
                hash TEXT,
                importance REAL DEFAULT 0.0
            );
        """)
        conn.commit()

class Database:
    """Helper interface for all DB transactions."""
    
    @staticmethod
    def get_setting(key: str, default: Any = None) -> Any:
        conn = get_db_connection()
        with _db_lock:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row['value'])
                except:
                    return row['value']
            return default

    @staticmethod
    def set_setting(key: str, value: Any):
        conn = get_db_connection()
        val_str = json.dumps(value, ensure_ascii=False)
        with _db_lock:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, val_str)
            )
            conn.commit()

    @staticmethod
    def get_all_settings() -> Dict[str, Any]:
        conn = get_db_connection()
        with _db_lock:
            cursor = conn.execute("SELECT key, value FROM settings")
            res = {}
            for r in cursor.fetchall():
                try:
                    res[r['key']] = json.loads(r['value'])
                except:
                    res[r['key']] = r['value']
            return res
