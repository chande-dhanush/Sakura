import os
import chromadb
import threading
import shutil
from typing import Optional, List, Any
from ..metadata import get_project_root

CHROMA_ROOT = os.path.join(get_project_root(), "data", "chroma_store")

class PerDocChromaStore:
    """
    Isolated Chroma Store for a SINGLE document.
    Path: data/chroma_store/<doc_id>/
    Collection: doc_<doc_id>
    """
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.persist_dir = os.path.join(CHROMA_ROOT, doc_id)
        self.collection_name = f"doc_{doc_id}"
        self.client = None
        self.collection = None
        self._lock = threading.Lock()

    def _init_client(self):
        """Lazy init client."""
        if self.client:
            return

        with self._lock:
            if self.client: return
            
            os.makedirs(self.persist_dir, exist_ok=True)
            try:
                self.client = chromadb.PersistentClient(path=self.persist_dir)
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception as e:
                print(f" Failed to init Chroma for {self.doc_id}: {e}")
                self.client = None

    def add_documents(self, ids: List[str], embeddings: List[Any], metadatas: List[dict], documents: List[str]) -> bool:
        self._init_client()
        if not self.collection: return False
        
        try:
            with self._lock:
                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    documents=documents
                )
            return True
        except Exception as e:
            print(f"⚠️ Chroma add failed for {self.doc_id}: {e}")
            return False

    def query(self, query_embeddings: List[Any], n_results: int = 3) -> Optional[dict]:
        self._init_client()
        if not self.collection: return None
        
        try:
            return self.collection.query(
                query_embeddings=query_embeddings,
                n_results=n_results
            )
        except Exception as e:
            print(f"⚠️ Chroma query failed for {self.doc_id}: {e}")
            return None

    def unload(self):
        """Unload client to release file locks."""
        if self.client:
            try:
                # Explicitly stop the system to release resources
                if hasattr(self.client, "_system"):
                    self.client._system.stop()
                
                # Clear internal caches
                self.client.clear_system_cache()
            except Exception as e:
                print(f"⚠️ Chroma unload warning: {e}")
                
        self.client = None
        self.collection = None
        import gc
        gc.collect()

    def delete_store(self) -> bool:
        """Delete this entire store from disk (Robust)."""
        import time
        import gc
        try:
            # 1. Unload Client
            print(f"️ Deleting store for {self.doc_id}...")
            self.client = None 
            self.collection = None
            
            # 2. Force GC to release file handles
            gc.collect()
            
            if not os.path.exists(self.persist_dir):
                return True

            # 3. Retry Loop for Windows locking
            for i in range(5):
                try:
                    shutil.rmtree(self.persist_dir)
                    return True
                except Exception as e:
                    print(f"⚠️ Retry {i+1} failed to delete {self.persist_dir}: {e}")
                    time.sleep(0.5)
            
            return False
        except Exception as e:
            print(f" Failed to delete store {self.doc_id}: {e}")
            return False

# Factory function
def get_doc_store(doc_id: str) -> PerDocChromaStore:
    return PerDocChromaStore(doc_id)

def get_chroma_client():
    """Get global Chroma client for caching."""
    import chromadb
    # Use a specific cache directory to avoid conflict with per-doc stores
    cache_dir = os.path.join(get_project_root(), "data", "smart_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return chromadb.PersistentClient(path=cache_dir)
