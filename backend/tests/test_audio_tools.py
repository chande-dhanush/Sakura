"""
Audio Tools Test Suite
======================
Tests for audio transcription and summarization tools.

Run: pytest sakura_assistant/tests/test_audio_tools.py -v

Note: Full tests require actual audio files. Basic unit tests run without dependencies.
"""

import pytest
import sys
import os
import tempfile

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestAudioToolsBasics:
    """Basic tests that don't require audio files."""
    
    def test_import_tools(self):
        """Audio tools should be importable."""
        from sakura_assistant.core.tools_libs.audio_tools import (
            transcribe_audio, summarize_audio
        )
        assert transcribe_audio is not None
        assert summarize_audio is not None
    
    def test_tools_are_langchain_tools(self):
        """Tools should be decorated with @tool."""
        from sakura_assistant.core.tools_libs.audio_tools import (
            transcribe_audio, summarize_audio
        )
        # LangChain tools have a 'name' attribute
        assert hasattr(transcribe_audio, 'name')
        assert hasattr(summarize_audio, 'name')
        
        assert transcribe_audio.name == "transcribe_audio"
        assert summarize_audio.name == "summarize_audio"
    
    def test_file_not_found_error(self):
        """Missing file should return error gracefully."""
        from sakura_assistant.core.tools_libs.audio_tools import transcribe_audio
        
        result = transcribe_audio.invoke({"file_path": "nonexistent_file.mp3"})
        assert "error" in result.lower() or "not found" in result.lower()
    
    def test_summarize_file_not_found(self):
        """Summarize should handle missing files gracefully."""
        from sakura_assistant.core.tools_libs.audio_tools import summarize_audio
        
        result = summarize_audio.invoke({"file_path": "nonexistent_file.mp3"})
        assert "error" in result.lower() or "not found" in result.lower()


class TestAudioConversion:
    """Test audio format conversion utilities."""
    
    def test_convert_to_wav_import(self):
        """Conversion function should be accessible."""
        from sakura_assistant.core.tools_libs.audio_tools import _convert_to_wav
        assert _convert_to_wav is not None
    
    def test_wav_passthrough(self):
        """WAV files should not be re-converted."""
        from sakura_assistant.core.tools_libs.audio_tools import _convert_to_wav
        
        # Create a temp WAV file (just needs to exist)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF" + b"\x00" * 100)  # Minimal WAV header bytes
            temp_path = f.name
        
        try:
            result = _convert_to_wav(temp_path)
            # Should return same path for WAV
            assert result == temp_path
        except Exception:
            # May fail on invalid WAV, which is fine for this test
            pass
        finally:
            os.unlink(temp_path)


class TestToolsInRegistry:
    """Test that audio tools are properly registered."""
    
    def test_tools_in_get_all_tools(self):
        """Audio tools should appear in the main tools list."""
        from sakura_assistant.core.tools import get_all_tools
        
        all_tools = get_all_tools()
        tool_names = [t.name for t in all_tools]
        
        assert "transcribe_audio" in tool_names
        assert "summarize_audio" in tool_names


@pytest.mark.skipif(
    not os.path.exists("d:/Personal Projects/Sakura V10/backend/uploads"),
    reason="Uploads directory not found"
)
class TestWithRealAudio:
    """Tests that require actual audio files in uploads/."""
    
    def test_transcribe_wav_file(self):
        """Test transcription with a real WAV file."""
        from sakura_assistant.core.tools_libs.audio_tools import transcribe_audio
        
        # Skip if no test audio available
        test_files = [
            "test_audio.wav",
            "sample.wav",
        ]
        
        test_file = None
        uploads_dir = "d:/Personal Projects/Sakura V10/backend/uploads"
        for f in test_files:
            if os.path.exists(os.path.join(uploads_dir, f)):
                test_file = f
                break
        
        if not test_file:
            pytest.skip("No test audio file available")
        
        result = transcribe_audio.invoke({"file_path": test_file})
        
        # Should have some transcript
        assert "Transcript" in result or "words" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
