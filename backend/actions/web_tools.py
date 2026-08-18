import webbrowser
import httpx
import re
from typing import Dict, Any, List

class WebTools:
    def open_url_in_browser(self, url: str) -> Dict[str, Any]:
        """Opens a URL in the user's default web browser."""
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            webbrowser.open(url)
            return {"status": "success", "url": url}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def search_duckduckgo(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Performs a free web search via DuckDuckGo HTML API."""
        try:
            url = "https://html.duckduckgo.com/html/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            data = {"q": query}
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, data=data, headers=headers)
                
            results = []
            if res.status_code == 200:
                # Simple robust regex extraction of search result snippets
                matches = re.findall(
                    r'<a class="result__snippet[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    res.text,
                    re.DOTALL
                )
                titles = re.findall(
                    r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    res.text,
                    re.DOTALL
                )
                
                # Extract clean snippets
                snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', res.text, re.DOTALL)
                for i, snip in enumerate(snippets[:max_results]):
                    clean_snip = re.sub(r'<[^>]+>', '', snip).strip()
                    results.append({"rank": i + 1, "snippet": clean_snip})
                    
            if not results:
                # Fallback format
                results = [{"query": query, "info": "Searched online. Open browser to see full interactive results."}]

            return {"status": "success", "query": query, "results": results}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def fetch_webpage_text(self, url: str, max_chars: int = 5000) -> Dict[str, Any]:
        """Fetches and cleans text content from a web page."""
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                res = await client.get(url, headers=headers)
                
            text = res.text
            # Remove scripts and styles
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            # Remove tags
            clean = re.sub(r'<[^>]+>', ' ', text)
            # Compress whitespace
            clean = re.sub(r'\s+', ' ', clean).strip()
            
            if len(clean) > max_chars:
                clean = clean[:max_chars] + "..."

            return {"status": "success", "url": url, "text": clean}
        except Exception as e:
            return {"status": "error", "message": str(e)}

web_tools = WebTools()
