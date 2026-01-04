from langchain_core.tools import tool
from typing import List, Dict, Any, Optional
from .common import log_api_call

# --- Memory & RAG ---

@tool
def update_user_memory(category: str, key: str, value: str) -> str:
    """Save a fact about the user for long-term memory."""
    try:
        from ...utils.preferences import update_preference
        update_preference(category, key, value)
        return f"🧠 Memory updated: {category} -> {key}={value}"
    except Exception as e:
        return f"❌ Failed: {e}"

@tool
def ingest_document(path: str) -> str:
    """Ingest a document into user memory (RAG)."""
    try:
        from ...memory.ingestion.pipeline import get_ingestion_pipeline
        pipeline = get_ingestion_pipeline()
        result = pipeline.ingest_file_sync(path)
        if result.get("error"): return f"❌ Error: {result.get('message')}"
        return f"✅ Ingested '{result['filename']}' (ID: {result['file_id']})"
    except Exception as e:
        return f"❌ Ingest failed: {e}"

@tool
def fetch_document_context(query: str) -> str:
    """Fetch relevant context from uploaded documents using AI Routing."""
    try:
        from ...memory.router import get_document_router
        router = get_document_router()
        return router.query(query)
    except Exception as e:
        return f"❌ Retrieval error: {e}"

@tool
def list_uploaded_documents() -> str:
    """List all user-uploaded documents."""
    try:
        from ...utils.file_registry import get_file_registry
        files = get_file_registry().list_files()
        if not files: return "No documents."
        return "\n".join([f"- [{f['id']}] {f['filename']}" for f in files])
    except Exception as e:
        return f"❌ Error: {e}"

@tool
def delete_document(doc_id: str) -> str:
    """Delete a document by ID."""
    try:
        from ...memory.metadata import get_metadata_manager
        from ...memory.chroma_store.store import get_doc_store
        from ...utils.file_registry import get_file_registry
        
        get_metadata_manager().delete_metadata(doc_id)
        get_doc_store(doc_id).delete_store()
        get_file_registry().delete_file(doc_id)
        return "✅ Deleted."
    except Exception as e:
        return f"❌ Delete failed: {e}"

@tool
def get_rag_telemetry() -> str:
    """Get system health metrics for RAG."""
    try:
        from ...utils.telemetry import get_telemetry
        stats = get_telemetry().get_metrics()
        return str(stats)
    except Exception as e:
        return f"❌ Error: {e}"

@tool
def trigger_reindex() -> str:
    """Manually trigger a full re-index."""
    try:
        from ...memory.maintenance import get_reindex_job
        return get_reindex_job().run_full_reindex()
    except Exception as e:
        return f"❌ Error: {e}"

# --- Meta Tools ---

@tool
def execute_actions(actions: List[Dict[str, Any]]) -> str:
    """Execute a list of tool actions widely valid."""
    # This is circular if implemented here since we need to import ALL tools.
    # It's better implemented in the Facade (tools.py).
    return "Please execute actions sequentially."

# --- Note Tools (Re-exported logic wrapper) ---
# Note tool implementation is already modular in utils/note_tools.py
# We just need to ensure the facade imports it.
