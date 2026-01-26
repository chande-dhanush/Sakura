"""Test sidecar vs direct Python to find the issue."""
import sys
import os

print("=== Environment Check ===")
print(f"Frozen: {getattr(sys, 'frozen', False)}")

from sakura_assistant.utils.pathing import get_project_root
print(f"Project root: {get_project_root()}")

# Check if .env exists there
env_path = os.path.join(get_project_root(), ".env")
print(f".env exists at root: {os.path.exists(env_path)}")

# Check API keys
groq_key = os.getenv("GROQ_API_KEY", "")
print(f"GROQ_API_KEY loaded: {bool(groq_key)} ({groq_key[:10]}... if key)")

from sakura_assistant.config import USER_DETAILS
print(f"USER_DETAILS: {len(USER_DETAILS)} chars")

# Test LLM
print("\n=== Testing LLM ===")
from sakura_assistant.core.infrastructure.container import get_container
c = get_container()
print(f"has_groq: {c.has_groq}")
print(f"has_backup: {c.has_backup}")

if c.has_groq:
    try:
        llm = c.get_responder_llm()
        from langchain_core.messages import HumanMessage
        resp = llm.invoke([HumanMessage(content="say hi")])
        print(f"LLM Response: {resp.content[:50]}...")
    except Exception as e:
        print(f"LLM ERROR: {type(e).__name__}: {e}")
else:
    print("NO GROQ KEY - THIS IS THE PROBLEM")
