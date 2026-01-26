"""
Verification Script for V12 Features
====================================
Tests:
1. Smart Caching (First hit vs Cache hit)
2. Broadcaster (Events received)
"""
import sys
import os
import asyncio
import time
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sakura_assistant.core.tools_libs.research import SmartResearcher
from sakura_assistant.core.broadcaster import get_broadcaster

# Mock Embedder
class MockEmbedder:
    def embed_query(self, text):
        return [0.1] * 384 # Dummy vector

# Mock Chroma
class MockCollection:
    def __init__(self):
        self.data = {} # id -> (doc, meta, emb)
    
    def query(self, query_embeddings, n_results, include):
        # Linear search for verification
        results = {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}
        
        if self.data:
            # Return the first item as a "match" with 0 distance for testing
            first_id = list(self.data.keys())[0]
            doc, meta, emb = self.data[first_id]
            results["ids"][0].append(first_id)
            results["distances"][0].append(0.0) # Exact match
            results["documents"][0].append(doc)
            results["metadatas"][0].append(meta)
        
        return results

    def add(self, ids, embeddings, documents, metadatas):
        for i, doc_id in enumerate(ids):
            self.data[doc_id] = (documents[i], metadatas[i], embeddings[i])

class MockChromaClient:
    def __init__(self):
        self.collection = MockCollection()
    
    def get_or_create_collection(self, name):
        return self.collection

async def run_test():
    print(" Starting V12 Verification...")
    
    # 1. Setup Broadcaster Listener
    events = []
    def listener(event, data):
        events.append((event, data))
        print(f"    Event: {event}")
    
    broadcaster = get_broadcaster()
    broadcaster.add_listener(listener)
    
    # 2. Mock ALL Dependencies
    # Patch where they are imported FROM, because research.py imports them inside the function
    with patch('sakura_assistant.memory.ingestion.embedder.get_embedder', return_value=MockEmbedder()), \
         patch('sakura_assistant.memory.chroma_store.store.get_chroma_client', return_value=MockChromaClient()), \
         patch('tavily.TavilyClient') as MockTavily:
         
        # Setup Tavily Mock
        mock_tavily_instance = MagicMock()
        mock_tavily_instance.search.return_value = {
            "results": [{"title": "Test Page", "url": "http://test.com", "content": "This is a test result."}]
        }
        MockTavily.return_value = mock_tavily_instance
        
        researcher = SmartResearcher()
        
        # --- Run 1: Cold Start (Should call Tavily) ---
        print("\n[Run 1] Cold Research...")
        res1 = await researcher.research("test query")
        
        # Verify Tavily called
        if mock_tavily_instance.search.called:
            print(" PASS: Tavily called on cold start")
        else:
            print(" FAIL: Tavily NOT called")
            
        # Verify "research_start" and "tool_start" events
        event_names = [e[0] for e in events]
        if "research_start" in event_names and "tool_start" in event_names:
             print(" PASS: Broadcast events received (research_start, tool_start)")
        else:
             print(f" FAIL: Missing events. Got: {event_names}")
        
        # --- Run 2: Cache Hit (Should NOT call Tavily) ---
        print("\n[Run 2] Cached Research...")
        mock_tavily_instance.search.reset_mock()
        events.clear()
        
        res2 = await researcher.research("test query")
        
        # Verify Tavily NOT called
        if not mock_tavily_instance.search.called:
            print(" PASS: Tavily SKIPPED on cache hit")
        else:
            print(" FAIL: Tavily called despite cache")
            
        # Verify "cache_hit" event
        event_names = [e[0] for e in events]
        if "cache_hit" in event_names:
            print(" PASS: Broadcast event 'cache_hit' received")
        else:
            print(f" FAIL: Missing cache_hit event. Got: {event_names}")
            
    print("\n V12 Feature Verification Complete.")

if __name__ == "__main__":
    asyncio.run(run_test())
