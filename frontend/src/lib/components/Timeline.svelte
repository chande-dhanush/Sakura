<!-- Sakura V10 Timeline Component - Chat history container -->
<script>
    import { onMount, afterUpdate, tick } from 'svelte';
    import { messages, moodColors, sendMessage, isStreaming } from '$lib/stores/chat.js';
    import TimelineItem from './TimelineItem.svelte';
    
    let container;
    let shouldAutoScroll = true;
    let lastMessageCount = 0;
    
    // Track if user scrolled up - if so, don't auto-scroll
    function handleScroll() {
        if (!container) return;
        const { scrollTop, scrollHeight, clientHeight } = container;
        // If within 150px of bottom, enable auto-scroll
        shouldAutoScroll = scrollHeight - scrollTop - clientHeight < 150;
        showScrollButton = !shouldAutoScroll;
    }
    
    // Auto-scroll on new messages
    $: if ($messages && container && shouldAutoScroll) {
        // Use tick to wait for DOM update
        (async () => {
            await tick();
            container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
        })();
    }

    let showScrollButton = false;

    function scrollToBottom() {
        if (container) {
            shouldAutoScroll = true;
            container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
        }
    }

    onMount(() => {
        // Initial scroll
        scrollToBottom();
        
        // Scroll on window focus
        const onFocus = () => scrollToBottom();
        window.addEventListener('focus', onFocus);
        
        return () => window.removeEventListener('focus', onFocus);
    });
    
    // Suggestion chips - clicking sends the message
    const suggestions = [
        { text: "What's the weather today?", icon: "🌤️" },
        { text: "Check my emails", icon: "📧" },
        { text: "Play some music", icon: "🎵" },
        { text: "What can you do?", icon: "✨" }
    ];
    
    function handleSuggestion(text) {
        sendMessage(text);
    }
</script>

<div class="timeline" bind:this={container} on:scroll={handleScroll}>
    {#if $messages.length === 0}
        <div class="welcome">
            <div class="logo">🌸</div>
            <h2>Sakura</h2>
            <p>Your AI assistant. Ask me anything — I can search the web, play music, check your email, and much more.</p>
            <div class="suggestions">
                {#each suggestions as { text, icon }}
                    <button class="chip" on:click={() => handleSuggestion(text)}>
                        <span class="chip-icon">{icon}</span>
                        <span class="chip-text">{text}</span>
                    </button>
                {/each}
            </div>
        </div>
    {:else}
        {#each $messages as message, i (i)}
            <TimelineItem {message} />
        {/each}
    {/if}

    {#if showScrollButton}
        <button class="scroll-btn" on:click={scrollToBottom} title="Scroll to Bottom">
            ↓
        </button>
    {/if}
</div>

<style>
    .timeline {
        flex: 1;
        overflow-y: auto;
        padding: 20px;
        display: flex;
        flex-direction: column;
        gap: 16px;
    }
    
    /* Welcome Screen */
    .welcome {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        gap: 12px;
        padding: 40px;
    }
    
    .logo {
        font-size: 64px;
        opacity: 0.8;
        filter: drop-shadow(0 0 20px rgba(136, 136, 255, 0.3));
    }
    
    .welcome h2 {
        font-size: 24px;
        font-weight: 600;
        color: rgba(255, 255, 255, 0.9);
        margin: 0;
    }
    
    .welcome p {
        font-size: 14px;
        color: rgba(255, 255, 255, 0.5);
        max-width: 300px;
        line-height: 1.5;
    }
    
    .suggestions {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 8px;
        margin-top: 16px;
    }
    
    .chip {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 10px 16px;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 24px;
        font-size: 13px;
        color: rgba(255, 255, 255, 0.7);
        cursor: pointer;
        transition: all 0.2s ease;
    }
    
    .chip:hover {
        background: rgba(136, 136, 255, 0.12);
        border-color: rgba(136, 136, 255, 0.3);
        color: #fff;
        transform: translateY(-1px);
    }
    
    .chip:active {
        transform: translateY(0);
    }
    
    .chip-icon {
        font-size: 14px;
    }
    
    .chip-text {
        font-weight: 500;
    }
    
    /* Custom scrollbar */
    .timeline::-webkit-scrollbar {
        width: 6px;
    }
    
    .timeline::-webkit-scrollbar-track {
        background: transparent;
    }
    
    .timeline::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 3px;
    }
    
    .timeline::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.2);
    }

    .scroll-btn {
        position: fixed;
        bottom: 100px; /* Above Omnibox */
        right: 24px;
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: rgba(30, 30, 45, 0.9);
        border: 1px solid rgba(255, 255, 255, 0.2);
        color: rgba(255, 255, 255, 0.9);
        font-size: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        backdrop-filter: blur(8px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
        transition: all 0.2s;
        z-index: 50;
        animation: fadeIn 0.2s ease;
    }
    
    .scroll-btn:hover {
        background: rgba(136, 136, 255, 0.3);
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.5);
    }
</style>
