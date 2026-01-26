/**
 * Sakura V18 Audio Service
 * Frontend-based TTS playback using HTML5 Audio API
 * Bypasses pygame.mixer issues in Tauri production builds
 */

import { invoke } from '@tauri-apps/api/core';
import { convertFileSrc } from '@tauri-apps/api/core';
import { remove } from '@tauri-apps/plugin-fs';

let currentAudio: HTMLAudioElement | null = null;

/**
 * Generate and play TTS audio
 * @param text - Text to speak
 */
export async function speak(text: string): Promise<void> {
  // Guard empty text
  if (!text?.trim()) {
    console.warn('[TTS] Empty text, skipping');
    return;
  }
  
  try {
    // Stop any current playback
    stopSpeaking();
    
    // Small delay to let stop complete (race condition fix)
    await new Promise(r => setTimeout(r, 50));
    
    console.log('[TTS] Generating audio for:', text.slice(0, 50) + '...');
    
    // Generate audio via backend
    const audioPath = await invoke<string>('generate_speech', { text });
    console.log('[TTS] Audio generated:', audioPath);
    
    // Convert to asset URL for Tauri webview
    const assetUrl = convertFileSrc(audioPath);
    console.log('[TTS] Asset URL:', assetUrl);
    
    // Play with HTML5 Audio API
    currentAudio = new Audio(assetUrl);
    
    currentAudio.onended = async () => {
      console.log('[TTS] Playback complete, cleaning up...');
      try {
        await remove(audioPath);
        console.log('[TTS] ✓ Audio file deleted');
      } catch (e) {
        console.warn('[TTS] Cleanup failed:', e);
      }
      currentAudio = null;
    };
    
    currentAudio.onerror = (e) => {
      console.error('[TTS] Playback error:', e);
      currentAudio = null;
    };
    
    await currentAudio.play();
    console.log('[TTS] ✓ Playing audio');
    
  } catch (error) {
    console.error('[TTS] Failed:', error);
    // Let caller handle UI feedback
    throw error;
  }
}

/**
 * Stop current TTS playback
 */
export function stopSpeaking(): void {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
    console.log('[TTS] Stopped');
  }
}

/**
 * Check if TTS is currently playing
 */
export function isSpeaking(): boolean {
  return currentAudio !== null && !currentAudio.paused;
}
