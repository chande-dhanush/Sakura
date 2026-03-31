from langchain_core.tools import tool
from typing import List, Dict, Any, Optional
from .common import log_api_call

import re

# --- Memory & RAG ---

def _slugify(text: str) -> str:
    """Convert text to valid entity ID."""
    slug = re.sub(r'[^a-z0-9]+', '_', text.lower())
    return slug[:50]

@tool
def update_user_memory(category: str, key: str, value: str) -> str:
    """
    Save a fact about the user for long-term memory.
    V17.1: Now writes to BOTH PreferenceStore AND WorldGraph.
    """
    try:
        from ...utils.preferences import update_preference
        
        # Keep: Existing PreferenceStore update (backward compatibility)
        update_preference(category, key, value)
        
        # V17.1: Also update WorldGraph
        try:
            from ..graph.world_graph import get_world_graph
            from ..graph.nodes import EntityType, EntitySource
            
            wg = get_world_graph()
            
            # Detect preference type via keyword analysis
            fact = f"{key}: {value}"
            fact_lower = fact.lower()
            
            if any(kw in fact_lower for kw in ["love", "like", "enjoy", "prefer", "favorite", "fond of"]):
                entity_id = f"pref:like:{_slugify(key)}"
                summary = f"Likes: {value}"
                entity_type = EntityType.PREFERENCE
            elif any(kw in fact_lower for kw in ["hate", "dislike", "avoid", "can't stand", "detest"]):
                entity_id = f"pref:dislike:{_slugify(key)}"
                summary = f"Dislikes: {value}"
                entity_type = EntityType.PREFERENCE
            else:
                entity_id = f"fact:{category}:{_slugify(key)}"
                summary = f"{key}: {value}"
                entity_type = EntityType.FACT
            
            # Create or update entity
            wg.get_or_create_entity(
                type=entity_type,
                name=summary,
                source=EntitySource.USER_STATED,
                attributes={"category": category, "key": key, "value": value}
            )
            wg.save()
            
        except Exception as wg_err:
            print(f"⚠️ [update_user_memory] WorldGraph sync failed: {wg_err}")
            # Non-fatal, preference still saved to JSON
        
        return f"✅ Remembered: {key} = {value}"
    except Exception as e:
        return f"❌ Failed: {e}"


@tool
def ingest_document(path: str) -> str:
    """Ingest a document into user memory (RAG)."""
    try:
        from ...memory.ingestion.pipeline import get_ingestion_pipeline
        pipeline = get_ingestion_pipeline()
        result = pipeline.ingest_file_sync(path)
        if result.get("error"): return f" Error: {result.get('message')}"
        return f" Ingested '{result['filename']}' (ID: {result['file_id']})"
    except Exception as e:
        return f" Ingest failed: {e}"

@tool
def fetch_document_context(query: str) -> str:
    """Fetch relevant context from uploaded documents using AI Routing."""
    try:
        from ...memory.router import get_document_router
        router = get_document_router()
        return router.query(query)
    except Exception as e:
        return f" Retrieval error: {e}"

@tool
def list_uploaded_documents() -> str:
    """List all user-uploaded documents."""
    try:
        from ...utils.file_registry import get_file_registry
        files = get_file_registry().list_files()
        if not files: return "No documents."
        return "\n".join([f"- [{f['id']}] {f['filename']}" for f in files])
    except Exception as e:
        return f" Error: {e}"

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
        return " Deleted."
    except Exception as e:
        return f" Delete failed: {e}"

@tool
def get_rag_telemetry() -> str:
    """Get system health metrics for RAG."""
    try:
        from ...utils.telemetry import get_telemetry
        stats = get_telemetry().get_metrics()
        return str(stats)
    except Exception as e:
        return f" Error: {e}"

@tool
def trigger_reindex() -> str:
    """Manually trigger a full re-index."""
    try:
        from ...memory.maintenance import get_reindex_job
        return get_reindex_job().run_full_reindex()
    except Exception as e:
        return f" Error: {e}"

@tool
def query_ephemeral(ephemeral_id: str, query: str) -> str:
    """
    Query a specific ephemeral (temporary) Vector Store.
    Use this when a previous tool's output was too large and intercepted.
    """
    try:
        from ..ephemeral_manager import get_ephemeral_manager
        return get_ephemeral_manager().query(ephemeral_id, query)
    except Exception as e:
        return f" Query failed: {e}"

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
