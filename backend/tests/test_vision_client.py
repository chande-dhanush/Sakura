import pytest
import base64
import os
import io
from unittest.mock import MagicMock, patch, AsyncMock
from PIL import Image
from sakura_assistant.core.models.vision_client import VisionClient

pytestmark = pytest.mark.asyncio

class TestVisionClient:

    @pytest.fixture
    def mock_recorder(self):
        return MagicMock()

    @pytest.fixture
    def client(self, mock_recorder):
        return VisionClient(flight_recorder=mock_recorder)

    # --- Unit: _to_base64 ---

    def test_to_base64_path(self, client, tmp_path):
        """1. File path input -> returns valid base64 string."""
        img_path = tmp_path / "test.png"
        img = Image.new('RGB', (10, 10), color='red')
        img.save(img_path)
        
        b64 = client._to_base64(str(img_path))
        assert isinstance(b64, str)
        assert len(b64) > 0
        # Verify it can be decoded back
        assert base64.b64decode(b64)

    def test_to_base64_passthrough(self, client):
        """2. Raw base64 string input -> returns same string."""
        sample_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        # Heuristic in code is > 60 chars
        assert client._to_base64(sample_b64) == sample_b64

    def test_to_base64_unrecognized(self, client):
        """3. Unrecognized type -> raises ValueError."""
        with pytest.raises(ValueError, match="Unrecognized image input type"):
            client._to_base64(123)

    # --- Unit: _build_messages ---

    def test_build_messages(self, client):
        """4 & 5. Verify message format."""
        b64 = "base64data"
        prompt = "test prompt"
        messages = client._build_messages(b64, prompt)
        
        content = messages[0]["content"]
        assert content[0]["type"] == "text"
        assert content[0]["text"] == prompt
        assert content[1]["type"] == "image_url"
        assert "data:image/png;base64,base64data" in content[1]["image_url"]["url"]

    # --- Unit: analyze() ---

    @pytest.mark.asyncio
    async def test_analyze_success(self, client):
        """6. Mock Groq API success -> returns text."""
        client.client.chat.completions.create = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="Look at this screen"))]
        ))
        
        img = Image.new('RGB', (1, 1))
        result = await client.analyze(img, prompt="test")
        
        assert result == "Look at this screen"
        client.flight_recorder.log_llm_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_fallback(self, client):
        """7. Primary fails, Fallback succeeds."""
        # First call fails, second succeeds
        client.client.chat.completions.create = AsyncMock(side_effect=[
            Exception("API Error"),
            MagicMock(choices=[MagicMock(message=MagicMock(content="Fallback result"))])
        ])
        
        img = Image.new('RGB', (1, 1))
        result = await client.analyze(img, prompt="test")
        
        assert result == "Fallback result"
        # Flight recorder should be called for the successful fallback
        assert client.flight_recorder.log_llm_call.call_count == 1

    @pytest.mark.asyncio
    async def test_analyze_total_failure(self, client):
        """8. Both models fail -> returns safe error string."""
        client.client.chat.completions.create = AsyncMock(side_effect=Exception("Death"))
        
        img = Image.new('RGB', (1, 1))
        result = await client.analyze(img, prompt="test")
        
        assert "Vision analysis unavailable" in result

    @pytest.mark.asyncio
    async def test_analyze_none_input(self, client):
        """9. None input -> returns safe error string."""
        result = await client.analyze(None)
        assert "No image provided" in result
