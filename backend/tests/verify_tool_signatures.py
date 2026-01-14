"""
Verification Script: Tool Signature Check
==========================================

Run this BEFORE merging any decorator changes to tools.py.
Verifies that LangChain tool introspection still works.

Usage:
    python -m sakura_assistant.tests.verify_tool_signatures
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def verify_tools():
    """
    Verify that all tools have proper signatures for LangChain.
    """
    from sakura_assistant.core.tools import get_all_tools
    
    print("=" * 60)
    print("TOOL SIGNATURE VERIFICATION")
    print("=" * 60)
    
    tools = get_all_tools()
    failed = []
    
    for tool in tools:
        name = getattr(tool, 'name', 'UNKNOWN')
        args = getattr(tool, 'args', {})
        
        # Check 1: Tool has a name
        if not name or name == 'UNKNOWN':
            failed.append(f"{tool} - Missing 'name' attribute")
            continue
        
        # Check 2: Tool has args (even if empty dict)
        if args is None:
            failed.append(f"{name} - 'args' is None (decorator may have broken signature)")
            continue
        
        # Check 3: Verify description exists
        desc = getattr(tool, 'description', '')
        if not desc:
            failed.append(f"{name} - Missing description")
            continue
        
        print(f"✅ {name}: {len(args)} args | {desc[:40]}...")
    
    print("=" * 60)
    
    if failed:
        print(f"❌ FAILED: {len(failed)} tool(s) have issues:")
        for f in failed:
            print(f"   - {f}")
        return False
    else:
        print(f"✅ ALL {len(tools)} TOOLS PASSED VERIFICATION")
        return True


if __name__ == "__main__":
    success = verify_tools()
    sys.exit(0 if success else 1)
