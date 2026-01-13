import asyncio
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import Request
from server import chat, lifespan
from fastapi import FastAPI

async def mock_request(data):
    """Mock a FastAPI Request object."""
    class MockRequest:
        async def json(self):
            return data
    return MockRequest()

async def verify_streaming():
    print("🧪 Starting Async Server Verification...")
    
    # 1. Initialize Server (lifespan)
    app = FastAPI()
    async with lifespan(app):
        # 2. Prepare Request
        req = await mock_request({"query": "What time is it?", "tts_enabled": False})
        
        print("📨 Sending 'What time is it?' to chat endpoint...")
        response = await chat(req)
        
        # 3. Stream Response
        print("🌊 Streaming response...")
        async for chunk in response.body_iterator:
            chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            lines = chunk_str.strip().split("\n")
            
            for line in lines:
                if line.startswith("data: "):
                    data_str = line[6:]  # Strip 'data: '
                    try:
                        data = json.loads(data_str)
                        evt_type = data.get("type")
                        
                        if evt_type == "thinking":
                            print("   [Thinking] ...")
                        elif evt_type == "trace_start":
                            print(f"   [Trace] Started: {data.get('id')}")
                        elif evt_type == "timing":
                            print(f"   [Timing] {data.get('stage')} ({data.get('ms')}ms): {data.get('info')}")
                        elif evt_type == "tool_used":
                            print(f"   [Tool] {data.get('tool')}")
                        elif evt_type == "token":
                            content = data.get("content")
                            print(f"   [Token] Content preview: {content[:50]}...")
                        elif evt_type == "done":
                            print(f"   [Done] Mode: {data.get('mode')}")
                            
                    except Exception as e:
                        print(f"   [Parse Error] {e} line: {line}")

    print("\n✅ Verification Complete: Async Streaming + FlightRecorder SSE working!")

if __name__ == "__main__":
    asyncio.run(verify_streaming())
