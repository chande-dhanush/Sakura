"""
Test Suite: Path Sandboxing
============================
Tests the _validate_path security function.
"""
import pytest
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sakura_assistant.core.tools_libs.common import _validate_path
    from sakura_assistant.core.tools import file_read, file_write
except ImportError:
    # Fallback for running from different directories
    from core.tools_libs.common import _validate_path
    from core.tools import file_read, file_write


class TestPathSandboxing:
    """Test path validation security."""
    
    def test_allows_project_root(self):
        """Valid project paths should pass."""
        # Get project root from config
        try:
            from sakura_assistant.config import get_project_root
        except ImportError:
            from config import get_project_root
        
        project_root = get_project_root()
        test_path = os.path.join(project_root, "test_file.txt")
        
        # Should not raise
        result = _validate_path(test_path)
        assert result is not None
    
    def test_allows_documents(self):
        """Paths in Documents folder should pass."""
        docs_path = Path.home() / "Documents" / "test.txt"
        result = _validate_path(str(docs_path))
        assert docs_path.name in result
    
    def test_allows_desktop(self):
        """Paths in Desktop folder should pass."""
        desktop_path = Path.home() / "Desktop" / "test.txt"
        result = _validate_path(str(desktop_path))
        assert "Desktop" in result
    
    def test_allows_downloads(self):
        """Paths in Downloads folder should pass."""
        downloads_path = Path.home() / "Downloads" / "test.txt"
        result = _validate_path(str(downloads_path))
        assert "Downloads" in result
    
    def test_blocks_system32(self):
        """System paths should be blocked."""
        with pytest.raises(ValueError, match="Outside Sandbox"):
            _validate_path("C:/Windows/System32/drivers/etc/hosts")
    
    def test_blocks_program_files(self):
        """Program Files should be blocked."""
        with pytest.raises(ValueError, match="Outside Sandbox"):
            _validate_path("C:/Program Files/test.exe")
    
    def test_blocks_temp_folder(self):
        """Temp folder should be blocked."""
        with pytest.raises(ValueError, match="Outside Sandbox"):
            _validate_path("C:/Users/Public/test.txt")
    
    def test_blocks_parent_traversal(self):
        """Parent directory traversal should be blocked."""
        with pytest.raises(ValueError, match="traversal"):
            _validate_path("../../../etc/passwd")
    
    def test_blocks_hidden_traversal(self):
        """Hidden directory traversal in middle of path."""
        with pytest.raises(ValueError, match="traversal"):
            _validate_path("D:/Projects/test/../../../Windows/System32/config")
    
    def test_blocks_root_access(self):
        """Root level access outside sandbox."""
        with pytest.raises(ValueError, match="Outside Sandbox"):
            _validate_path("C:/secret.txt")
    
    def test_blocks_appdata(self):
        """AppData folder should be blocked (unless explicitly allowed)."""
        appdata = os.getenv("APPDATA", "C:/Users/test/AppData/Roaming")
        with pytest.raises(ValueError, match="Outside Sandbox"):
            _validate_path(os.path.join(appdata, "test.txt"))


class TestFileToolsSandbox:
    """Test that file tools use sandboxing."""
    
    def test_file_write_blocks_config(self):
        """file_write should block writes to config.py."""
        # Use a path that would normally be in project but is protected
        try:
            from sakura_assistant.config import get_project_root
        except ImportError:
            from config import get_project_root
        
        config_path = os.path.join(get_project_root(), "sakura_assistant", "config.py")
        result = file_write.invoke({"path": config_path, "content": "malicious"})
        assert "Protected" in result or "Security" in result
    
    def test_file_read_blocks_system(self):
        """file_read should block system file access."""
        result = file_read.invoke({"path": "C:/Windows/System32/config/SAM"})
        assert "Security" in result or "Error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
