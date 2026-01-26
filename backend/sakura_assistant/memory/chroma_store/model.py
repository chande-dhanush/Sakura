import gc
import time
import threading
import logging
from sentence_transformers import SentenceTransformer
from ...config import EMBEDDING_IDLE_TIMEOUT

logger = logging.getLogger(__name__)

# Configuration
EMBEDDING_MODEL_NAME = "BAAI/bge-large-en-v1.5"

# P0: Lazy load with thread safety and idle unload
_embedding_model = None
_embed_lock = threading.Lock()
_embed_last_used = 0
_embed_unload_timer = None

def get_embedding_model():
    """Lazy-load Chroma embedding model. Thread-safe with idle unload."""
    global _embedding_model, _embed_last_used, _embed_unload_timer
    
    with _embed_lock:
        if _embedding_model is None:
            logger.info(f" Loading Chroma embedding model: {EMBEDDING_MODEL_NAME}...")
            print(f" Loading Chroma embedding model: {EMBEDDING_MODEL_NAME}...")
            try:
                _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
                logger.info(" Chroma embeddings loaded.")
                print(" Chroma embeddings loaded.")
            except Exception as e:
                logger.error(f"Failed to load Chroma embedding model: {e}")
                print(f" Failed to load embedding model: {e}")
                return None
        
        _embed_last_used = time.time()
        _schedule_unload()
        return _embedding_model

def _schedule_unload():
    """Schedule embedding unload after idle timeout."""
    global _embed_unload_timer
    
    if _embed_unload_timer:
        _embed_unload_timer.cancel()
    
    _embed_unload_timer = threading.Timer(
        EMBEDDING_IDLE_TIMEOUT, 
        _check_and_unload
    )
    _embed_unload_timer.daemon = True
    _embed_unload_timer.start()

def _check_and_unload():
    """Check if embeddings have been idle and unload if so."""
    global _embedding_model
    
    with _embed_lock:
        if _embedding_model is None:
            return
        
        idle_time = time.time() - _embed_last_used
        if idle_time >= EMBEDDING_IDLE_TIMEOUT:
            unload_embedding_model()

def unload_embedding_model():
    """Unload Chroma embedding model to free memory."""
    global _embedding_model
    
    with _embed_lock:
        if _embedding_model is not None:
            logger.info(" Unloading Chroma embeddings (idle timeout)...")
            print(" Unloading Chroma embeddings (idle timeout)...")
            del _embedding_model
            _embedding_model = None
            gc.collect()
            logger.info(" Chroma embeddings unloaded.")
            print(" Chroma embeddings unloaded.")

def is_loaded() -> bool:
    """Check if embedding model is currently loaded."""
    return _embedding_model is not None
