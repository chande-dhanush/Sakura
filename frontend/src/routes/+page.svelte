<script>
    import { onMount, tick } from 'svelte';
    import { invoke } from '@tauri-apps/api/core';
    import { listen } from '@tauri-apps/api/event';
    import { getCurrentWindow } from '@tauri-apps/api/window';
    import Omnibox from '$lib/components/Omnibox.svelte';
    import Timeline from '$lib/components/Timeline.svelte';
    import WorldGraphPill from '$lib/components/WorldGraphPill.svelte';
    import VoiceSetup from '$lib/components/VoiceSetup.svelte';
    import Setup from '$lib/components/Setup.svelte'; // V10: New Onboarding
    import { messages, moodColors, refreshState, connectionError, clearChat, startPolling, backendStatus, voiceStatus, checkBackendReady, checkVoiceStatus, loadHistory } from '$lib/stores/chat.js';
    
    let showMenu = false;
    let historyLoading = false;
    let isQuickSearch = false; // Spotlight mode
    let showVoiceSetup = false;
    let showSettings = false; // V10: Settings Modal State
    
    onMount(async () => {
        console.log('[Main] Window mounted, waiting for backend...');
        
        // Wait for backend to be ready (shows loading screen)
        // If SETUP_REQUIRED, this will return true but set status to 'setup_required'
        const ready = await checkBackendReady();
        if (!ready) {
            console.error('[Main] Backend failed to start');
            return;
        }
        
        // Only load data if fully ready (not in setup mode)
        if ($backendStatus === 'ready') {
            try {
                await refreshState();
                console.log('[Main] State refreshed');
                await loadHistory();
                console.log('[Main] History load complete. Messages in store:', $messages.length);
                
                // Check voice status
                await checkVoiceStatus();
                
                // V15.2.1: Sync visibility state on mount (Bubble-Gate)
                try {
                    await fetch('http://localhost:3210/api/ui/visibility', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ visible: true })
                    });
                    console.log('👁️ [Visibility] Synced on mount: true');
                } catch (e) {
                    console.error('[Visibility] Mount sync failed:', e);
                }
                
                // V15: Connect to Proactive WebSocket
                const ws = new WebSocket('ws://localhost:3210/ws/proactive');
                
                ws.onopen = () => {
                    console.log('💌 [Proactive] Connected to backend');
                };
                
                ws.onmessage = async (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.type === 'proactive_message') {
                            console.log('💌 [Proactive] Received:', data.content);
                            
                            // 1. Auto-open window
                            const appWindow = getCurrentWindow();
                            await appWindow.show();
                            await appWindow.setFocus();
                            
                            // 2. Add message to chat
                            messages.update(msgs => [...msgs, {
                                role: 'assistant',
                                content: data.content,
                                timestamp: new Date().toISOString()
                            }]);
                            
                            // 3. Optional: Play chime sound (if file exists)
                            // const audio = new Audio('/sounds/chime.mp3');
                            // audio.play().catch(() => {});
                        }
                    } catch (e) {
                        console.error('[Proactive] Error handling message:', e);
                    }
                };
                
                ws.onerror = (e) => console.error('[Proactive] WebSocket error:', e);
                
                // Listen for Quick Search Trigger (Shift+S global)
                await listen('quick_search_trigger', async () => {
                    console.log('⚡ Quick Search Mode Triggered');
                    isQuickSearch = true;
                    const appWindow = getCurrentWindow();
                    await appWindow.setFocus();
                });

                // Listen for Full Mode Trigger (Shift+F default)
                await listen('full_mode_trigger', async () => {
                    console.log('🔄 Full Mode Triggered');
                    isQuickSearch = false;
                    const appWindow = getCurrentWindow();
                    await appWindow.setFocus();
                });
                
            } catch (e) {
                console.error('[Main] Init error:', e);
            }
        }
    });
    
    async function handleReloadHistory() {
        console.log('[Main] Manual history reload triggered');
        historyLoading = true;
        showMenu = false;
        try {
            await loadHistory();
            console.log('[Main] Reloaded. Messages:', $messages.length);
        } finally {
            historyLoading = false;
        }
    }
    
    function handleClearChat() {
        if (confirm('🗑️ Clear all chat history, memory, and World Graph?\n\nThis cannot be undone.')) {
            clearChat();
            showMenu = false;
        }
    }

    function closeMenu() {
        showMenu = false;
    }
    
    async function openLogsWindow() {
        showMenu = false;
        await invoke('open_logs_window');
    }
    
    // V15.2.1: Report visibility state to backend
    async function reportVisibility(visible) {
        try {
            await fetch('http://localhost:3210/api/ui/visibility', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ visible })
            });
            console.log(`👁️ [Visibility] Reported: ${visible}`);
        } catch (e) {
            console.error('[Visibility] Failed to report:', e);
        }
    }
    
    async function hideWindow() {
        // V15.2.1: Report that UI is now hidden (Bubble-Gate)
        await reportVisibility(false);
        
        await invoke('hide_main_window');
        // Reset quick search mode when hidden
        isQuickSearch = false; 
    }

    function handleKeydown(e) {
        if (e.key === 'Escape') {
            e.preventDefault();
            if (showSettings) {
                showSettings = false; // Close settings on ESC
            } else if (showMenu) {
                showMenu = false;
            } else {
                hideWindow();
            }
            return;
        }
    }
    function handleBlur() {
        if (isQuickSearch) {
            console.log('[Main] Window lost focus in Quick Search mode - hiding');
            hideWindow();
        }
    }
