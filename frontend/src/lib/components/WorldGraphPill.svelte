<!-- Sakura V10 WorldGraphPill - Floating mood/entity indicator -->
<script>
    import { mood, focusEntity, moodColors } from '$lib/stores/chat.js';
    
    const moodEmoji = {
        frustrated: '😤',
        urgent: '⚡',
        playful: '😊',
        curious: '🤔',
        neutral: '😌'
    };
</script>

{#if $mood !== 'neutral' || $focusEntity}
    <div class="pill" style="--primary: {$moodColors.primary}; --glow: {$moodColors.glow}">
        {#if $mood !== 'neutral'}
            <span class="mood">{moodEmoji[$mood] || '😌'}</span>
        {/if}
        {#if $focusEntity}
            <span class="entity">{$focusEntity}</span>
        {/if}
    </div>
{/if}

<style>
    .pill {
        position: fixed;
        top: 12px;
        right: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        background: rgba(10, 10, 10, 0.9);
        border: 1px solid var(--primary);
        border-radius: 20px;
        box-shadow: 0 0 15px var(--glow);
        font-size: 12px;
        color: var(--primary);
        z-index: 100;
    }
    
    .mood {
        font-size: 16px;
    }
    
    .entity {
        max-width: 100px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
</style>
