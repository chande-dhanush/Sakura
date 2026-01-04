"""
Sanity Check Script for Sakura V9.1
====================================
Run before every commit to catch major breaks.

Usage:
    python -m sakura_assistant.tests.sanity_check

EXIT CODES:
    0 = All checks passed
    1 = Critical failure
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def check_tool_count():
    """Verify all tools are registered."""
    try:
        from sakura_assistant.core.tools import get_all_tools
        tools = get_all_tools()
        count = len(tools)
        
        # V9.1: Expected tool count (update if you add/remove tools)
        EXPECTED = 48
        
        if count >= EXPECTED:
            print(f"✅ Tool count: {count} (expected >= {EXPECTED})")
            return True
        else:
            print(f"❌ Tool count: {count} (expected >= {EXPECTED})")
            return False
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        print("   (Circular import? Check tools.py imports)")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def check_config_imports():
    """Verify config.py loads without errors."""
    try:
        from sakura_assistant import config
        assert hasattr(config, 'TOOL_GROUPS')
        assert hasattr(config, 'TOOL_GROUPS_UNIVERSAL')
        print("✅ Config loaded successfully")
        return True
    except Exception as e:
        print(f"❌ Config failed: {e}")
        return False


def check_world_graph():
    """Verify World Graph initializes."""
    try:
        from sakura_assistant.core.world_graph import WorldGraph
        wg = WorldGraph()
        assert wg is not None
        print("✅ World Graph initializes")
        return True
    except Exception as e:
        print(f"❌ World Graph failed: {e}")
        return False


def main():
    print("=" * 50)
    print("SAKURA V9.1 SANITY CHECK")
    print("=" * 50)
    
    checks = [
        ("Config", check_config_imports),
        ("World Graph", check_world_graph),
        ("Tools", check_tool_count),
    ]
    
    results = []
    for name, check in checks:
        try:
            results.append(check())
        except Exception as e:
            print(f"❌ {name} crashed: {e}")
            results.append(False)
    
    print("=" * 50)
    
    if all(results):
        print("✅ ALL CHECKS PASSED - Safe to commit")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Do not commit!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
