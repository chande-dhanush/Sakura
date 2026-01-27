"""
V11.1 Agentic Web - Smart Researcher
"""
import os
import json
from langchain_core.tools import tool
from typing import Dict, Any, List

class SmartResearcher:
    def __init__(self):
        self._llm = None  # Lazy load to avoid circular deps if possible
        
    def _get_llm(self):
        if not self._llm:
            # We need a lightweight LLM instance, or reuse the main one.
            # For now, let's create a dedicated one or import global
            from ..infrastructure.container import get_container
            self._llm = get_container().get_responder_llm() # Use Responder (70B) for synthesis
        return self._llm

    def _determine_tier(self, query: str) -> str:
        """
        Heuristic to choose search tier.
        Simple Fact = Basic (1 credit)
        Complex Topic = Advanced (2 credits)
        """
        query_lower = query.lower()
        
        # Tier 1 Indicators (Simple Facts)
        simple_triggers = ["who is", "what is", "price of", "weather in", "when did", "define", "height of"]
        if any(query_lower.startswith(t) for t in simple_triggers) and len(query.split()) < 8:
            return "basic"
            
        # Tier 2 Indicators (Comparison, Deep Dive)
        complex_triggers = ["compare", "vs", "versus", "best", "review", "analysis", "summary of", "how to", "why"]
        if any(t in query_lower for t in complex_triggers):
            return "advanced"
            
        # Default fallback: Basic for short queries, Advanced for long ones
        return "basic" if len(query.split()) < 6 else "advanced"

    async def research(self, query: str) -> str:
        """
        Execute Two-Tier Research with Smart Caching.
        V17.5: Emits progress updates for SSE streaming.
        """
        from tavily import TavilyClient
        from ..infrastructure.broadcaster import broadcast
        
        # V17.5: Get progress emitter
        emitter = None
        try:
            from ...utils.progress_emitter import get_progress_emitter
            emitter = get_progress_emitter()
        except:
            pass
        
        # 0. Broadcasting Start
        broadcast("research_start", {"query": query, "step": "Checking Cache..."})
        if emitter:
            emitter.tool_progress("research_topic", f"🔬 Starting research on '{query[:40]}...'")
        
        # --- SMART CACHING START ---
        collection = None
        query_emb = None
        
        try:
            # Import using absolute path for robustness
            from sakura_assistant.memory.chroma_store.store import get_chroma_client
            client = get_chroma_client()
            collection = client.get_or_create_collection(name="search_cache")
            
            if emitter:
                emitter.tool_progress("research_topic", "📂 Checking cache...")
            
            # Embed query
            try:
                from sakura_assistant.memory.chroma_store.model import get_embedding_model
                model = get_embedding_model()
                if model:
                     query_emb = model.encode(query).tolist()
                else:
                     raise ImportError("Model failed to load")
            except Exception as e:
                # Fallback for Test Environment
                print(f"⚠️ Embedder Import Failed: {e}. Using Mock.")
                import random
                rng = random.Random(query) 
                query_emb = [rng.random() for _ in range(384)]

            # Query Cache
            results = collection.query(
                query_embeddings=[query_emb],
                n_results=1,
                include=["documents", "distances", "metadatas"]
            )
            
            if results["ids"][0]:
                distance = results["distances"][0][0]
                if distance < 0.1: 
                    cached_summary = results["documents"][0][0]
                    timestamp = results["metadatas"][0][0].get("timestamp")
                    print(f"⚡ SmartResearcher: Cache Hit (dist={distance:.4f})")
                    broadcast("cache_hit", {"query": query, "distance": distance})
                    if emitter:
                        emitter.tool_success("research_topic", f"⚡ Cache hit! Using cached result")
                    return f" **[Cached Result - {timestamp}]:**\n{cached_summary}"
        except Exception as e:
            print(f"⚠️ Cache check failed: {e}")
            # Do NOT crash, proceed to live search

        # --- SMART CACHING END ---

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return " Tavily API Key missing."

        client = TavilyClient(api_key=api_key)
        tier = self._determine_tier(query)
        
        print(f"️ SmartResearcher: Analyzing '{query}' via Tier: {tier.upper()}")
        broadcast("tool_start", {"tool": "Tavily", "tier": tier, "query": query})
        
        if emitter:
            emitter.tool_progress("research_topic", f"🔍 Phase 1/3: Searching with Tavily ({tier})...")
        
        try:
            results = []
            final_output = ""
            
            if tier == "basic":
                # Tier 1: Fast, cheap (1 credit)
                response = client.search(query, search_depth="basic", max_results=3)
                results = response.get("results", [])
                
                # Simple summary for basic facts
                if not results:
                    if emitter:
                        emitter.tool_progress("research_topic", "⚠️ No results found")
                    return " No results found."
                
                if emitter:
                    emitter.tool_progress("research_topic", f"📄 Phase 2/3: Found {len(results)} sources")
                
                # Just return a neat list for basic facts, or simple synthesis
                out = [f"**Research Results (Basic):**"]
                for r in results:
                    out.append(f"- [{r['title']}]({r['url']}): {r['content']}")
                final_output = "\n".join(out)

            else:
                # Tier 2: Deep, expensive (2 credits)
                response = client.search(query, search_depth="advanced", include_raw_content=True, max_results=5)
                results = response.get("results", [])
                
                if not results:
                    if emitter:
                        emitter.tool_progress("research_topic", "⚠️ No results found")
                    return " No results found."
                
                if emitter:
                    emitter.tool_progress("research_topic", f"📄 Phase 2/3: Found {len(results)} sources, extracting content...")
                
                # Synthesize with LLM
                context = []
                for r in results:
                    # Use raw content if available and reasonable length, else snippet
                    content = r.get("raw_content", "")[:1000] if r.get("raw_content") else r.get("content", "")
                    context.append(f"Source: {r['title']} ({r['url']})\nContent: {content}\n---")
                
                context_str = "\n".join(context)
                
                if emitter:
                    emitter.tool_progress("research_topic", "🧠 Phase 3/3: Synthesizing with LLM...")
                
                prompt = f"""You are a Research Synthesizer.
                Query: {query}
                
                Context:
                {context_str}
                
                Instructions:
                1. Answer the query comprehensively based on the context.
                2. Use inline citations like [Source Name](url).
                3. If conflicting info, mention it.
                4. Be concise but deep.
                """
                
                llm = self._get_llm()
                from langchain_core.messages import SystemMessage, HumanMessage
                # Direct LLM call
                response = await llm.ainvoke([HumanMessage(content=prompt)])
                
                final_output = f" **Research Verdict:**\n\n{response.content}"

            # --- SAVE TO CACHE ---
            if collection and query_emb:
                try:
                    import time
                    import uuid
                    collection.add(
                        ids=[str(uuid.uuid4())],
                        embeddings=[query_emb],
                        documents=[final_output],
                        metadatas=[{"query": query, "timestamp": time.ctime(), "tier": tier}]
                    )
                    print(" Saved result to SmartCache")
                except Exception as e:
                    print(f"⚠️ Cache save failed: {e}")
            else:
                 print("⚠️ Cache save skipped (collection/embedding missing)")
            
            if emitter:
                emitter.tool_success("research_topic", f"✅ Research complete ({len(results)} sources)")
                
            return final_output

        except Exception as e:
            if emitter:
                emitter.tool_error("research_topic", str(e))
            return f" Research Error: {e}"

# Tool Wrapper
@tool
async def research_topic(query: str) -> str:
    """
    Perform smart research on a topic. 
    Use this for complex questions, comparisons, or deep dives. 
    Do NOT use for simple 'what time is it' or weather.
    """
    researcher = SmartResearcher()
    return await researcher.research(query)
