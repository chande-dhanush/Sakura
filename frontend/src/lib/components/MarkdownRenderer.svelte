<!-- Sakura V10 MarkdownRenderer - Renders markdown content -->
<script>
    export let content = '';
    
    // Simple markdown parsing (for production, use marked or similar)
    function parseMarkdown(text) {
        if (!text) return '';
        
        return text
            // Code blocks
            .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
            // Inline code
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            // Bold
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*([^*]+)\*/g, '<em>$1</em>')
            // Links
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
            // Line breaks
            .replace(/\n/g, '<br>');
    }
    
    $: html = parseMarkdown(content);
</script>

<div class="markdown">
    {@html html}
</div>

<style>
    .markdown {
        font-size: 14px;
        line-height: 1.6;
    }
    
    .markdown :global(code) {
        background: rgba(255, 255, 255, 0.1);
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 13px;
    }
    
    .markdown :global(pre) {
        background: rgba(0, 0, 0, 0.3);
        padding: 12px;
        border-radius: 8px;
        overflow-x: auto;
        margin: 8px 0;
    }
    
    .markdown :global(pre code) {
        background: transparent;
        padding: 0;
    }
    
    .markdown :global(strong) {
        font-weight: 600;
        color: rgba(255, 255, 255, 0.95);
    }
    
    .markdown :global(em) {
        font-style: italic;
        color: rgba(255, 255, 255, 0.8);
    }
    
    .markdown :global(a) {
        color: #4488ff;
        text-decoration: none;
    }
    
    .markdown :global(a:hover) {
        text-decoration: underline;
    }
</style>
