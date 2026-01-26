<!-- Sakura V10 TimelineItem - Single chat turn -->
<script>
    import { moodColors, deleteMessage } from '$lib/stores/chat.js';
    import ThoughtChain from './ThoughtChain.svelte';
    import MarkdownRenderer from './MarkdownRenderer.svelte';
    import { speak } from '$lib/audioService';
    
    export let message;
    
    let showActions = false;
    
    $: isUser = message.role === 'user';
    $: hasTools = message.tools && message.tools.length > 0;
    $: isThinking = message.content === '...';
    
    function handleDelete() {
        if (message.id) {
            deleteMessage(message.id);
        }
    }

    async function handleSpeak() {
        if (!message.content) return;
        try {
            await speak(message.content);
        } catch (e) {
            console.error("Speak failed", e);
            // TODO: Show toast notification to user
        }
    }
</script>

<div 
    class="item" 
    class:user={isUser}
    on:mouseenter={() => showActions = true}
    on:mouseleave={() => showActions = false}
>
    <div class="avatar" class:user-avatar={isUser}>
        {isUser ? '👤' : '🌸'}
    </div>
    
    <div class="content">
        {#if hasTools && !isUser}
            <ThoughtChain tools={message.tools} mode={message.mode} />
        {/if}
        
        <div class="bubble" class:thinking={isThinking} style="--primary: {$moodColors.primary}">
            {#if isThinking}
                <span class="thinking-dots">
                    <span>●</span><span>●</span><span>●</span>
                </span>
            {:else}
                <MarkdownRenderer content={message.content} />
            {/if}
            
            <!-- Message Actions -->
            {#if showActions && !isThinking}
                <div class="actions">
                    {#if !isUser}
                        <button on:click={handleSpeak} title="Read Aloud">🔊</button>
                    {/if}
                    <button on:click={handleDelete} title="Delete">🗑️</button>
                </div>
            {/if}
        </div>
        
        {#if message.mode && !isUser}
            <span class="mode-badge">{message.mode}</span>
        {/if}
    </div>
</div>

<style>
    .item {
        display: flex;
        gap: 12px;
        max-width: 85%;
        animation: fadeIn 0.3s ease;
        position: relative;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .item.user {
        flex-direction: row-reverse;
        align-self: flex-end;
    }
    
    .avatar {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: linear-gradient(135deg, rgba(136, 136, 255, 0.2), rgba(136, 136, 255, 0.05));
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        flex-shrink: 0;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .user-avatar {
        background: linear-gradient(135deg, rgba(68, 255, 136, 0.2), rgba(68, 255, 136, 0.05));
    }
    
    .content {
        display: flex;
        flex-direction: column;
        gap: 8px;
        min-width: 0;
    }
    
    .bubble {
        position: relative;
        padding: 14px 18px;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.08);
        color: rgba(255, 255, 255, 0.9);
        line-height: 1.55;
        font-size: 14px;
    }
    
    .user .bubble {
        background: linear-gradient(135deg, rgba(68, 136, 255, 0.15), rgba(68, 136, 255, 0.08));
        border-color: rgba(68, 136, 255, 0.2);
    }
    
    .bubble.thinking {
        padding: 12px 20px;
    }
    
    .thinking-dots {
        display: flex;
        gap: 4px;
    }
    
    .thinking-dots span {
        opacity: 0.4;
        animation: blink 1.4s infinite;
        font-size: 12px;
    }
    
    .thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
    .thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
    
    @keyframes blink {
        0%, 80%, 100% { opacity: 0.4; }
        40% { opacity: 1; }
    }
    
    .actions {
        position: absolute;
        top: 4px;
        right: 4px;
        display: flex;
        gap: 4px;
    }
    
    .actions button {
        background: rgba(0, 0, 0, 0.5);
        border: none;
        border-radius: 4px;
        padding: 4px 6px;
        font-size: 12px;
        cursor: pointer;
        opacity: 0.7;
        transition: opacity 0.2s;
    }
    
    .actions button:hover {
        opacity: 1;
    }
    
    .mode-badge {
        font-size: 10px;
        color: rgba(255, 255, 255, 0.35);
        text-transform: uppercase;
        letter-spacing: 1px;
        padding-left: 4px;
    }
</style>
