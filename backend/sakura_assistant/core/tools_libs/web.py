import os
from langchain_core.tools import tool
from typing import Optional
from .common import log_api_call

# --- Imports ---
try:
    import pywhatkit
except ImportError:
    pywhatkit = None

# --- Web Tools ---

@tool
def play_youtube(topic: str) -> str:
    """Play a video or song on YouTube."""
    if not pywhatkit:
        return "❌ YouTube playback not available."
    try:
        pywhatkit.playonyt(topic)
        return f"📺 Playing '{topic}' on YouTube."
    except Exception as e:
        return f"❌ YouTube error: {e}"

@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "❌ TAVILY_API_KEY missing."
    try:
        from tavily import TavilyClient
        print(f"Called Search: {query}")
        
        max_results = min(max_results, 10)
        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results)
        
        results = response.get("results", [])
        if not results:
            return "❌ No search results found."
        
        out = []
        for r in results:
            title = r.get("title", "No title")
            snippet = r.get("content", "")[:200]
            url = r.get("url", "")
            out.append(f"🔍 **{title}**\n   {snippet}...\n   🔗 {url}")
        
        return "\n\n".join(out)
    except Exception as e:
        return f"❌ Search failed: {e}"

@tool
def search_wikipedia(query: str) -> str:
    """Search Wikipedia for a summary."""
    print("Called Wikipedia search")
    try:
        import wikipedia
        wikipedia.set_lang("en")
        search_results = wikipedia.search(query, results=1)
        if not search_results:
            return "❌ No Wikipedia page found."
        
        page_title = search_results[0]
        summary = wikipedia.summary(page_title, sentences=3)
        return f"📚 Wikipedia ({page_title}):\n{summary}\n(Source: {wikipedia.page(page_title).url})"
    except ImportError:
        return "❌ 'wikipedia' library not installed."
    except Exception as e:
        return f"❌ Wikipedia error: {e}"

@tool
def search_arxiv(query: str) -> str:
    """Search Arxiv for scientific papers."""
    print("Called Arxiv search")
    try:
        import arxiv
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=3,
            sort_by=arxiv.SortCriterion.Relevance
        )
        
        results = []
        for r in client.results(search):
            results.append(f"📄 {r.title}\n   - Authors: {', '.join(a.name for a in r.authors)}\n   - Summary: {r.summary[:200]}...\n   - PDF: {r.pdf_url}")
            
        if not results:
            return "❌ No papers found."
            
        return "\n\n".join(results)
    except ImportError:
        return "❌ 'arxiv' library not installed."
    except Exception as e:
        return f"❌ Arxiv error: {e}"

@tool
def get_news(topic: str = "technology") -> str:
    """Get latest news headlines."""
    import requests
    try:
        url = f"https://news.google.com/rss/search?q={topic}&hl=en-IN&gl=IN&ceid=IN:en"
        response = requests.get(url, timeout=5)
        
        if response.status_code != 200:
            return f"❌ News fetch failed"
        
        import re
        titles = re.findall(r"<title>(.*?)</title>", response.text)
        headlines = titles[1:6]  # Top 5 headlines
        
        if not headlines:
            return f"❌ No news found for '{topic}'"
        
        result = [f"📰 **Top {topic} news:**"]
        for i, title in enumerate(headlines, 1):
            title = title.replace("&amp;", "&").replace("&quot;", '"')
            result.append(f"{i}. {title}")
        
        return "\n".join(result)
    except Exception as e:
        return f"❌ News fetch failed: {e}"

@tool
def web_scrape(url: str, extract_main: bool = True) -> str:
    """Scrape and read the main content of a website URL."""
    print(f"Called web_scrape: {url}")
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cleanup
        junk_tags = ["script", "style", "nav", "header", "footer", "aside", 
                     "iframe", "noscript", "form", "button", "input", "select"]
        for tag in soup(junk_tags):
            tag.decompose()
        
        # Try to find main content
        main_content = None
        if extract_main:
            main_content = soup.find('main') or soup.find('article')
            if not main_content:
                for content_id in ["content", "main", "article", "post"]:
                    main_content = soup.find(id=content_id)
                    if main_content: break
        
        target = main_content or soup.find('body') or soup
        text = target.get_text(separator='\n', strip=True)
        
        lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 15]
        clean_text = '\n'.join(lines)
        
        if len(clean_text) > 2000:
            # Auto-ingest logic would go here, simplified to return truncated for refactor safety
            # To restore full fidelity, we should duplicate the auto-ingest or keep it simple.
            # For now, let's keep it simple and safe.
            return f"📄 Content (Truncated, {len(clean_text)} chars):\n{clean_text[:2000]}...\n(Full auto-ingest moved to Memory tools)"
            
        if len(clean_text) < 100:
            return f"⚠️ Could not extract meaningful content from {url}."
        
        return clean_text
    except Exception as e:
        return f"❌ Scraping failed: {e}"
