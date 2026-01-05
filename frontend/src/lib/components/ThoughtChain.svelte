<!-- Sakura V10 ThoughtChain - Collapsible ReAct steps (Perplexity-style) -->
<script>
    import { moodColors } from '$lib/stores/chat.js';
    
    export let tools = [];
    
    // Default to COLLAPSED for clean UI - users expand if curious
    let expanded = false;
    
    function toggle() {
        expanded = !expanded;
    }
</script>

{#if tools.length > 0}
    <div class="thought-chain" style="--primary: {$moodColors.primary}">
        <button class="header" on:click={toggle}>
            <span class="icon">{expanded ? '▼' : '▶'}</span>
            <span class="label">
                {tools.length} tool{tools.length > 1 ? 's' : ''} used
            </span>
            <span class="tools-preview">
                {tools.map(t => t.tool).join(', ')}
            </span>
        </button>
        
        {#if expanded}
            <div class="steps">
                {#each tools as tool, i}
                    <div class="step" class:success={tool.status === 'success'} class:error={tool.status === 'error'}>
                        <span class="step-number">{i + 1}</span>
                        <span class="step-tool">{tool.tool}</span>
                        {#if tool.status === 'success'}
                            <span class="step-status">✓</span>
                        {:else if tool.status === 'error'}
                            <span class="step-status">✗</span>
                        {:else}
                            <span class="step-status spinner">⏳</span>
                        {/if}
                    </div>
                {/each}
            </div>
        {/if}
    </div>
{/if}

<style>
    .thought-chain {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        overflow: hidden;
    }
    
    .header {
        display: flex;
        align-items: center;
        gap: 8px;
        width: 100%;
        padding: 8px 12px;
        background: transparent;
        border: none;
        color: rgba(255, 255, 255, 0.6);
        font-size: 12px;
        cursor: pointer;
        text-align: left;
        transition: background 0.2s;
    }
    
    .header:hover {
        background: rgba(255, 255, 255, 0.05);
    }
    
    .icon {
        font-size: 10px;
        opacity: 0.5;
    }
    
    .label {
        font-weight: 500;
    }
    
    .tools-preview {
        flex: 1;
        text-align: right;
        opacity: 0.5;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    
    .steps {
        padding: 8px 12px;
        border-top: 1px solid rgba(255, 255, 255, 0.05);
        display: flex;
        flex-direction: column;
        gap: 6px;
    }
    
    .step {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        color: rgba(255, 255, 255, 0.7);
    }
    
    .step-number {
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.1);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 10px;
    }
    
    .step-tool {
        flex: 1;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .step-status {
        font-size: 14px;
    }
    
    .step.success .step-status {
        color: #44ff88;
    }
    
    .step.error .step-status {
        color: #ff4444;
    }
    
    .spinner {
        animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
</style>
