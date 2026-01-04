import time
import logging
import threading
import numpy as np
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

class EphemeralCache:
    """
    Ephemeral In-Memory Cache for RAG Retrieval (EAG).
    - Stores (query_embedding, results, timestamp).
    - Checks semantic similarity of new query vs cached query.
    - TTL: 3 minutes.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(EphemeralCache, cls).__new__(cls)
                    cls._instance._init_cache()
        return cls._instance

    def _init_cache(self):
        self.cache: List[Dict[str, Any]] = [] # List of {emb, results, timestamp, query_text}
        self.ttl = 180 # 3 minutes
        self.similarity_threshold = 0.82
        self.cache_lock = threading.Lock()

    def check(self, query_embedding: np.ndarray, query_text: str = "") -> Optional[List[Dict]]:
        """
        Check cache for semantically similar query.
        Returns cached results or None.
        """
        self._cleanup()
        
        # Determine norm for cosine sim
        query_norm = np.linalg.norm(query_embedding)
        if query_norm == 0:
            return None

        best_score = -1.0
        best_results = None

        with self.cache_lock:
            for entry in self.cache:
                cached_emb = entry['embedding']
                
                # Cosine Similarity
                dot_product = np.dot(query_embedding, cached_emb)
                cached_norm = np.linalg.norm(cached_emb)
                
                if cached_norm == 0:
                    continue
                    
                score = dot_product / (query_norm * cached_norm)
                
                if score > best_score:
                    best_score = score
                    best_results = entry['results']

        if best_score >= self.similarity_threshold:
            logger.info(f"⚡ EAG Cache Hit! Score: {best_score:.4f} for query: '{query_text}'")
            return best_results
        
        return None

    def update(self, query_embedding: np.ndarray, results: List[Dict], query_text: str = ""):
        """Update cache with new query results."""
        with self.cache_lock:
            self.cache.append({
                "embedding": query_embedding,
                "results": results,
                "timestamp": time.time(),
                "query_text": query_text
            })
            # Limit cache size to prevent RAM bloat (e.g., keep last 50)
            if len(self.cache) > 50:
                self.cache.pop(0)

    def _cleanup(self):
        """Remove expired entries."""
        now = time.time()
        with self.cache_lock:
            self.cache = [
                e for e in self.cache 
                if (now - e['timestamp']) < self.ttl
            ]

# Singleton Accessor
def get_ephemeral_cache():
    return EphemeralCache()
