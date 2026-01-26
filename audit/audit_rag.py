"""
Sakura War Room Audit: RAG Faithfulness & Agentic Quality
==========================================================
Impartial audit using "LLM-as-a-Judge" methodology.
Evaluates:
1. Memory RAG (FAISS Vector Store) - Refined Query
2. Agentic RAG (Web Search Tool)
3. Document RAG (Chroma Per-Doc Store)

Metrics:
- Context Precision: Is the retrieved info relevant? (0.0 - 1.0)
"""
import os
import sys
import json
import time
import asyncio
import uuid
from typing import List, Dict

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sakura_assistant.core.infrastructure.container import get_container
from sakura_assistant.memory.faiss_store.store import get_memory_store
try:
    from sakura_assistant.core.tools_libs.web import web_search
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

# Document RAG Imports
try:
    from sakura_assistant.memory.ingestion.pipeline import get_ingestion_pipeline
    from sakura_assistant.memory.chroma_store.store import get_doc_store
    from sakura_assistant.memory.chroma_store.model import get_embedding_model
    DOC_RAG_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Document RAG imports failed: {e}")
    DOC_RAG_AVAILABLE = False

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "audit_artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

# Judge Prompts
JUDGE_PROMPT = """
You are an impartial RAG AI Auditor. Grade the retrieval quality for the given query.

Query: {query}
Retrieved Context:
{context}

Task: Rate the **Relevance** of the retrieved context to the query.
- Score 0.0: Irrelevant, hallucinated, or wrong topic.
- Score 0.5: Partially relevant, misses key details.
- Score 1.0: Highly relevant, contains the answer.

Return ONLY the numeric score (e.g., 0.8). Do not explain.
"""

class RagAuditor:
    def __init__(self):
        print("⚖️  Initializing Impartial LLM Judge...")
        self.container = get_container()
        self.judge_llm = self.container.get_planner_llm()
        self.memory = get_memory_store()
        
    async def judge_relevance(self, query: str, context: str) -> float:
        """Use LLM to score context relevance."""
        if not context or "No relevant" in context:
            return 0.0
            
        prompt = JUDGE_PROMPT.format(query=query, context=context)
        try:
            response = self.judge_llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            import re
            match = re.search(r"0\.\d+|1\.0|0|1", content)
            if match:
                return float(match.group(0))
            return 0.0
        except Exception as e:
            print(f"   ⚠️ Judge error: {e}")
            return 0.0

    async def audit_memory_rag(self):
        print("\n🧠 Auditing Memory RAG (FAISS)...")
        
        # 1. Seed Memory with known facts
        seed_facts = [
            ("The project code name is Sakura V10.", "project_code"),
            ("The panic button code is 1999.", "security_code"),
            ("Dhanush prefers dark mode interfaces.", "pref_ui")
        ]
        
        print(f"   🌱 Seeding {len(seed_facts)} test memories...")
        for fact, _ in seed_facts:
            self.memory.add_message(fact, role="system")
        time.sleep(1) # Allow indexing
        
        test_cases = [
            "What is the project code name?",
            "What is the panic button code?",
            "What does the user like?"  # Refined "Positive" query
        ]
        
        results = []
        for query in test_cases:
            print(f"   🔍 Query: {query}")
            context = self.memory.get_context_for_query(query)
            score = await self.judge_relevance(query, context)
            print(f"      Score: {score}/1.0")
            results.append({"query": query, "score": score, "type": "Memory"})
            
        return results

    async def audit_agentic_rag(self):
        print("\n🌐 Auditing Agentic RAG (Web Search)...")
        if not WEB_AVAILABLE:
            print("   ⚠️ Web Search tool not available. Skipping.")
            return []
            
        test_cases = [
            "What is the current price of Bitcoin?",
            "Who is the CEO of OpenAI?",
            "Latest version of Python?"
        ]
        
        results = []
        for query in test_cases:
            print(f"   🔍 Query: {query}")
            try:
                # Use invoke for StructuredTool
                context = web_search.invoke({"query": query})
                score = await self.judge_relevance(query, str(context))
                print(f"      Score: {score}/1.0")
                results.append({"query": query, "score": score, "type": "Web"})
            except Exception as e:
                print(f"      Error: {e}")
                results.append({"query": query, "score": 0.0, "type": "Web"})
                
        return results

    async def audit_document_rag(self):
        print("\n📄 Auditing Document RAG (Chroma)...")
        if not DOC_RAG_AVAILABLE:
            print("   ⚠️ Document RAG modules not available.")
            return []

        # 1. Create Dummy Doc
        dummy_path = os.path.join(ARTIFACTS_DIR, "audit_test_doc.txt")
        secret_fact = "The secret ingredient for the potion is Star-Dust 42."
        with open(dummy_path, "w", encoding="utf-8") as f:
            f.write(f"CONFIDENTIAL REPORT\n\nSubject: Project Alchemy\n\n{secret_fact}\n\nEnd of Report.")
            
        # 2. Ingest
        print(f"   📥 Ingesting test document: {dummy_path}")
        pipeline = get_ingestion_pipeline()
        res = pipeline.ingest_file_sync(dummy_path)
        
        if res.get("error"):
            print(f"   ❌ Ingestion failed: {res.get('message')}")
            return [{"query": "Doc Lookup", "score": 0.0, "type": "Document"}]
            
        file_id = res["file_id"]
        print(f"   ✅ Ingested (ID: {file_id})")
        
        # 3. Query
        try:
            store = get_doc_store(file_id)
            model = get_embedding_model()
            
            query = "What is the secret ingredient?"
            print(f"   🔍 Query: {query}")
            
            q_emb = model.encode([query]).tolist()
            retrieval = store.query(query_embeddings=q_emb, n_results=1)
            
            if retrieval and retrieval['documents'] and retrieval['documents'][0]:
                context = retrieval['documents'][0][0] # First doc of first result
                score = await self.judge_relevance(query, context)
            else:
                context = "No results found."
                score = 0.0
                
            print(f"      Score: {score}/1.0")
            
            # Clean up (Wrap in try-except for Windows file lock stability)
            try:
                store.delete_store()
            except Exception as cleanup_err:
                print(f"   ⚠️ Cleanup warning (non-fatal): {cleanup_err}")
            
            return [{"query": query, "score": score, "type": "Document"}]
            
        except Exception as e:
            print(f"   ⚠️ Doc Query failed: {e}")
            return [{"query": "Doc Lookup", "score": 0.0, "type": "Document"}]

