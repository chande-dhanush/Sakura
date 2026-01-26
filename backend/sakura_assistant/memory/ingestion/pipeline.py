import os
import uuid
import logging
import threading
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor

from .handlers import get_handler_for_file
from .chunking import chunk_text_semantics
from ..chroma_store.store import get_doc_store
from ..metadata import get_metadata_manager
from ...utils.file_registry import get_file_registry
from ...core.ingest_state import set_ingesting
from ...config import GROQ_API_KEY, GOOGLE_API_KEY

# Note: delete_document import removed - was causing circular import with tools.py

logger = logging.getLogger(__name__)

class IngestionPipeline:
    """
    Robust ingestion pipeline with LLM summarization and Per-Doc Isolation.
    """
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2) # Limit concurrency
        self._lock = threading.Lock()
        self.llm = self._init_llm()

    def _init_llm(self):
        try:
            if GROQ_API_KEY:
                return ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1, groq_api_key=GROQ_API_KEY)
            if GOOGLE_API_KEY:
                return ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1, google_api_key=GOOGLE_API_KEY)
        except:
            return None

    def ingest_file_async(self, file_path: str, metadata: Optional[Dict] = None) -> str:
        """Submit background ingestion."""
        file_id = str(uuid.uuid4())
        self.executor.submit(self._process_file, file_path, file_id, metadata)
        return file_id

    def ingest_file_sync(self, file_path: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Blocking ingestion."""
        file_id = str(uuid.uuid4())
        return self._process_file(file_path, file_id, metadata)

    def _generate_summary(self, text: str) -> Dict[str, Any]:
        """Generate description and tags via LLM."""
        if not self.llm:
            return {"description": text[:200] + "...", "tags": []}
            
        try:
            prompt = f"""Analyze this document content (first 3000 chars):
{text[:3000]}...

Task:
1. Write a 1-sentence description.
2. Extract 3-5 keywords/tags.

Response Format (JSON):
{{
  "description": "...",
  "tags": ["..."]
}}
"""
            res = self.llm.invoke([HumanMessage(content=prompt)]).content
            import re
            match = re.search(r"\{.*\}", res, re.DOTALL)
            if match:
                import json
                return json.loads(match.group())
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            
        return {"description": text[:200] + "...", "tags": []}

    def _process_file(self, file_path: str, file_id: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        set_ingesting(True)
        try:
            if not os.path.exists(file_path):
                return {"error": True, "message": "File not found."}

            filename = os.path.basename(file_path)
            
            # 1. Get Handler
            handler = get_handler_for_file(file_path)
            if not handler:
                return {"error": True, "message": f"No handler for file type: {filename}"}

            # 2. Extract Text
            text = handler.extract_text(file_path)
            if not text or not text.strip():
                return {"error": True, "message": "Extracted text is empty."}

            # 3. Generate Metadata (Summary + Tags)
            logger.info(f"Generating summary for {filename}...")
            llm_meta = self._generate_summary(text)
            
            full_metadata = {
                "file_id": file_id,
                "filename": filename,
                "path": file_path,
                "description": llm_meta.get("description", ""),
                "tags": llm_meta.get("tags", [])
            }
            if metadata:
                full_metadata.update(metadata)

            # 4. Save Metadata (JSON)
            logger.info(f"Saving metadata for {file_id}...")
            meta_mgr = get_metadata_manager()
            meta_mgr.save_metadata(file_id, full_metadata)

            # 5. Chunking
            chunks = chunk_text_semantics(text, metadata={"source": filename, "file_id": file_id})
            if not chunks:
                return {"error": True, "message": "No chunks generated."}

            # 6. Store in Per-Doc Chroma
            logger.info(f"Embedding {len(chunks)} chunks for {file_id}...")
            store = get_doc_store(file_id)
            
            # 6.5 Embeddings
            from ..chroma_store.model import get_embedding_model
            model = get_embedding_model()
            
            ids = [c["id"] for c in chunks]
            texts = [c["text"] for c in chunks]
            c_metas = [c["metadata"] for c in chunks]
            
            # Add file_id to chunk metadata
            for m in c_metas:
                m["file_id"] = file_id
            
            embeddings = model.encode(texts).tolist()
            
            store.add_documents(ids, embeddings, c_metas, texts)

            # 7. Register in Registry (Legacy/UI support)
            registry = get_file_registry()
            registry.add_file(
                file_id=file_id,
                filename=filename,
                file_type=handler.file_type,
                chunk_count=len(chunks),
                metadata=full_metadata
            )

            return {
                "error": False,
                "file_id": file_id,
                "filename": filename,
                "chunks": len(chunks),
                "summary": full_metadata["description"],
                "message": f" Ingested {filename} ({len(chunks)} chunks)"
            }

        except Exception as e:
            logger.error(f"Ingestion failed for {file_path}: {e}")
            return {"error": True, "message": f"Ingestion failed: {str(e)}"}
        finally:
            set_ingesting(False)

# Singleton
_pipeline = IngestionPipeline()

def get_ingestion_pipeline():
    return _pipeline
