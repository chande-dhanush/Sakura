<script>
    import { onMount } from 'svelte';
    import { invoke } from '@tauri-apps/api/core';
    import { getCurrentWindow } from '@tauri-apps/api/window';
    
    let menuOpen = false;
    
    onMount(() => {
        console.log('[Bubble] Mounted');
    });
    
    async function handleClick() {
        console.log('[Bubble] Click - opening main window');
        menuOpen = false;
        try {
            await invoke('show_main_window');
        } catch (e) {
            console.error('[Bubble] Failed to show main:', e);
        }
    }
    
    function handleRightClick(e) {
        console.log('[Bubble] Right-click detected');
        e.preventDefault();
        e.stopPropagation();
        menuOpen = !menuOpen;
        console.log('[Bubble] Menu open:', menuOpen);
    }
    
    async function handleQuit() {
        console.log('[Bubble] Hard Quit requested');
        menuOpen = false;
        try {
            await invoke('force_quit');
        } catch (e) {
            console.error('[Bubble] Quit failed:', e);
        }
    }
    
    function handleGlobalClick(e) {
        if (menuOpen && !e.target.closest('.bubble-menu')) {
            menuOpen = false;
        }
    }
</script>

<svelte:window on:click={handleGlobalClick} />

<div 
    class="bubble-container" 
    on:contextmenu|preventDefault|stopPropagation={handleRightClick}
    role="application"
>
    <button 
        class="sakura-bubble" 
        on:click={handleClick}
        on:contextmenu|preventDefault|stopPropagation={handleRightClick}
        title="Left-click: Open | Right-click: Menu"
    >
        <span class="bubble-icon">🌸</span>
    </button>
    
    {#if menuOpen}
        <div class="bubble-menu">
            <button on:click={handleClick}>📖 Open Sakura</button>
            <hr />
            <button class="quit-btn" on:click={handleQuit}>❌ Quit</button>
        </div>
    {/if}
</div>

<style>
    :global(html), :global(body) {
        margin: 0;
        padding: 0;
        background: transparent;
        overflow: hidden; /* Prevent scrollbars */
        width: 220px;
        height: 220px;
    }
    
    .bubble-container {
        width: 220px;
        height: 220px;
        position: relative;
        /* pointer-events: none; If we want click-through on empty space (requires Tauri setup, skipping for now) */
    }
    
    .sakura-bubble {
        width: 64px;
        height: 64px;
        position: absolute;
        bottom: 0;
        right: 0;
        /* pointer-events: auto; */
        
        background: linear-gradient(135deg, rgba(30, 30, 45, 0.95) 0%, rgba(20, 20, 30, 0.98) 100%);
        border: 1.5px solid rgba(136, 136, 255, 0.4);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        box-shadow: 
            0 4px 24px rgba(0, 0, 0, 0.6),
            0 0 40px rgba(136, 136, 255, 0.2),
            inset 0 1px 0 rgba(255, 255, 255, 0.1);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        animation: bubble-pulse 3s ease-in-out infinite;
    }
    
    /* ... (rest of .sakura-bubble styles) ... */
    
    .bubble-icon {
        font-size: 28px;
        filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3));
        pointer-events: none;
    }
    
    .sakura-bubble:hover {
        transform: scale(1.1);
        border-color: rgba(136, 136, 255, 0.7);
        box-shadow: 
            0 6px 30px rgba(0, 0, 0, 0.7),
            0 0 50px rgba(136, 136, 255, 0.35);
    }
    
    .sakura-bubble:active {
        transform: scale(1.02);
    }
    
    @keyframes bubble-pulse {
        0%, 100% { 
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6), 0 0 40px rgba(136, 136, 255, 0.2); 
        }
        50% { 
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6), 0 0 50px rgba(136, 136, 255, 0.35); 
        }
    }
    
    /* Context Menu - positioned relative to bottom-right bubble */
    .bubble-menu {
        position: absolute;
        bottom: 75px;
        right: 10px;
        min-width: 140px;
        background: rgba(25, 25, 35, 0.98);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 12px;
        padding: 6px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(16px);
        z-index: 9999;
        /* pointer-events: auto; */
    }

    .bubble-menu button {
        display: block;
        width: 100%;
        padding: 10px 14px;
        background: transparent;
        border: none;
        border-radius: 8px;
        color: rgba(255, 255, 255, 0.85);
        font-size: 13px;
        text-align: left;
        cursor: pointer;
        transition: all 0.15s;
    }

    .bubble-menu button:hover {
        background: rgba(255, 255, 255, 0.1);
    }

    .bubble-menu hr {
        border: none;
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        margin: 4px 0;
    }

    .bubble-menu .quit-btn {
        color: #ff6666;
    }

    .bubble-menu .quit-btn:hover {
        background: rgba(255, 68, 68, 0.15);
    }
</style>
