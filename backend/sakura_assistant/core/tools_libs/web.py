import os
import json
import time
import webbrowser
from langchain_core.tools import tool
from typing import Optional
from .common import log_api_call

# V17.5: Progress Emitter for SSE streaming
def _get_emitter():
    """Lazy-load progress emitter to avoid circular imports."""
    try:
        from ...utils.progress_emitter import get_progress_emitter
        return get_progress_emitter()
    except:
        return None

# --- Caching ---
_weather_cache = {}  # {city_lower: (result, timestamp)}
WEATHER_CACHE_TTL = 600  # 10 minutes

# --- Bookmarks ---
def _load_bookmarks():
    """Load bookmarks from JSON file."""
    # Use persistent storage (AppData/SakuraV10/data/bookmarks.json)
    from ..config import get_project_root
    bookmarks_path = os.path.join(get_project_root(), "data", "bookmarks.json")
    
    if os.path.exists(bookmarks_path):
        try:
            with open(bookmarks_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Flatten all categories into single dict
                flat = {}
                for category, sites in data.items():
                    flat.update(sites)
                return flat, bookmarks_path
        except Exception:
            pass
    return {}, bookmarks_path

def _fuzzy_match(query: str, options: dict) -> tuple:
    """Find best matching site using fuzzy matching."""
    query = query.lower().strip().replace(" ", "")
    
    # Exact match first
    if query in options:
        return query, options[query]
    
    # Partial match
    for name, url in options.items():
        if query in name or name in query:
            return name, url
    
    # Try matching without common words
    for word in ["open", "go to", "launch", "start", "my"]:
        query = query.replace(word.replace(" ", ""), "")
    
    for name, url in options.items():
        if query in name or name in query:
            return name, url
    
    return None, None

# --- Web Tools ---

@tool
def play_youtube(topic: str) -> str:
    """Play a video or song on YouTube. Opens and auto-plays the first matching video."""
    try:
        from urllib.parse import quote
        import requests
        
        # Method 1: Try to get actual first video ID (more reliable auto-play)
        try:
            search_url = f"https://www.youtube.com/results?search_query={quote(topic)}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(search_url, headers=headers, timeout=5)
            
            import re
            match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', response.text)
            if match:
                video_id = match.group(1)
                play_url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
                webbrowser.open(play_url)
                return f"▶️ Now playing on YouTube: '{topic}'"
        except Exception:
            pass
        
        # Method 2: Fallback
        search_url = f"https://www.youtube.com/results?search_query={quote(topic)}"
        webbrowser.open(search_url)
        return f" Opening YouTube search for '{topic}'."
        
    except Exception as e:
        return f" YouTube error: {e}"

@tool
def get_weather(city: str = "") -> str:
    """Get current weather for a city. Results are cached for 10 minutes."""
    import requests
    
    if not city:
        city = "Bangalore"
    
    city_key = city.lower().strip()
    
    # Check cache
    if city_key in _weather_cache:
        cached_result, cached_time = _weather_cache[city_key]
        if time.time() - cached_time < WEATHER_CACHE_TTL:
            return cached_result + " (cached)"
    
    try:
        url = f"https://wttr.in/{city}?format=%l:+%c+%t+(%f)+%h+%w"
        response = requests.get(url, timeout=5, headers={'User-Agent': 'curl/7.68.0'})
        
        if response.status_code == 200 and "Unknown location" not in response.text:
            result = f"️ {response.text.strip()}"
            _weather_cache[city_key] = (result, time.time())
            return result
        else:
            return f" Could not find weather for '{city}'."
    except Exception as e:
        return f" Weather unavailable: {e}"

@tool
def open_site(site_name: str) -> str:
    """Open a frequently used website by name. Supports fuzzy matching.
    
    Examples: 'open whatsapp', 'linkedin', 'github', 'netflix', 'anime'
    
    See all available shortcuts with 'list my bookmarks'.
    """
    bookmarks, _ = _load_bookmarks()
    
    if not bookmarks:
        return " No bookmarks configured. Add sites to data/bookmarks.json."
    
    matched_name, url = _fuzzy_match(site_name, bookmarks)
    
    if url:
        webbrowser.open(url)
        return f" Opening {matched_name}: {url}"
    else:
        # Suggest similar
        suggestions = [name for name in bookmarks.keys() if site_name[0].lower() == name[0].lower()][:5]
        if suggestions:
            return f" Site '{site_name}' not found. Did you mean: {', '.join(suggestions)}?"
        return f" Site '{site_name}' not found. Use 'list my bookmarks' to see available sites."

@tool
def list_bookmarks() -> str:
    """List all available website shortcuts/bookmarks."""
    from ..config import get_project_root
    bookmarks_path = os.path.join(get_project_root(), "data", "bookmarks.json")
    
    if not os.path.exists(bookmarks_path):
        return " No bookmarks file found."
    
    try:
        with open(bookmarks_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        lines = [" **Available Site Shortcuts:**\n"]
        for category, sites in data.items():
            lines.append(f"\n**{category.title()}:**")
            site_list = ", ".join(sites.keys())
            lines.append(f"  {site_list}")
        
        return "\n".join(lines)
    except Exception as e:
        return f" Error loading bookmarks: {e}"

@tool
def save_bookmark(name: str, url: str, category: str = "custom") -> str:
    """Save a new website shortcut/bookmark.
    
    Args:
        name: Short name for the site (e.g., 'mysite')
        url: Full URL (e.g., 'https://example.com')
        category: Category to save under (default: 'custom')
    """
    from ..config import get_project_root
    bookmarks_path = os.path.join(get_project_root(), "data", "bookmarks.json")
    
    try:
        # Load existing
        data = {}
        if os.path.exists(bookmarks_path):
            with open(bookmarks_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        # Add new bookmark
        if category not in data:
            data[category] = {}
        
        data[category][name.lower().strip()] = url.strip()
        
        # Save
        with open(bookmarks_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        return f" Saved bookmark: '{name}' → {url}"
    except Exception as e:
        return f" Failed to save bookmark: {e}"

@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information."""
    emitter = _get_emitter()
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return " TAVILY_API_KEY missing."
    try:
        from tavily import TavilyClient
        print(f"Called Search: {query}")
        
        # V17.5: Emit progress
        if emitter:
            emitter.tool_progress("web_search", f"🔍 Searching web for '{query[:30]}...'")
        
        max_results = min(max_results, 10)
        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results)
        
        results = response.get("results", [])
        if not results:
            if emitter:
                emitter.tool_progress("web_search", "⚠️ No results found")
            return " No search results found."
        
        # V17.5: Emit result count
        if emitter:
            emitter.tool_success("web_search", f"✅ Found {len(results)} results")
        
        out = []
        for r in results:
            title = r.get("title", "No title")
            snippet = r.get("content", "")[:200]
            url = r.get("url", "")
            out.append(f" **{title}**\n   {snippet}...\n    {url}")
        
        return "\n\n".join(out)
    except Exception as e:
        if emitter:
            emitter.tool_error("web_search", str(e))
        return f" Search failed: {e}"

@tool
def search_wikipedia(query: str) -> str:
    """Search Wikipedia for a summary."""
    emitter = _get_emitter()
    print("Called Wikipedia search")
    
    # V17.5: Emit progress
    if emitter:
        emitter.tool_progress("search_wikipedia", f"🔍 Searching Wikipedia for '{query[:30]}...'")
    
    try:
        import wikipedia
        wikipedia.set_lang("en")
        search_results = wikipedia.search(query, results=1)
        if not search_results:
            if emitter:
                emitter.tool_progress("search_wikipedia", "⚠️ No Wikipedia page found")
            return " No Wikipedia page found."
        
        page_title = search_results[0]
        
        # V17.5: Emit found page
        if emitter:
            emitter.tool_progress("search_wikipedia", f"📖 Found article: {page_title}")
        
        summary = wikipedia.summary(page_title, sentences=3)
        
        # V17.5: Emit success
        if emitter:
            emitter.tool_success("search_wikipedia", f"✅ Retrieved summary ({len(summary)} chars)")
        
        return f" Wikipedia ({page_title}):\n{summary}\n(Source: {wikipedia.page(page_title).url})"
    except ImportError:
        return " 'wikipedia' library not installed."
    except Exception as e:
        if emitter:
            emitter.tool_error("search_wikipedia", str(e))
        return f" Wikipedia error: {e}"

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
            results.append(f" {r.title}\n   - Authors: {', '.join(a.name for a in r.authors)}\n   - Summary: {r.summary[:200]}...\n   - PDF: {r.pdf_url}")
            
        if not results:
            return " No papers found."
            
        return "\n\n".join(results)
    except ImportError:
        return " 'arxiv' library not installed."
    except Exception as e:
        return f" Arxiv error: {e}"

@tool
def get_news(topic: str = "technology") -> str:
    """Get latest news headlines."""
    emitter = _get_emitter()
    import requests
    
    # V17.5: Emit progress
    if emitter:
        emitter.tool_progress("get_news", f"📰 Fetching {topic} news...")
    
    try:
        url = f"https://news.google.com/rss/search?q={topic}&hl=en-IN&gl=IN&ceid=IN:en"
        response = requests.get(url, timeout=5)
        
        if response.status_code != 200:
            if emitter:
                emitter.tool_error("get_news", f"HTTP {response.status_code}")
            return f" News fetch failed"
        
        import re
        titles = re.findall(r"<title>(.*?)</title>", response.text)
        headlines = titles[1:6]  # Top 5 headlines
        
        if not headlines:
            if emitter:
                emitter.tool_progress("get_news", f"⚠️ No news found for '{topic}'")
            return f" No news found for '{topic}'"
        
        # V17.5: Emit success
        if emitter:
            emitter.tool_success("get_news", f"✅ Found {len(headlines)} headlines")
        
        result = [f" **Top {topic} news:**"]
        for i, title in enumerate(headlines, 1):
            title = title.replace("&amp;", "&").replace("&quot;", '"')
            result.append(f"{i}. {title}")
        
        return "\n".join(result)
    except Exception as e:
        if emitter:
            emitter.tool_error("get_news", str(e))
        return f" News fetch failed: {e}"

@tool
def web_scrape(url: str, extract_main: bool = True) -> str:
    """Scrape and read the main content of a website URL.
    
    V15.2.2: Sanitizes content to prevent indirect prompt injection.
    """
    emitter = _get_emitter()
    print(f"Called web_scrape: {url}")
    
    # V17.5: Emit progress
    if emitter:
        emitter.tool_progress("web_scrape", f"🌐 Connecting to {url[:40]}...")
    
    try:
        import requests
        import re
        from bs4 import BeautifulSoup
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # V17.5: Emit download complete
        if emitter:
            size_kb = len(response.content) / 1024
            emitter.tool_progress("web_scrape", f"📥 Downloaded {size_kb:.1f} KB")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cleanup junk tags
        junk_tags = ["script", "style", "nav", "header", "footer", "aside", 
                     "iframe", "noscript", "form", "button", "input", "select"]
        for tag in soup(junk_tags):
            tag.decompose()
        
        # V17.5: Emit extraction progress
        if emitter:
            emitter.tool_progress("web_scrape", "🔍 Extracting content...")
        
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
        
        # V15.2.2: Sanitize for prompt injection
        text = _sanitize_scraped_content(text)
        
        lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 15]
        clean_text = '\n'.join(lines)
        
        # V17.5: Emit success
        if emitter:
            emitter.tool_success("web_scrape", f"✅ Extracted {len(clean_text)} characters")
        
        if len(clean_text) > 2000:
            return f" Content (Truncated, {len(clean_text)} chars):\n{clean_text[:2000]}...\n(Full auto-ingest moved to Memory tools)"
            
        if len(clean_text) < 100:
            return f"⚠️ Could not extract meaningful content from {url}."
        
        return clean_text
    except Exception as e:
        if emitter:
            emitter.tool_error("web_scrape", str(e))
        return f" Scraping failed: {e}"


def _sanitize_scraped_content(text: str) -> str:
    """
    V15.2.2: Sanitize scraped content to prevent indirect prompt injection.
    
    Removes patterns that could trick the LLM into executing malicious commands.
    """
    import re
    
    # Prompt injection patterns to remove
    injection_patterns = [
        r"IGNORE (PREVIOUS|ALL|ABOVE) INSTRUCTIONS",
        r"SYSTEM (PROMPT|MESSAGE|OVERRIDE)",
        r"YOU ARE NOW IN .* MODE",
        r"IMPORTANT:.*USE TOOL",
        r"DISREGARD YOUR.*GUIDELINES",
        r"ADMIN (MODE|OVERRIDE)",
        r"<\s*system\s*>.*?</\s*system\s*>",
        r"EXECUTE:.*",
        r"RUN COMMAND:.*",
    ]
    
    for pattern in injection_patterns:
        text = re.sub(pattern, "[FILTERED]", text, flags=re.IGNORECASE | re.DOTALL)
    
    # Cap length to prevent context overflow attacks
    if len(text) > 10000:
        text = text[:10000] + "\n[TRUNCATED FOR SECURITY]"
    
    return text
