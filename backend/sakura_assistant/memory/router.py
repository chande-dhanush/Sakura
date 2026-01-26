import json
import logging
from typing import List, Dict, Any, Optional

from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..config import GROQ_API_KEY, GOOGLE_API_KEY
from .metadata import get_metadata_manager
from .chroma_store.store import get_doc_store
from .chroma_store.model import get_embedding_model
from .ephemeral_cache import get_ephemeral_cache

logger = logging.getLogger(__name__)

class DocumentRouter:
    """
    Intelligent Router for Document Retrieval.
    Flow:
    1. Check Ephemeral Cache.
    2. Get Candidate Docs via LLM Classification (Metadata).
    3. Query Vector Stores for selected docs.
    4. Update Cache.
    """
    def __init__(self):
        self.llm = self._init_llm()
        self.meta_manager = get_metadata_manager()
        self.cache = get_ephemeral_cache()
        self.encoder = get_embedding_model()

    def _init_llm(self):
        """Initialize a fast LLM for routing."""
        try:
            if GROQ_API_KEY:
                return ChatGroq(
                    model="llama-3.3-70b-versatile", # Update to supported model
                    temperature=0.0,
                    groq_api_key=GROQ_API_KEY
                )
            if GOOGLE_API_KEY:
                return ChatGoogleGenerativeAI(
                    model="gemini-1.5-flash",
                    temperature=0.0,
                    google_api_key=GOOGLE_API_KEY
                )
        except Exception as e:
            logger.error(f"Router LLM init failed: {e}")
        return None

    def query(self, query_text: str, top_k_docs: int = 2) -> str:
        """
        Main entry point for RAG.
        Returns formatted context string.
        """
        if not query_text or not query_text.strip():
            return ""

        # 0. Encode Query (Needed for Cache & Search)
        if not self.encoder:
            return " Embedding model not loaded."
            
        try:
            query_emb = self.encoder.encode(query_text)
        except Exception as e:
            return f" Embedding failed: {e}"

        # 1. Check Ephemeral Cache (EAG)
        cached_results = self.cache.check(query_emb, query_text)
        if cached_results:
            return self._format_results(cached_results, source="Memory Cache (EAG) ⚡")

        # 2. Get All Metadata
        all_meta = self.meta_manager.list_all_metadata()
        if not all_meta:
            return "" # No docs

        # 3. LLM Routing
        selected_doc_ids = self._route_query(query_text, all_meta, top_k=top_k_docs)
        if not selected_doc_ids:
            return " No relevant documents found."

        # 4. Vector Search per Doc
        aggregated_results = []
        for doc_id in selected_doc_ids:
            store = get_doc_store(doc_id)
            res = store.query(query_embeddings=[query_emb.tolist()], n_results=3)
            
            if res and res['ids']:
                ids = res['ids'][0]
                docs = res['documents'][0]
                metas = res['metadatas'][0]
                dists = res['distances'][0]
                
                for i, doc in enumerate(docs):
                    aggregated_results.append({
                        "content": doc,
                        "metadata": metas[i],
                        "score": 1.0 - dists[i],
                        "doc_id": doc_id
                    })

        # 5. Sort & Format
        aggregated_results.sort(key=lambda x: x['score'], reverse=True)
        final_results = aggregated_results[:5]
        
        # 6. Update Cache
        self.cache.update(query_emb, final_results, query_text)

        return self._format_results(final_results, source="Document Store ")

    def _route_query(self, query: str, metadatas: List[Dict], top_k: int) -> List[str]:
        """Ask LLM which docs are relevant."""
        if not self.llm:
            # Fallback: Searching all if LLM dead is risky, but better than nothing?
            # Or just return top 1? Let's return all ids if few, else none.
            return [m['doc_id'] for m in metadatas][:3]

        prompt = f"""You are a Document Retrieval Router.
Query: "{query}"

Available Documents:
"""
        for i, m in enumerate(metadatas):
            prompt += f"{i}. ID: {m['doc_id']} | File: {m.get('filename')} | Desc: {m.get('description', 'No desc')}\n"

        prompt += f"""
Task: Select the top {top_k} document IDs that are relevant to the query.
Format: Return ONLY a JSON list of strings, e.g. ["id1", "id2"].
If none relevant, return [].
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)]).content
            import re
            # Extract JSON list using regex
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if match:
                return json.loads(match.group())
            else:
                # Fallback: try to find ids directly if JSON fails
                return []
        except Exception as e:
            logger.error(f"Routing failed: {e}")
            
        return []

    def _format_results(self, results: List[Dict], source: str) -> str:
        """Format results for context injection."""
        if not results: return " No context found."
        
        out = [f"### Relevant Context ({source})"]
        for r in results:
            meta = r.get('metadata', {})
            filename = meta.get('filename', 'Unknown')
            page = f" (Pg {meta.get('page_number')})" if meta.get('page_number') else ""
            out.append(f"**File**: {filename}{page} | **Score**: {r.get('score', 0):.2f}")
            out.append(f"> {r['content']}")
            out.append("---")
            
        return "\n".join(out)

# Singleton
_router = DocumentRouter()

def get_document_router():
    return _router