async def run_audit():
    auditor = RagAuditor()
    
    # Run Audits
    mem_results = await auditor.audit_memory_rag()
    web_results = await auditor.audit_agentic_rag()
    doc_results = await auditor.audit_document_rag()
    
    all_results = mem_results + web_results + doc_results
    
    # Calculate Stats
    avg_mem = sum(r['score'] for r in mem_results) / len(mem_results) if mem_results else 0
    avg_web = sum(r['score'] for r in web_results) / len(web_results) if web_results else 0
    avg_doc = sum(r['score'] for r in doc_results) / len(doc_results) if doc_results else 0
    
    # Generate Report
    report_path = os.path.join(ARTIFACTS_DIR, "rag_detailed_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("SAKURA V10 IMPARTIAL RAG AUDIT\n")
        f.write("==============================\n")
        f.write(f"Judge Model: {auditor.judge_llm.model_name if hasattr(auditor.judge_llm, 'model_name') else 'Llama-70B'}\n\n")
        
        f.write("🧠 MEMORY RAG (FAISS)\n")
        f.write(f"Average Relevance Score: {avg_mem:.2f}/1.0\n")
        for r in mem_results:
            f.write(f" - Q: {r['query']}\n   Score: {r['score']}\n")
            
        f.write("\n🌐 AGENTIC RAG (WEB)\n")
        f.write(f"Average Relevance Score: {avg_web:.2f}/1.0\n")
        for r in web_results:
            f.write(f" - Q: {r['query']}\n   Score: {r['score']}\n")

        f.write("\n📄 DOCUMENT RAG (CHROMA)\n")
        f.write(f"Average Relevance Score: {avg_doc:.2f}/1.0\n")
        for r in doc_results:
            f.write(f" - Q: {r['query']}\n   Score: {r['score']}\n")




if __name__ == "__main__":
    asyncio.run(run_audit())
