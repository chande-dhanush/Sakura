import os
import base64
import time
import io
import asyncio
from typing import Union, Optional, List, Dict
from groq import AsyncGroq
from PIL import Image

from ...config import (
    GROQ_API_KEY, 
    VISION_MODEL, 
    VISION_MODEL_FALLBACK, 
    VISION_MAX_TOKENS, 
    VISION_TEMPERATURE
)
from ...utils.token_counter import count_tokens

class VisionClient:
    """
    Dedicated vision model client for Sakura.
    Handles image analysis tasks independently from the main LLM pipeline.
    Invoked only by vision-related tools (read_screen, future image inputs).
    """

    def __init__(self, flight_recorder=None):
        """
        Initialize Groq client using existing GROQ_API_KEY from environment.
        """
        self.api_key = GROQ_API_KEY
        self.client = AsyncGroq(api_key=self.api_key)
        self.flight_recorder = flight_recorder

    async def analyze(
        self,
        image_input: Union[str, Image.Image, bytes],
        prompt: str = "Describe what is on the screen in detail. Focus on text, UI elements, and any actionable information.",
        context: str = None,
        tool_name: str = "read_screen"
    ) -> str:
        """
        Send an image to the vision model and return a text description.
        
        Behavior:
        - Converts image_input to base64 PNG automatically.
        - Calls VISION_MODEL (primary).
        - Retries with VISION_MODEL_FALLBACK once on failure.
        - Logs to FlightRecorder if available.
        """
        if image_input is None:
            return "Vision analysis unavailable. No image provided."

        try:
            full_prompt = prompt
            if context:
                full_prompt += f"\n\nThe user is asking about: {context}"

            base64_image = self._to_base64(image_input)
            messages = self._build_messages(base64_image, full_prompt)

            # Try Primary Model
            return await self._call_api(VISION_MODEL, messages, tool_name, full_prompt)

        except Exception as e:
            print(f"⚠️ Primary vision model ({VISION_MODEL}) failed: {e}")
            try:
                # Retry with Fallback Model
                return await self._call_api(VISION_MODEL_FALLBACK, messages, tool_name, full_prompt)
            except Exception as e2:
                print(f"❌ Fallback vision model ({VISION_MODEL_FALLBACK}) also failed: {e2}")
                return "Vision analysis unavailable. Please describe what you see manually."

    async def _call_api(self, model: str, messages: list, tool_name: str, prompt: str) -> str:
        """Helper to call Groq API and log results."""
        start_time = time.perf_counter()
        
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=VISION_MAX_TOKENS,
            temperature=VISION_TEMPERATURE
        )
        
        elapsed = (time.perf_counter() - start_time) * 1000
        content = response.choices[0].message.content
        
        # Log to FlightRecorder if available
        if self.flight_recorder:
            # Estimate tokens
            input_tokens = count_tokens(prompt, model)
            output_tokens = count_tokens(content, model)
            
            # Note: Groq API returns usage in response, but requirements asked for token_counter
            # We will use counts from token_counter as requested
            self.flight_recorder.log_llm_call(
                stage=f"vision:{tool_name}",
                model=model,
                tokens={"prompt": input_tokens, "completion": output_tokens, "total": input_tokens + output_tokens},
                duration_ms=elapsed,
                success=True
            )
            
        return content

    def _to_base64(self, image_input: Union[str, Image.Image, bytes]) -> str:
        """
        Convert any image input type to base64-encoded PNG string.
        Handles: file path, PIL Image object, raw base64 string (pass-through), bytes.
        """
        if isinstance(image_input, str):
            # Check if it's already a base64 string
            # Heuristic: base64 usually doesn't have spaces and is long.
            # If it starts with a common base64 header or is a pure b64 blob, pass through.
            if image_input.startswith("data:image") or (len(image_input) > 60 and " " not in image_input and not ("\\" in image_input or "/" in image_input)):
                 return image_input.split(",")[-1] # Strip header if present
            
            # Assume it's a file path
            if os.path.exists(image_input):
                with open(image_input, "rb") as image_file:
                    return base64.b64encode(image_file.read()).decode('utf-8')
            else:
                # If it's a string but doesn't exist as a file, and didn't match b64 heuristic, 
                # just try to return it as is or raise.
                return image_input
        
        elif isinstance(image_input, Image.Image):
            buffered = io.BytesIO()
            image_input.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        elif isinstance(image_input, bytes):
            return base64.b64encode(image_input).decode('utf-8')
        
        else:
            raise ValueError(f"Unrecognized image input type: {type(image_input)}")

    def _build_messages(self, base64_image: str, prompt: str) -> list:
        """Build the Groq vision API message format."""
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": prompt
                    },
                    {
                        "type": "image_url", 
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
