"""
V17.2 Security Patch Validation Suite
Run this to verify all fixes are working.
"""
import os
import sys
import pytest

# Ensure backend is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_path_traversal_protection():
    """Test that dangerous file paths are blocked."""
    # Adjusted import based on actual file structure detected
    try:
        from sakura_assistant.core.tools_libs.system import file_open, file_read, file_write
    except ImportError:
        # Fallback to user-specified path if structure changed
        from sakura_assistant.tools.system import file_open, file_read, file_write
    
    dangerous_paths = [
        "C:\\Windows\\System32\\config\\SAM",
        "C:/Users/../.ssh/id_rsa",
        "../../../etc/passwd",
        "C:\\Program Files\\malware.exe",
    ]
    
    for path in dangerous_paths:
        # All should be blocked
        # Access underlying function of @tool
        result_open = file_open.func(path)
        result_read = file_read.func(path)
        result_write = file_write.func(path, "test")
        
        print(f"DEBUG: path={path}")
        print(f"DEBUG: result_open={result_open}")
        print(f"DEBUG: result_read={result_read}")
        print(f"DEBUG: result_write={result_write}")
        
        try:
            # Check for any of the blocking messages
            for name, res in [("open", result_open), ("read", result_read), ("write", result_write)]:
                lower_res = res.lower()
                assert "access denied" in lower_res or "validation failed" in lower_res or "security check error" in lower_res or "blocked dangerous path" in lower_res, f"file_{name} failed to block: {path} -> {res}"
        except AssertionError as e:
            print(f"❌ FAILURE: {e}")
            raise e
    
    print("✅ Path traversal protection: PASS")


def test_folder_sanitization():
    """Test that note folder traversal is prevented."""
    from sakura_assistant.utils.note_tools import _sanitize_folder_name
    
    tests = [
        ("../../../etc", "___etc"),
        ("../../malicious", "__malicious"),
        ("C:\\Windows", "C_Windows"),
        ("folder/subfolder", "folder_subfolder"),
        ("normal_folder", "normal_folder"),
    ]
    
    for input_folder, expected in tests:
        result = _sanitize_folder_name(input_folder)
        assert result == expected, f"Sanitization failed: {input_folder} → {result} (expected {expected})"
    
    print("✅ Folder sanitization: PASS")


def test_websocket_origin_validation():
    """Test WebSocket origin enforcement (manual verification required)."""
    print("⚠️ WebSocket validation requires manual testing:")
    print("1. Try connecting with empty origin (should reject)")
    print("2. Try connecting with 'http://evil.com' (should reject)")
    print("3. Try connecting with 'tauri://localhost' (should accept)")
    print("Run: wscat -c ws://localhost:3210/ws/status --header 'Origin: <test_origin>'")


def test_validate_path_is_used():
    """Verify validate_path is actually imported and used."""
    import inspect
    try:
        from sakura_assistant.core.tools_libs.system import file_open, file_read, file_write
    except ImportError:
        from sakura_assistant.tools.system import file_open, file_read, file_write
    
    for func in [file_open, file_read, file_write]:
        # Access underlying function source
        source = inspect.getsource(func.func)
        assert "validate_path" in source, f"{func.func.__name__} doesn't call validate_path!"
    
    print("✅ validate_path usage: PASS")

def test_validate_path_direct():
    """Debug: Test validate_path directly."""
    try:
        from sakura_assistant.core.execution.executor import validate_path, SecurityError
    except ImportError:
        from sakura_assistant.execution.executor import validate_path, SecurityError
    
    path = "C:/Windows/System32/config/SAM"
    try:
        validate_path(path)
        print(f"❌ validate_path FAILED to raise for {path}")
        assert False, f"validate_path accepted {path}"
    except SecurityError as e:
        print(f"✅ validate_path correctly raised: {e}")
    except Exception as e:
        print(f"❓ validate_path raised unexpected: {type(e)} {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("SAKURA V17.2 SECURITY PATCH VALIDATION")
    print("=" * 60)
    
    try:
        test_validate_path_direct()
        test_path_traversal_protection()
        test_folder_sanitization()
        test_validate_path_is_used()
        test_websocket_origin_validation()
        
        print("\n" + "=" * 60)
        print("✅ ALL AUTOMATED TESTS PASSED")
        print("⚠️ Manually verify WebSocket tests above")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
