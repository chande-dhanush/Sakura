import os
import json
import shutil
import hashlib
import time
import re
import gc
import threading
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
import numpy as np
from functools import lru_cache
from ...utils.pathing import get_project_root
from ...config import FAISS_MMAP, LAZY_EMBEDDINGS, MAX_INMEM_HISTORY, EMBEDDING_IDLE_TIMEOUT
from ...utils.stability_logger import log_mem, log_reinforce

logger = logging.getLogger(__name__)

# Use sentence-transformers directly (lighter than langchain_huggingface)
try:
    from sentence_transformers import SentenceTransformer
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("⚠️ FAISS/SentenceTransformers not available. Using basic memory.")

# === CONFIGURATION ===
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
DATA_DIR = Path(get_project_root()) / "data"
BACKUP_DIR = DATA_DIR / "backup"
FAISS_INDEX_PATH = DATA_DIR / "faiss_index.bin"
MEMORY_METADATA_FILE = DATA_DIR / "memory_metadata.json"
MEMORY_IMPORTANCE_PATH = DATA_DIR / "memory_importance.json"  # Patch 1: Separate importance file
CONVERSATION_FILE = DATA_DIR / "conversation_history.json"
MEMORY_STATS_FILE = DATA_DIR / "memory_stats.json"

# Ensure data directories exist
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

def write_memory_atomic(path: Path, obj: Any):
    """
    Writes JSON data atomically with backup and checksum.
    """
    try:
        data_bytes = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        tmp_path = path.with_suffix(".tmp")
        
        # 1. Atomic Write
        with open(tmp_path, "wb") as f:
            f.write(data_bytes)
            f.flush()
            os.fsync(f.fileno())
        
        # 2. Rename (Atomic on POSIX, mostly safe on Windows)
        if path.exists():
            os.replace(tmp_path, path)
        else:
            os.rename(tmp_path, path)
            
        # 3. Backup
        timestamp = int(time.time())
        backup_path = BACKUP_DIR / f"{path.name}.{timestamp}.bak"
        shutil.copy2(path, backup_path)
        
        # Prune old backups (Keep last 5)
        backups = sorted(BACKUP_DIR.glob(f"{path.name}.*.bak"), key=os.path.getmtime)
        for old_backup in backups[:-5]:
            try:
                old_backup.unlink()
            except:
                pass

        # 4. Checksum
        checksum = hashlib.sha256(data_bytes).hexdigest()
        with open(str(path) + ".sha256", "w") as f:
            f.write(checksum)
    except Exception as e:
        print(f"❌ Atomic write failed for {path}: {e}")

