"""
V11.3 Global Context Valve - Ephemeral Manager
Manages temporary Chroma collections for large tool outputs.
"""
import uuid
import time
import os
import shutil
from typing import List, Dict, Optional
from datetime import datetime, timedelta

# Avoid circular imports by lazy loading Store
from ...memory.chroma_store.store import get_doc_store

class EphemeralManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EphemeralManager, cls).__new__(cls)
            cls._instance.active_stores = {} # {id: creation_timestamp}
        return cls._instance

    def ingest_text(self, text: str, source_tool: str = "unknown") -> str:
        """
        Chunk and index text into a temporary Chroma collection.
        Returns the ephemeral_id.
        """
        # 1. Generate ID
        eph_id = f"eph_{uuid.uuid4().hex[:8]}"
        
        # 2. Chunking (Simple overlap splitter to avoid heavy deps if possible, 
        # or use LangChain if available)
        chunks = self._chunk_text(text, chunk_size=500, overlap=50)
        
        # 3. Prepare Embeddings
        # We need an embedding function. Assuming we can get one or use a default.
        # Ideally, we reuse the system's embedding function.
        # For now, let PerDocChromaStore handle it if it has a default, 
        # OR we pass pre-computed embeddings. 
        # CAUTION: PerDocChromaStore in store.py expects embeddings list.
        # We need to compute them.
        
        try:
            from ..infrastructure.container import get_container
            # Attempt to get embedding service
             # This might be tricky if we don't have a clean way to get embeddings.
             # Let's check if we can rely on Chroma's default or if we need the App's one.
             # For robustness, let's try to get the app's embedding generator.
             # If unavailable, fail gracefully or use a placeholder.
            container = get_container()
             # We don't have a direct "get_embedding_fn" exposed easily in container based on previous files.
             # Let's check `backend/sakura_assistant/memory/embedding.py` if it exists, or similar.
             # Actually, PerDocChromaStore.add_documents takes `embeddings` list.
             # Let's use `sentence-transformers` if we can import it, or rely on a helper.
            pass
        except ImportError:
            pass
        except Exception:
            pass

        # To keep it simple and robust for this "Context Valve", 
        # we will use the `ingest_document` pipeline logic which handles this, 
        # OR just call the embedding model directly.
        
        # STRATEGY: Use the existing `get_embedding_model` from `core.model_wrapper` or similar? 
        # Let's assume we can get embeddings.
        
        embeddings = self._compute_embeddings(chunks)
        if not embeddings:
            return "error_embedding_failed"

        # 4. Store
        store = get_doc_store(eph_id)
        ids = [f"{eph_id}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": source_tool, "chunk_index": i} for i in range(len(chunks))]
        
        success = store.add_documents(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=chunks
        )
        store.unload() # Release lock
        
        if success:
            self.active_stores[eph_id] = time.time()
            print(f" [Ephemeral] Indexed {len(chunks)} chunks to {eph_id}")
            return eph_id
        return "error_storage_failed"

    def query(self, eph_id: str, query_text: str) -> str:
        """Query an ephemeral store."""
        if eph_id not in self.active_stores and not self._store_exists(eph_id):
            return " Ephemeral store not found or expired."
            
        # Compute query embedding
        query_emb = self._compute_embeddings([query_text])
        if not query_emb:
            return " Embedding failed."
            
        store = get_doc_store(eph_id)
        results = store.query(query_embeddings=query_emb, n_results=3)
        
        if not results or not results['documents'][0]:
            store.unload()
            return "No relevant context found."
            
        # Format results
        docs = results['documents'][0]
        store.unload() # Release lock
        
        return "\n---\n".join(docs)

    def cleanup_old(self, max_age_minutes: int = 10):
        """Delete stores older than X minutes."""
        now = time.time()
        to_delete = []
        
        for eid, timestamp in self.active_stores.items():
            age_min = (now - timestamp) / 60
            if age_min > max_age_minutes:
                to_delete.append(eid)
        
        for eid in to_delete:
            self._delete_store(eid)

    def _delete_store(self, eph_id: str):
        print(f" [Ephemeral] Cleaning up {eph_id}...")
        
        # 1. Attempt standard store deletion via Class
        try:
            store = get_doc_store(eph_id)
            if store.client:
                try:
                    if hasattr(store.client, "_system"):
                        store.client._system.stop()
                    store.client.clear_system_cache()
                except Exception:
                    pass
                store.client = None
                store.collection = None
            
            import gc
            gc.collect()
            gc.collect()
        except Exception as e:
            print(f"⚠️ Standard delete failed for {eph_id}: {e}")

        # 2. Manual cleanup of folder (Robust Windows Logic)
        from ...config import get_project_root
        path = os.path.join(get_project_root(), "data", "chroma_store", eph_id)
        
        if os.path.exists(path):
            import gc
            import chromadb
            
            # --- STRATEGY: Polling Delete with Permission Reset ---
            deleted = False
            error_msg = ""
            
            # Helper to reset permissions
            def reset_perms(path):
                import stat
                try:
                    os.chmod(path, stat.S_IWRITE)
                except: pass

            for i in range(5): # Polling 5 times
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, onerror=lambda func, p, _: (reset_perms(p), func(p)))
                    elif os.path.exists(path):
                        os.remove(path)
                    
                    if not os.path.exists(path):
                        deleted = True
                        break
                except Exception as e:
                    error_msg = str(e)
                    time.sleep(0.5) # Wait before retry
            
            if deleted:
                print(f" Deleted folder: {path}")
            else:
                # --- STRATEGY: Rename Fallback (Last Resort) ---
                print(f"⚠️ Delete failed ({error_msg}). Executing RENAME FALLBACK.")
                try:
                    new_path = f"{path}_TRASH_{uuid.uuid4().hex}"
                    os.rename(path, new_path)
                    print(f" Renamed locked folder to: {new_path}")
                except Exception as ex:
                    print(f" CRITICAL: Failed to delete AND rename {eph_id}: {ex}")

        if eph_id in self.active_stores:
            del self.active_stores[eph_id]

    def _store_exists(self, eph_id: str) -> bool:
        # Check if folder exists in data/chroma_store
        from ...config import get_project_root
        path = os.path.join(get_project_root(), "data", "chroma_store", eph_id)
        return os.path.exists(path)

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        chunks = []
        for i in range(0, len(text), chunk_size - overlap):
            chunks.append(text[i:i + chunk_size])
        return chunks

    def _compute_embeddings(self, texts: List[str]) -> List[List[float]]:
        # Helper to get embeddings. 
        # We'll try to use the same logic as the main system.
        # If unavailable, we might need a fallback.
        try:
            # Try V10 standard embedding
            from ...memory.ingestion.embedder import get_embedder
            embedder = get_embedder()
            return embedder.embed_documents(texts)
        except ImportError:
            # Fallback: Check if we are in test environment and insert path
            try:
                import sys
                from sakura_assistant.memory.ingestion.embedder import get_embedder
                embedder = get_embedder()
                return embedder.embed_documents(texts)
            except Exception as e:
                print(f"⚠️ EphemeralManager: Could not import get_embedder: {e}")
                return []


# Singleton Factory
def get_ephemeral_manager():
    return EphemeralManager()
