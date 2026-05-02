import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.sakura_assistant.utils.tts import get_pipeline, get_audio_output_dir
import soundfile as sf
import numpy as np

async def generate_wake_ack():
    print("Generating 'Yes?' acknowledgment sound...")
    pipe = get_pipeline()
    if not pipe:
        print("Error: Kokoro pipeline not available")
        return

    text = "Yes?"
    voice = 'af_heart'
    
    # Generate audio
    gen = pipe(text, voice=voice, speed=1)
    audio = None
    for (_, _, chunk) in gen:
        if audio is None:
            audio = chunk
        else:
            audio = np.concatenate([audio, chunk])
    
    if audio is None:
        print("Error: No audio generated")
        return

    # Save to backend/data/audio/wake_ack.wav
    output_dir = Path("backend/data/audio")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "wake_ack.wav"
    
    sf.write(str(output_path), audio, 24000)
    print(f"Successfully saved to {output_path}")

if __name__ == "__main__":
    asyncio.run(generate_wake_ack())