class VectorMemoryStore:
    """
    RAG memory using FAISS and SentenceTransformers directly.
    Falls back to simple list if dependencies unavailable.
    Singleton pattern enforced via global instance.
    """
    def __init__(self):
        self.conversation_history = []
        self._history_lock = threading.Lock()  # Thread-safety for history mutations
        self.memory_stats = {
            "total_memories": 0,
            "last_updated": None,
            "system_health": "initializing"
        }
        
        # P0: Lazy-loaded embeddings model
        self._embeddings_model = None
        # CRITICAL: Use RLock (reentrant) to prevent deadlock when
        # _check_and_unload_embeddings calls unload_embeddings
        self._embed_lock = threading.RLock()
        self._embed_last_used = 0
        self._embed_unload_timer = None
        
        # P2: Embedding cache (LRU for repeated phrases)
        self._embed_cache = {}
        self._embed_cache_order = []
        self._embed_cache_max = 1024
        
        self.faiss_index = None
        self.memory_texts = []
        self.memory_metadata = []
        self.memory_importance = {}  # Patch 1: Importance scores {id: score}
        self.inverted_index = {} # keyword -> list of chunk indices
        self.last_write_time = 0 # For rate limiting
        self._mmap_active = False
        
        # Debounced save timer
        self._save_timer = None
        self._save_lock = threading.Lock()
        
        self._initialize_system()

    def _ensure_embeddings_loaded(self):
        """Lazy-load embeddings model on first use. Thread-safe."""
        with self._embed_lock:
            if self._embeddings_model is None:
                if not FAISS_AVAILABLE:
                    return None
                logger.info("🧠 Loading embedding model (lazy)...")
                print("🧠 Loading embedding model (lazy)...")
                try:
                    self._embeddings_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
                    logger.info("✅ Embeddings loaded.")
                    print("✅ Embeddings loaded.")
                except Exception as e:
                    logger.error(f"Failed to load embeddings: {e}")
                    return None
            
            self._embed_last_used = time.time()
            self._schedule_embed_unload()
            return self._embeddings_model
    
    def _schedule_embed_unload(self):
        """Schedule embedding unload after idle timeout."""
        if self._embed_unload_timer:
            self._embed_unload_timer.cancel()
        
        self._embed_unload_timer = threading.Timer(
            EMBEDDING_IDLE_TIMEOUT, 
            self._check_and_unload_embeddings
        )
        self._embed_unload_timer.daemon = True
        self._embed_unload_timer.start()
    
    def _check_and_unload_embeddings(self):
        """Check if embeddings have been idle and unload if so."""
        with self._embed_lock:
            if self._embeddings_model is None:
                return
            
            idle_time = time.time() - self._embed_last_used
            if idle_time >= EMBEDDING_IDLE_TIMEOUT:
                self.unload_embeddings()
    
    def unload_embeddings(self):
        """Unload embedding model to free memory."""
        with self._embed_lock:
            if self._embeddings_model is not None:
                logger.info("💤 Unloading embeddings (idle timeout)...")
                print("💤 Unloading embeddings (idle timeout)...")
                del self._embeddings_model
                self._embeddings_model = None
                gc.collect()
                logger.info("✅ Embeddings unloaded.")
                print("✅ Embeddings unloaded.")
    
    @property
    def embeddings_model(self):
        """Property for backward compatibility - lazy loads on access."""
        return self._ensure_embeddings_loaded()
    
    @embeddings_model.setter
    def embeddings_model(self, value):
        """Setter for backward compatibility."""
        self._embeddings_model = value

    def _initialize_system(self):
        try:
            if not FAISS_AVAILABLE:
                print("🧠 Using basic memory (FAISS not available)")
                self.memory_stats["system_health"] = "basic"
                return
                
            print("🧠 Initializing Vector Memory (lazy embeddings)...")
            
            # P0: DO NOT load embeddings here - lazy load on first use
            # self._embeddings_model = SentenceTransformer(EMBEDDING_MODEL_NAME)  # REMOVED
            
            # 2. Load or Create FAISS Index (with mmap if enabled)
            if FAISS_INDEX_PATH.exists() and MEMORY_METADATA_FILE.exists():
                try:
                    # P0: Use mmap to avoid loading entire index into RAM
                    if FAISS_MMAP:
                        try:
                            self.faiss_index = faiss.read_index(str(FAISS_INDEX_PATH), faiss.IO_FLAG_MMAP)
                            self._mmap_active = True
                            logger.info("FAISS index loaded with MMAP")
                            print(f"📂 Loaded FAISS index with MMAP ({self.faiss_index.ntotal} vectors)")
                        except Exception as e:
                            logger.warning(f"FAISS mmap failed, falling back to normal read: {e}")
                            print(f"⚠️ FAISS mmap failed, using normal read: {e}")
                            self.faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
                            self._mmap_active = False
                    else:
                        self.faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
                        self._mmap_active = False
                    
                    with open(MEMORY_METADATA_FILE, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        self.memory_texts = metadata.get('texts', [])
                        self.memory_metadata = metadata.get('metadata', [])
                        self.inverted_index = metadata.get('inverted_index', {})
                    
                    # Patch 1: Load importance from separate file
                    if MEMORY_IMPORTANCE_PATH.exists():
                        try:
                            with open(MEMORY_IMPORTANCE_PATH, 'r', encoding='utf-8') as f:
                                self.memory_importance = json.load(f)
                        except Exception:
                            self.memory_importance = {}
                    
                    if not self._mmap_active:
                        print(f"📂 Loaded FAISS index with {self.faiss_index.ntotal} vectors")
                except Exception as e:
                    print(f"⚠️ Error loading FAISS index: {e}. Creating new one.")
                    self._create_new_index()
            else:
                self._create_new_index()
            
            # 3. Load conversation history (capped to MAX_INMEM_HISTORY)
            self._load_conversation()
            
            self.memory_stats["system_health"] = "healthy"
            self.memory_stats["total_memories"] = len(self.memory_texts)
            self.memory_stats["mmap_active"] = self._mmap_active
            
            print(f"🧠 Memory initialized: {len(self.conversation_history)} msgs in memory, mmap={self._mmap_active}")
            
        except Exception as e:
            print(f"❌ Error initializing memory: {e}")
            self.memory_stats["system_health"] = "error"

    def _create_new_index(self):
        # Create empty index
        embedding_dim = 384  # all-MiniLM-L6-v2 dimension
        self.faiss_index = faiss.IndexFlatL2(embedding_dim)
        self.memory_texts = []
        self.memory_metadata = []
        self.inverted_index = {}
        self._save_index()

    def _update_inverted_index(self, text: str, index: int):
        """Update simple inverted index for keyword search"""
        # Simple tokenization
        tokens = set(re.findall(r'\w+', text.lower()))
        # Remove common stop words (very basic list)
        stop_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 'in', 'to', 'of', 'for', 'with'}
        tokens = tokens - stop_words
        
        for token in tokens:
            if token not in self.inverted_index:
                self.inverted_index[token] = []
            self.inverted_index[token].append(index)

    def _save_index(self):
        if self.faiss_index:
            try:
                faiss.write_index(self.faiss_index, str(FAISS_INDEX_PATH))
                
                # Use atomic write for metadata AND inverted index
                metadata_obj = {
                    'texts': self.memory_texts,
                    'metadata': self.memory_metadata,
                    'inverted_index': self.inverted_index
                }
                write_memory_atomic(MEMORY_METADATA_FILE, metadata_obj)
                
                # Patch 1: Save importance to separate file
                with open(MEMORY_IMPORTANCE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(self.memory_importance, f, indent=2)
                    
            except Exception as e:
                print(f"❌ Error saving index: {e}")

    def _load_conversation(self):
        """Load conversation history, capped to MAX_INMEM_HISTORY."""
        print(f"📜 [DEBUG] Checking history file: {CONVERSATION_FILE}")
        if CONVERSATION_FILE.exists():
            try:
                with open(CONVERSATION_FILE, 'r', encoding='utf-8') as f:
                    full_history = json.load(f)
                
                # P0: Cap in-memory history to MAX_INMEM_HISTORY
                if len(full_history) > MAX_INMEM_HISTORY:
                    self.conversation_history = full_history[-MAX_INMEM_HISTORY:]
                    print(f"📜 Loaded last {MAX_INMEM_HISTORY} of {len(full_history)} messages")
                else:
                    self.conversation_history = full_history
                
                print(f"💬 In-memory history: {len(self.conversation_history)} messages")
            except Exception as e:
                print(f"⚠️ Error loading conversation: {e}")
                self.conversation_history = []
        else:
            print(f"⚠️ History file NOT FOUND at {CONVERSATION_FILE}")
    
    def get_full_history(self) -> List[Dict]:
        """Load full conversation history from disk (for export/review)."""
        if CONVERSATION_FILE.exists():
            try:
                with open(CONVERSATION_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return self.conversation_history

    def _save_metadata(self):
        """P1: Debounced write - schedule save after 2s of no activity."""
        self._trigger_debounced_save()
    
    def _trigger_debounced_save(self):
        """Schedule a debounced save (2 second delay)."""
        if not hasattr(self, '_save_timer'):
            self._save_timer = None
        if not hasattr(self, '_save_lock'):
            self._save_lock = threading.Lock()
        
        with self._save_lock:
            # Cancel existing timer
            if self._save_timer:
                self._save_timer.cancel()
            
            # Schedule new save in 2 seconds
            self._save_timer = threading.Timer(2.0, self._do_save_metadata)
            self._save_timer.daemon = True
            self._save_timer.start()
    
    def _do_save_metadata(self):
        """Actually perform the save (called by timer)."""
        try:
            write_memory_atomic(CONVERSATION_FILE, self.conversation_history)
            logger.debug("Debounced save completed")
        except Exception as e:
            logger.error(f"Debounced save failed: {e}")
    
    def flush_saves(self):
        """Force immediate save (call before shutdown)."""
        if hasattr(self, '_save_timer') and self._save_timer:
            self._save_timer.cancel()
        self._do_save_metadata()
    
    def reinforce_memory(self, idx: int, boost: float = 1.0):
        """
        Patch 2: Reinforce a memory's importance when it's retrieved.
        
        Args:
            idx: Memory index
            boost: Amount to increase importance
        """
        key = str(idx)
        current = float(self.memory_importance.get(key, 0.0))
        new_score = round(current + float(boost), 4)
        self.memory_importance[key] = new_score
        log_reinforce(idx, new_score)
        # Save immediately to persist reinforcement
        try:
            with open(MEMORY_IMPORTANCE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.memory_importance, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist reinforcement: {e}")

    def append_to_history(self, msg: dict):
        """
        Append a message dict directly to history and schedule save.
        Used by ViewModel to ensure shared state updates.
        Thread-safe with debounced persistence.
        Includes deduplication guard.
        """
        # DEDUPLICATION GUARD: Prevent identical consecutive messages
        with self._history_lock:
            if self.conversation_history:
                last_msg = self.conversation_history[-1]
                if (last_msg.get('role') == msg.get('role') and 
                    last_msg.get('content') == msg.get('content')):
                    print(f"⚠️ [DEDUP] Skipping duplicate {msg.get('role')} message")
                    return  # Skip duplicate
            
            log_mem("STORE.append()", msg)
            print(f"📝 [APPEND] {msg.get('role')} message to history (len={len(self.conversation_history)+1})")
            self.conversation_history.append(msg)
        self._trigger_debounced_save()

    def add_message(self, content: str, role: str = "user", timestamp: Optional[str] = None):
        """Add a message to FAISS vector memory (NOT conversation history).
        
        NOTE: This method is for FAISS indexing only.
        Conversation history is managed separately via append_to_history().
        """
        # Ensure content is string
        if not isinstance(content, str):
            content = str(content)
            
        # 1. Rate Limiting (0.5s)
        now = time.time()
        if now - self.last_write_time < 0.5:
            # Skip rapid writes (spam protection)
            return
        self.last_write_time = now

        if not timestamp:
            timestamp = datetime.now().isoformat()
            
        # NOTE: DO NOT append to conversation_history here!
        # History is managed by append_to_history() to prevent duplicates.
        # This function is ONLY for FAISS vector indexing.
        
        # Only index user messages or important assistant info
        if not FAISS_AVAILABLE or not self.embeddings_model or not self.faiss_index:
            return

        # Deduplication Check (Content Hash)
        # Normalize: lowercase, remove whitespace
        norm_content = re.sub(r'\s+', '', content.lower())
        content_hash = hashlib.sha256(norm_content.encode()).hexdigest()
        
        # Check if hash exists in recent metadata (last 100)
        for meta in self.memory_metadata[-100:]:
            if meta.get('hash') == content_hash:
                return

        # Add to Vector Store
        try:
            embedding = self.embeddings_model.encode([content])
            self.faiss_index.add(np.array(embedding, dtype=np.float32))
            
            self.memory_texts.append(content)
            self.memory_metadata.append({
                "timestamp": timestamp,
                "role": role,
                "hash": content_hash
            })
            
            # Update Inverted Index
            new_idx = len(self.memory_texts) - 1
            self._update_inverted_index(content, new_idx)
            
            self._save_index()
            self.memory_stats["total_memories"] = len(self.memory_texts)
            self.memory_stats["last_updated"] = timestamp
            
            # Invalidate cache
            self.get_context_for_query.cache_clear()
            
        except Exception as e:
            print(f"❌ Error adding to vector store: {e}")

    @lru_cache(maxsize=256) # Increased cache size
    def get_context_for_query(self, query: str, k: int = 5, max_chars: int = 2500) -> str:
        """
        Hybrid Retrieval with Strict Token/Char Budget.
        """
        if not FAISS_AVAILABLE or not self.embeddings_model or not self.faiss_index:
            recent = self.conversation_history[-5:]
            return "\n".join([f"{m.get('role', 'user').title()}: {m.get('content','')}" for m in recent])
        
        try:
            # 1. Vector Search (Semantic Candidates) - Get top 30
            query_embedding = self.embeddings_model.encode([query])[0]
            distances, vector_indices = self.faiss_index.search(np.array([query_embedding], dtype=np.float32), k=30)
            
            # 2. Keyword Search (Lexical Candidates)
            query_tokens = set(re.findall(r'\w+', query.lower()))
            keyword_indices = set()
            for token in query_tokens:
                if token in self.inverted_index:
                    keyword_indices.update(self.inverted_index[token])
            
            # 3. Hybrid Scoring
            all_candidates = set(vector_indices[0]) | keyword_indices
            all_candidates = {idx for idx in all_candidates if idx != -1 and idx < len(self.memory_texts)}
            
            scored_candidates = []
            
            for idx in all_candidates:
                # A. Vector Score
                vec_score = 0.0
                if idx in vector_indices[0]:
                    rank = np.where(vector_indices[0] == idx)[0][0]
                    dist = distances[0][rank]
                    vec_score = 1.0 / (1.0 + dist)
                
                # B. Keyword Score
                text = self.memory_texts[idx].lower()
                found_tokens = sum(1 for t in query_tokens if t in text)
                kw_score = found_tokens / len(query_tokens) if query_tokens else 0
                
                # C. Recency Score
                recency_score = idx / len(self.memory_texts)
                
                # Weighted Sum
                final_score = (0.4 * vec_score) + (0.3 * kw_score) + (0.3 * recency_score)
                scored_candidates.append((final_score, idx))
            
            # 4. Re-rank and Budget Enforcement
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            
            final_memories = []
            current_chars = 0
            
            # Iterate through ranked candidates
            for score, idx in scored_candidates:
                text = self.memory_texts[idx]
                meta = self.memory_metadata[idx]
                
                # Format memory entry
                entry = f"- {text} (from {meta.get('timestamp', '')})"
                entry_len = len(entry) + 1 # +1 for newline
                
                # Check budget
                if current_chars + entry_len > max_chars:
                    continue 
                
                final_memories.append(entry)
                current_chars += entry_len
                
                if len(final_memories) >= k:
                    break
            
            # Get recent history (Separate budget)
            recent = self.conversation_history[-5:]
            recent_text = "\n".join([f"{m.get('role', 'user').title()}: {m.get('content','')}" for m in recent])
            
            return f"Relevant Memories (Budget: {current_chars}/{max_chars} chars):\n" + "\n".join(final_memories) + f"\n\nRecent Conversation:\n{recent_text}"
            
        except Exception as e:
            print(f"❌ Error retrieving context: {e}")
            return ""

    def delete_memory_by_keyword(self, keyword: str) -> int:
        """
        Delete all memories containing the keyword.
        """
        keyword = keyword.lower()
        to_keep_indices = []
        deleted_count = 0
        
        for i, text in enumerate(self.memory_texts):
            if keyword not in text.lower():
                to_keep_indices.append(i)
            else:
                deleted_count += 1
        
        if deleted_count == 0:
            return 0
            
        # Rebuild
        new_texts = [self.memory_texts[i] for i in to_keep_indices]
        new_metadata = [self.memory_metadata[i] for i in to_keep_indices]
        
        self.memory_texts = new_texts
        self.memory_metadata = new_metadata
        
        self._create_new_index()
        if self.embeddings_model and new_texts:
            embeddings = self.embeddings_model.encode(new_texts)
            self.faiss_index.add(np.array(embeddings, dtype=np.float32))
            
        self._save_index()
        
        # Rebuild inverted index
        self.inverted_index = {}
        for idx, text in enumerate(new_texts):
            self._update_inverted_index(text, idx)
            
        print(f"🗑️ Deleted {deleted_count} memories containing '{keyword}'")
        return deleted_count

    def clear_all_memory(self):
        """Clear all memory, preserving list reference for shared access."""
        # CRITICAL: Use clear() instead of = [] to preserve shared reference
        self.conversation_history.clear()
        self.memory_texts.clear()
        self.memory_metadata.clear()
        self.inverted_index.clear()
        self.memory_importance.clear()
        
        # Delete FAISS index file
        if FAISS_INDEX_PATH.exists():
            try: FAISS_INDEX_PATH.unlink()
            except: pass
        if MEMORY_METADATA_FILE.exists():
            try: MEMORY_METADATA_FILE.unlink()
            except: pass
        if MEMORY_IMPORTANCE_PATH.exists():
            try: MEMORY_IMPORTANCE_PATH.unlink()
            except: pass
        
        # Recreate empty index
        self._create_new_index()
        
        # Save empty state
        self._save_metadata()
        self._save_index()

# Global Instance
_memory_store_instance = None

def get_memory_store():
    global _memory_store_instance
    if _memory_store_instance is None:
        _memory_store_instance = VectorMemoryStore()
    return _memory_store_instance

def save_conversation(history: List[Dict]):
    """Sync history contents without replacing the list reference."""
    store = get_memory_store()
    # GUARD: Never replace the list reference - sync contents in-place
    with store._history_lock:
        if history is not store.conversation_history:
            store.conversation_history[:] = history
    store._trigger_debounced_save()

def save_conversation_async(history: List[Dict]):
    """Async save to prevent UI blocking."""
    import threading
    def _save():
        try:
            save_conversation(history)
        except Exception as e:
            print(f"⚠️ Async save failed: {e}")
    
    threading.Thread(target=_save, daemon=True).start()

def load_conversation() -> List[Dict]:
    return get_memory_store().conversation_history

def add_message_to_memory(content: str, role: str = "user", timestamp: Optional[str] = None):
    get_memory_store().add_message(content, role, timestamp)

def get_relevant_context(query: str, max_chars: int = 2500) -> str:
    return get_memory_store().get_context_for_query(query, max_chars=max_chars)

def delete_memory_keyword(keyword: str) -> int:
    return get_memory_store().delete_memory_by_keyword(keyword)

def get_memory_stats() -> Dict:
    # Safe check to avoid triggering init just for stats
    global _memory_store_instance
    if _memory_store_instance:
        return _memory_store_instance.memory_stats
    return {"total_memories": 0, "system_health": "initializing"}

def clear_conversation_history():
    get_memory_store().clear_all_memory()
