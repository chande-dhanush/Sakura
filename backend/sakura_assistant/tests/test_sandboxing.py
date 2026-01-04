import pytest
import os
import sys

# Add project root to path so we can import 'core'
sys.path.append(os.getcwd())
try:
    from core.tools import file_read, file_write, _validate_path
except ImportError:
    # If test is run from tests/ subdirectory
    sys.path.append(os.path.dirname(os.getcwd()))
    from core.tools import file_read, file_write, _validate_path

def test_sandbox_allows_project_root():
    # Should pass (assuming we run from a valid place)
    # We'll use a dummy path within CWD
    cwd = os.getcwd()
    try:
        _validate_path(os.path.join(cwd, "test_file.txt"))
    except ValueError:
        pytest.fail("Sandbox blocked valid project file.")

def test_sandbox_blocks_system():
    # Attempt to access a likely system path
    with pytest.raises(ValueError, match="Outside Sandbox"):
        _validate_path("C:/Windows/System32/drivers/etc/hosts")

def test_sandbox_blocks_traversal():
    # Attempt ..
    with pytest.raises(ValueError, match="traversal"):
        _validate_path("d:/Personal Projects/sakura_modifs/sakura_assistant/../secret.txt")

def test_file_write_block_config():
    # Should block writing to config.py
    res = file_write(os.path.join(os.getcwd(), "config.py"), "malicious_content")
    assert "Security Violation" in res
