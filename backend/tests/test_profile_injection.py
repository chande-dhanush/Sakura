import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from sakura_assistant.core.context_manager import ContextManager

def test_profile_injection():
    cm = ContextManager()
    context = cm.get_dynamic_context("Who am I?")
    
    print("=== DYNAMIC CONTEXT OUTPUT ===")
    print(context)
    print("==============================")
    
    if "USER PROFILE (SIDECAR)" in context:
        print("✅ Header Found")
    else:
        print("❌ Header Missing")
        
    if "Dhanush" in context and "AI Engineer" in context:
        print("✅ Data Found")
    else:
        print("❌ Data Missing")

if __name__ == "__main__":
    test_profile_injection()