</script>

<svelte:window on:keydown={handleKeydown} on:blur={handleBlur} />

<!-- SETUP MODE - Onboarding for new users -->
{#if $backendStatus === 'setup_required'}
    <Setup />
{:else if $backendStatus === 'starting'}
    <div class="loading-overlay">
        <div class="loading-logo">🌸</div>
        <h2>Starting Sakura...</h2>
        <p class="loading-hint">Initializing AI assistant...</p>
        <div class="loading-spinner"></div>
    </div>
{:else if $backendStatus === 'error'}
    <div class="loading-overlay error">
        <div class="loading-logo">❌</div>
        <h2>Failed to Start</h2>
        <p class="loading-hint">Backend could not be initialized. Please restart the app.</p>
    </div>
{:else}
<!-- Main App Content (only when backend is ready) -->

<!-- Overlay for menu -->
{#if showMenu}
    <div 
        class="overlay" 
        on:click={closeMenu} 
        on:keydown={(e) => e.key === 'Escape' && closeMenu()}
        role="button" 
        tabindex="-1"
    ></div>
{/if}

<main class="app" 
      class:quick-search={isQuickSearch}
      class:has-voice-warning={$voiceStatus.enabled && !$voiceStatus.wakeWordConfigured}
      style="--bg: {$moodColors.bg}; --primary: {$moodColors.primary}; --glow: {$moodColors.glow}"
      role="application">
    
    <!-- VOICE WARNING BANNER - Inside main container -->
    {#if $voiceStatus.enabled && !$voiceStatus.wakeWordConfigured}
        <div class="voice-warning">
            <span>🎤 Voice wake word not configured ({$voiceStatus.templateCount}/3 templates)</span>
            <button on:click={() => showVoiceSetup = true}>Set Up Voice</button>
        </div>
    {/if}
    
    {#if !isQuickSearch}
        <!-- Title Bar - DRAGGABLE -->
        <div class="titlebar" data-tauri-drag-region role="toolbar">
            <span class="title">🌸 Sakura</span>
            <div class="controls">
                <button class="control menu-btn" on:click={() => showMenu = !showMenu} title="Menu">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="5" r="1.5" fill="currentColor"/>
                        <circle cx="12" cy="12" r="1.5" fill="currentColor"/>
                        <circle cx="12" cy="19" r="1.5" fill="currentColor"/>
                    </svg>
                </button>
                <button class="control" on:click={hideWindow} title="Minimize (ESC)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M5 12h14"/>
                    </svg>
                </button>
            </div>
            
            <!-- Dropdown Menu -->
            {#if showMenu}
                <div class="menu">
                    <button on:click={handleReloadHistory} disabled={historyLoading}>
                        <span class="menu-icon">🔄</span> {historyLoading ? 'Loading...' : 'Reload History'}
                    </button>
                    <button on:click={handleClearChat}>
                        <span class="menu-icon">🗑️</span> Clear Chat
                    </button>
                    <button on:click={() => { showMenu = false; showSettings = true; }}>
                        <span class="menu-icon">⚙️</span> Settings
                    </button>
                    <button on:click={openLogsWindow}>
                        <span class="menu-icon">📊</span> Open Logs
                    </button>
                    <div class="menu-divider"></div>
                    <div class="menu-shortcuts">
                        <span><kbd>ESC</kbd> Hide Window</span>
                        <span><kbd>Shift+S</kbd> Quick Search</span>
                    </div>
                </div>
            {/if}
        </div>
        
        <!-- Error Banner -->
        {#if $connectionError}
            <div class="error-banner">
                <span>⚠️ {$connectionError}</span>
                <button on:click={() => connectionError.set(null)} title="Dismiss">×</button>
            </div>
        {/if}
        
        <!-- World Graph Status Pill -->
        <WorldGraphPill />
        
        <!-- Chat Timeline -->
        <div class="timeline-container">
            <Timeline />
        </div>
    {/if}
    
    <!-- Input Area -->
    <div class="input-area">
        <Omnibox isQuickSearch={isQuickSearch} /> <!-- Pass Mode -->
    </div>
</main>

<!-- Voice Setup Modal -->
{#if showVoiceSetup}
    <VoiceSetup on:close={() => showVoiceSetup = false} />
{/if}

<!-- SETTINGS MODAL (Over everything else when active) -->
{#if showSettings}
    <Setup isUpdateMode={true} onClose={() => showSettings = false} />
{/if}

{/if} <!-- End of backendStatus check -->

<style>
    /* ===== GLOBAL RESET ===== */
    :global(*) {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }
    
    :global(html) {
        height: 100%;
        overflow: hidden;
    }
    
    :global(body) {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', sans-serif;
        background: transparent;
        color: #fff;
        overflow: hidden;
        -webkit-font-smoothing: antialiased;
        height: 100%;
        width: 100%;
        position: fixed;
        top: 0;
        left: 0;
    }
    
    /* ... Scrollbar styles omitted for brevity ... */
    :global(::-webkit-scrollbar) { width: 6px; }
    :global(::-webkit-scrollbar-track) { background: transparent; }
    :global(::-webkit-scrollbar-thumb) { background: rgba(255, 255, 255, 0.2); border-radius: 3px; }
    :global(::-webkit-scrollbar-thumb:hover) { background: rgba(255, 255, 255, 0.3); }
    
    /* ===== OVERLAY ===== */
    .overlay {
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: transparent; z-index: 99;
    }
    
    /* ===== DRAG REGION ===== */
    [data-tauri-drag-region] { -webkit-app-region: drag; app-region: drag; cursor: grab; user-select: none; }
    [data-tauri-drag-region] button { -webkit-app-region: no-drag; app-region: no-drag; cursor: pointer; }
    
    /* ===== MAIN APP ===== */
    .app {
        width: 100%;
        height: 100vh;
        max-height: 100vh;
        min-height: 0;
        display: flex;
        flex-direction: column;
        background: var(--bg);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 
            0 20px 60px rgba(0, 0, 0, 0.5),
            0 0 1px rgba(255, 255, 255, 0.1);
        overflow: hidden;
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }
    
    /* QUICK SEARCH MODE */
    .app.quick-search {
        background: rgba(25, 25, 35, 0.95);
        border-radius: 16px;
        border: 1px solid rgba(136, 136, 255, 0.3);
        justify-content: center; /* Center Omnibox vertically */
        box-shadow: 
            0 20px 80px rgba(0, 0, 0, 0.6),
            0 0 0 1px rgba(136, 136, 255, 0.2),
            0 0 40px rgba(136, 136, 255, 0.15);
    }
    
    .app.quick-search .input-area {
        background: transparent;
        border: none;
        padding: 0 24px; /* More padding for cleaner look */
    }
    
    /* ===== TITLE BAR & REST ===== */
    .titlebar {
        display: flex; align-items: center; justify-content: space-between;
        padding: 10px 14px; min-height: 44px;
        background: linear-gradient(180deg, rgba(30, 30, 40, 0.5), rgba(20, 20, 30, 0.3));
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        user-select: none; position: relative; border-radius: 12px 12px 0 0; pointer-events: auto;
    }
    
    .title { font-size: 14px; font-weight: 500; color: rgba(255, 255, 255, 0.9); text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3); pointer-events: none; }
    
    .controls { display: flex; gap: 4px; }
    .control { 
        width: 28px; height: 28px; border-radius: 6px; border: none; background: transparent; 
        color: rgba(255, 255, 255, 0.5); cursor: pointer; display: flex; align-items: center; 
        justify-content: center; transition: all 0.15s; 
    }
    .control:hover { background: rgba(255, 255, 255, 0.1); color: rgba(255, 255, 255, 0.8); }
    
    /* MENU Styles (Simplified for brevity, assume unchanged logic) */
    .menu { position: absolute; top: 100%; right: 10px; min-width: 180px; background: rgba(25, 25, 35, 0.98); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; padding: 6px; z-index: 100; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5); backdrop-filter: blur(20px); }
    .menu button { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px; border: none; border-radius: 6px; background: transparent; color: rgba(255, 255, 255, 0.85); font-size: 13px; cursor: pointer; transition: all 0.15s; text-align: left; }
    .menu button:hover { background: rgba(255, 255, 255, 0.08); }
    .menu-icon { font-size: 14px; }
    .menu-divider { height: 1px; background: rgba(255, 255, 255, 0.08); margin: 6px 0; }
    .menu-shortcuts { padding: 8px 12px; display: flex; flex-direction: column; gap: 4px; }
    .menu-shortcuts span { font-size: 11px; color: rgba(255, 255, 255, 0.4); display: flex; align-items: center; gap: 8px; }
    .menu-shortcuts kbd { background: rgba(255, 255, 255, 0.1); padding: 2px 6px; border-radius: 4px; font-family: inherit; font-size: 10px; }
    
    /* Error Banner */
    .error-banner { display: flex; align-items: center; justify-content: space-between; padding: 8px 14px; background: rgba(255, 68, 68, 0.15); border-bottom: 1px solid rgba(255, 68, 68, 0.3); color: #ff8888; font-size: 12px; }
    .error-banner button { background: transparent; border: none; color: #ff8888; font-size: 16px; cursor: pointer; padding: 0 4px; }
    
    .timeline-container { 
        flex: 1; 
        min-height: 0; /* Critical for flex children to shrink properly */
        overflow: hidden; /* Let Timeline component handle scrolling */
        display: flex; 
        flex-direction: column;
        padding: 0; /* Remove padding here, let Timeline handle it */
    }
    
    .input-area { padding: 12px; border-top: 1px solid rgba(255, 255, 255, 0.06); background: rgba(0, 0, 0, 0.2); }
    
    /* ===== LOADING OVERLAY ===== */
    .loading-overlay {
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(10, 10, 15, 0.98);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 16px;
        z-index: 1000;
        border-radius: 12px;
    }
    
    .loading-overlay.error {
        background: rgba(26, 10, 10, 0.98);
    }
    
    .loading-logo {
        font-size: 64px;
        animation: pulse 2s ease-in-out infinite;
    }
    
    .loading-overlay h2 {
        font-size: 20px;
        font-weight: 500;
        color: rgba(255, 255, 255, 0.9);
    }
    
    .loading-hint {
        font-size: 13px;
        color: rgba(255, 255, 255, 0.5);
    }
    
    .loading-spinner {
        width: 24px;
        height: 24px;
        border: 2px solid rgba(136, 136, 255, 0.3);
        border-top-color: #8888ff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }
    
    @keyframes pulse {
        0%, 100% { transform: scale(1); opacity: 0.8; }
        50% { transform: scale(1.05); opacity: 1; }
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    /* ===== VOICE WARNING BANNER ===== */
    .voice-warning {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 14px;
        background: rgba(255, 170, 0, 0.15);
        border-bottom: 1px solid rgba(255, 170, 0, 0.3);
        color: #ffcc66;
        font-size: 12px;
        flex-shrink: 0; /* Don't compress this banner */
        border-radius: 12px 12px 0 0; /* Match app border radius */
    }
    
    .voice-warning button {
        background: rgba(255, 170, 0, 0.2);
        border: 1px solid rgba(255, 170, 0, 0.4);
        color: #ffcc66;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 11px;
        cursor: pointer;
        transition: all 0.15s;
    }
    
    .voice-warning button:hover {
        background: rgba(255, 170, 0, 0.3);
    }
</style>
