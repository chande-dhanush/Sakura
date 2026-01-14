"""
Test Suite: ChatViewModel (Legacy PyQt5 UI)
============================================
These tests require PyQt5 which is only used for the desktop UI.
Skip this entire module when running on web-only backends.
"""
import unittest
import sys
import os

# Skip entire module if PyQt5 is not available
try:
    from PyQt5.QtCore import QObject
    from PyQt5 import QtWidgets
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False


@unittest.skipUnless(PYQT5_AVAILABLE, "PyQt5 not installed - skipping desktop UI tests")
class TestChatViewModel(unittest.TestCase):
    """Tests for the PyQt5-based ChatViewModel (legacy desktop UI)."""
    
    @classmethod
    def setUpClass(cls):
        """Set up PyQt5 application and mocks."""
        if not PYQT5_AVAILABLE:
            return
        
        from unittest.mock import MagicMock
        from PyQt5 import QtWidgets
        
        # Create QApplication if needed
        if not QtWidgets.QApplication.instance():
            cls.app = QtWidgets.QApplication(sys.argv)
        
        # Add project root to path
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
        
        # Mock heavy modules
        sys.modules['sakura_assistant.utils.storage'] = MagicMock()
        sys.modules['sakura_assistant.ui.workers'] = MagicMock()
        sys.modules['sakura_assistant.core.llm'] = MagicMock()
        sys.modules['sakura_assistant.utils.file_ingest'] = MagicMock()
        sys.modules['sakura_assistant.utils.file_registry'] = MagicMock()
        sys.modules['sakura_assistant.core.tools'] = MagicMock()
        
        from sakura_assistant.ui.viewmodel import ChatViewModel
        cls.ChatViewModel = ChatViewModel
    
    def test_placeholder(self):
        """Placeholder test - real tests require full PyQt5 setup."""
        self.assertTrue(PYQT5_AVAILABLE)


if __name__ == '__main__':
    unittest.main()
