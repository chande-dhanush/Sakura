import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime

# Setup paths relative to script location
scripts_dir = Path(__file__).parent
backend_dir = scripts_dir.parent
data_dir = backend_dir / "data"
db_path = data_dir / "sakura.db"

# Import database module functions
import sys
sys.path.append(str(backend_dir))
from sakura_assistant.core.database import get_db_connection, get_db_path, Database

def migrate():
    print("=== Sakura SQLite Migration ===")
    conn = get_db_connection()
    
    # 1. Migrate user_settings.json
    settings_file = data_dir / "user_settings.json"
    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            Database.set_setting("user_settings", data)
            print(f"[+] Migrated user_settings.json")
        except Exception as e:
            print(f"[-] Error migrating user_settings: {e}")
            
    # 2. Migrate desire_state.json
    desire_file = data_dir / "desire_state.json"
    if desire_file.exists():
        try:
            with open(desire_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            Database.set_setting("desire_state", data)
            print(f"[+] Migrated desire_state.json")
        except Exception as e:
            print(f"[-] Error migrating desire_state: {e}")
            
    # 3. Migrate summary_memory.json
    summary_file = data_dir / "summary_memory.json"
    if summary_file.exists():
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            Database.set_setting("summary_memory", data)
            print(f"[+] Migrated summary_memory.json")
        except Exception as e:
            print(f"[-] Error migrating summary_memory: {e}")

    # 4. Migrate planned_initiations.json
    planned_file = data_dir / "planned_initiations.json"
    if planned_file.exists():
        try:
            with open(planned_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            messages = data.get("messages", [])
            conn.execute("DELETE FROM planned_initiations")
            for msg in messages:
                conn.execute(
                    "INSERT INTO planned_initiations (message, created_at, status) VALUES (?, ?, ?)",
                    (msg, datetime.now().isoformat(), "pending")
                )
            conn.commit()
            print(f"[+] Migrated planned_initiations.json ({len(messages)} messages)")
        except Exception as e:
            print(f"[-] Error migrating planned_initiations: {e}")

    # 5. Migrate conversation_history.json
    history_file = data_dir / "conversation_history.json"
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            conn.execute("DELETE FROM conversations")
            for msg in history:
                conn.execute(
                    "INSERT INTO conversations (role, content, timestamp, hash) VALUES (?, ?, ?, ?)",
                    (msg.get("role"), msg.get("content"), msg.get("timestamp"), msg.get("hash"))
                )
            conn.commit()
            print(f"[+] Migrated conversation_history.json ({len(history)} messages)")
        except Exception as e:
            print(f"[-] Error migrating conversation_history: {e}")

    # 6. Migrate world_graph.json
    wg_file = data_dir / "world_graph.json"
    if wg_file.exists():
        try:
            with open(wg_file, "r", encoding="utf-8") as f:
                wg = json.load(f)
                
            Database.set_setting("world_graph_current_turn", wg.get("current_turn", 0))
            Database.set_setting("world_graph_current_session", wg.get("current_session", ""))
            
            # Entities
            conn.execute("DELETE FROM entities")
            entities = wg.get("entities", {})
            for e_id, e in entities.items():
                conn.execute("""
                    INSERT INTO entities (
                        id, type, name, attributes, lifecycle, source, mutable_by,
                        created_at, last_referenced, reference_count, familiarity, sentiment, confidence, not_claims, summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    e.get("id"), e.get("type"), e.get("name"),
                    json.dumps(e.get("attributes", {})), e.get("lifecycle"), e.get("source"),
                    json.dumps(e.get("mutable_by", [])), e.get("created_at"), e.get("last_referenced"),
                    e.get("reference_count", 0), e.get("familiarity", 0.0), e.get("sentiment", 0.0),
                    e.get("confidence", 0.5), json.dumps(e.get("not_claims", [])), e.get("summary", "")
                ))
            
            # Actions
            conn.execute("DELETE FROM actions")
            actions = wg.get("actions", [])
            for a in actions:
                conn.execute("""
                    INSERT INTO actions (
                        id, turn, timestamp, action_type, tool, args, result, success,
                        focus_entity, entities_involved, depends_on, user_intent, user_satisfaction, significance, key_facts, summary, session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    a.get("id"), a.get("turn"), a.get("timestamp"), a.get("action_type"), a.get("tool"),
                    json.dumps(a.get("args", {})), a.get("result"), 1 if a.get("success", True) else 0,
                    a.get("focus_entity"), json.dumps(a.get("entities_involved", [])), a.get("depends_on"),
                    a.get("user_intent"), a.get("user_satisfaction"), a.get("significance", 0.5),
                    json.dumps(a.get("key_facts", [])), a.get("summary", ""), a.get("session_id", "")
                ))
                
            # Responses
            conn.execute("DELETE FROM responses")
            responses = wg.get("responses", [])
            for r in responses:
                conn.execute("""
                    INSERT OR REPLACE INTO responses (turn, content, timestamp, mode, tool_context)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    r.get("turn"), r.get("content"), r.get("timestamp"), r.get("mode"), r.get("tool_context")
                ))
                
            conn.commit()
            print(f"[+] Migrated world_graph.json ({len(entities)} entities, {len(actions)} actions, {len(responses)} responses)")
        except Exception as e:
            print(f"[-] Error migrating world_graph: {e}")

    # 7. Migrate Memory Metadata & Importance
    meta_file = data_dir / "memory_metadata.json"
    importance_file = data_dir / "memory_importance.json"
    
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            importance = {}
            if importance_file.exists():
                try:
                    with open(importance_file, "r", encoding="utf-8") as f:
                        importance = json.load(f)
                except:
                    pass
                    
            texts = meta.get("texts", [])
            metadata_list = meta.get("metadata", [])
            
            conn.execute("DELETE FROM memory_items")
            for i in range(len(texts)):
                t = texts[i]
                m = metadata_list[i] if i < len(metadata_list) else {}
                imp = float(importance.get(str(i), 0.0))
                conn.execute("""
                    INSERT INTO memory_items (faiss_index, text, timestamp, role, hash, importance)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (i, t, m.get("timestamp"), m.get("role"), m.get("hash"), imp))
            
            # Store the inverted index under setting
            Database.set_setting("memory_inverted_index", meta.get("inverted_index", {}))
            conn.commit()
            print(f"[+] Migrated memory metadata & importance ({len(texts)} memory items)")
        except Exception as e:
            print(f"[-] Error migrating memory metadata: {e}")
            
    print("=== Migration Finished ===")

if __name__ == "__main__":
    migrate()
