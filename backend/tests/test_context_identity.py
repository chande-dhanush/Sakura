import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sakura_assistant.core.context_manager import ContextManager

def test_context():
    cm = ContextManager()
    ctx = cm.get_dynamic_context("Who am I?")
    print("=== DYNAMIC CONTEXT ===")
    print(ctx)
    print("=======================")
    
    if "User: Dhanush" in ctx: print("✅ Name Found")
    else: print("❌ Name Missing")
    
    # Check for theme (might be inside summary or explicit line)
    if "UI Theme: dark" in ctx or "Dark Mode" in ctx: print("✅ UI Theme Found")
    else: print("❌ UI Theme Missing")
    
    if "Interests: AI" in ctx: print("✅ Interests Found")
    else: print("❌ Interests Missing")

if __name__ == "__main__":
    test_context()
