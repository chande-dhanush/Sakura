<script>
    import { behavioralTraces, refreshBehaviorTrace } from '$lib/stores/chat.js';

    /** @type {Record<string, string>} */
    const labels = {
        memory: 'Memory',
        mood: 'Mood',
        planning: 'Planning',
        proactivity: 'Initiative',
        restraint: 'Restraint',
        routing: 'Routing',
        voice: 'Voice'
    };

    /** @param {string} value */
    function formatTime(value) {
        if (!value) return '';
        try {
            return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return '';
        }
    }
</script>

<section class="inspector" aria-label="Behavioral inspector">
    <div class="inspector-header">
        <div>
            <h2>Behavior</h2>
            <p>Why Sakura moved this way on the last turn.</p>
        </div>
        <button on:click={() => refreshBehaviorTrace()} title="Refresh behavior trace">
            Refresh
        </button>
    </div>

    {#if $behavioralTraces.length === 0}
        <div class="empty">No behavioral influences recorded yet.</div>
    {:else}
        <div class="trace-list">
            {#each $behavioralTraces as trace}
                <article class="trace">
                    <div class="trace-meta">
                        <span class="type">{labels[trace.type] || trace.type}</span>
                        <span>{trace.source}</span>
                        <time>{formatTime(trace.timestamp)}</time>
                    </div>
                    <p>{trace.impact}</p>
                </article>
            {/each}
        </div>
    {/if}
</section>

<style>
    .inspector {
        flex-shrink: 0;
        max-height: 210px;
        overflow: hidden;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        background: rgba(0, 0, 0, 0.18);
    }

    .inspector-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 10px 14px 8px;
    }

    h2 {
        font-size: 13px;
        font-weight: 600;
        color: rgba(255, 255, 255, 0.9);
    }

    p {
        margin-top: 2px;
        font-size: 11px;
        color: rgba(255, 255, 255, 0.48);
    }

    button {
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        background: rgba(255, 255, 255, 0.06);
        color: rgba(255, 255, 255, 0.78);
        padding: 6px 10px;
        font-size: 11px;
        cursor: pointer;
    }

    button:hover {
        background: rgba(255, 255, 255, 0.1);
    }

    .trace-list {
        max-height: 145px;
        overflow-y: auto;
        padding: 0 14px 12px;
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .trace {
        border-left: 2px solid var(--primary, rgba(136, 136, 255, 0.8));
        padding-left: 10px;
    }

    .trace-meta {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 10px;
        color: rgba(255, 255, 255, 0.42);
    }

    .type {
        color: rgba(255, 255, 255, 0.8);
        font-weight: 600;
    }

    .trace p {
        font-size: 12px;
        line-height: 1.35;
        color: rgba(255, 255, 255, 0.74);
    }

    .empty {
        padding: 0 14px 14px;
        font-size: 12px;
        color: rgba(255, 255, 255, 0.45);
    }
</style>
