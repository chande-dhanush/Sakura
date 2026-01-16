/**
 * Sakura V10 Window Manager (Multi-Window)
 * Simplified - no more morphing, just utilities
 */

import { getCurrentWindow } from '@tauri-apps/api/window';
import { invoke } from '@tauri-apps/api/core';

/**
 * Toggle the main window visibility
 */
export async function toggleMainWindow() {
    await invoke('toggle_main_window');
}

/**
 * Show the main window
 */
export async function showMainWindow() {
    await invoke('show_main_window');
}

/**
 * Hide the main window
 */
export async function hideMainWindow() {
    await invoke('hide_main_window');
}

/**
 * Quit the application
 */
export async function quitApp() {
    try {
        // Shutdown backend first
        await fetch('http://localhost:3210/shutdown', {
            method: 'POST',
            signal: AbortSignal.timeout(1000)
        });
    } catch {
        // Backend might be down
    }

    // Close the current window
    const win = getCurrentWindow();
    await win.close();
}
