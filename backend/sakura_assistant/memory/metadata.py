import os
import json
import logging
from typing import Dict, List, Optional
from ..utils.pathing import get_project_root

logger = logging.getLogger(__name__)

METADATA_DIR = os.path.join(get_project_root(), "data", "document_metadata")

class MetadataManager:
    """
    Manages metadata JSON files for documents.
    Each document has a corresponding <doc_id>.json file.
    """
    
    def __init__(self):
        os.makedirs(METADATA_DIR, exist_ok=True)
        self.cache: Dict[str, Dict] = {} # lazy cache

    def save_metadata(self, doc_id: str, data: Dict) -> bool:
        """Save metadata for a document."""
        try:
            path = os.path.join(METADATA_DIR, f"{doc_id}.json")
            
            # Ensure doc_id is in data
            data["doc_id"] = doc_id
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            self.cache[doc_id] = data
            return True
        except Exception as e:
            logger.error(f"Failed to save metadata for {doc_id}: {e}")
            return False

    def get_metadata(self, doc_id: str) -> Optional[Dict]:
        """Get metadata for a document."""
        if doc_id in self.cache:
            return self.cache[doc_id]
            
        try:
            path = os.path.join(METADATA_DIR, f"{doc_id}.json")
            if not os.path.exists(path):
                return None
                
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.cache[doc_id] = data
            return data
        except Exception as e:
            logger.error(f"Failed to load metadata for {doc_id}: {e}")
            return None

    def list_all_metadata(self) -> List[Dict]:
        """List all available document metadata."""
        results = []
        try:
            if not os.path.exists(METADATA_DIR):
                return []
                
            for filename in os.listdir(METADATA_DIR):
                if filename.endswith(".json"):
                    doc_id = filename[:-5]
                    meta = self.get_metadata(doc_id)
                    if meta:
                        results.append(meta)
        except Exception as e:
            logger.error(f"Failed to list metadata: {e}")
            
        return results

    def delete_metadata(self, doc_id: str) -> bool:
        """Delete metadata for a document."""
        try:
            path = os.path.join(METADATA_DIR, f"{doc_id}.json")
            if os.path.exists(path):
                os.remove(path)
            
            if doc_id in self.cache:
                del self.cache[doc_id]
                
            return True
        except Exception as e:
            logger.error(f"Failed to delete metadata for {doc_id}: {e}")
            return False

# Singleton
_metadata_manager = MetadataManager()

def get_metadata_manager():
    return _metadata_manager
