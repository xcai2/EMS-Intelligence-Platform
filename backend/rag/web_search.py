"""
Web search integration using Brave Search API.
"""
import httpx
from typing import Optional
from backend.core.config import BRAVE_API_KEY, BRAVE_SEARCH_URL, WEB_SEARCH_RESULTS


async def search_web(
    query: str,
    count: int = WEB_SEARCH_RESULTS,
) -> list[dict]:
    """
    Search the web using Brave Search API.
    
    Args:
        query: Search query
        count: Number of results to return
        
    Returns:
        List of web search results
    """
    results, _error = await search_web_with_diagnostics(query, count)
    return results


async def search_web_with_diagnostics(
    query: str,
    count: int = WEB_SEARCH_RESULTS,
) -> tuple[list[dict], str | None]:
    """
    Search web and return diagnostics for debugging UX/API behavior.
    Returns: (results, error_message)
    """
    if not BRAVE_API_KEY:
        return [], "BRAVE_API_KEY not set"

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
    }

    params = {
        "q": query,
        "count": count,
        "safesearch": "moderate",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                BRAVE_SEARCH_URL,
                headers=headers,
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

        results = []
        web_results = data.get("web", {}).get("results", [])

        for result in web_results[:count]:
            results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "description": result.get("description", ""),
                "published": result.get("age", ""),
            })

        return results, None

    except httpx.HTTPStatusError as e:
        return [], f"Brave API HTTP {e.response.status_code}"
    except httpx.RequestError as e:
        return [], f"Network request error: {e}"
    except Exception as e:
        return [], f"Web search error: {e}"


def search_web_sync(query: str, count: int = WEB_SEARCH_RESULTS) -> list[dict]:
    """Synchronous version of web search for non-async contexts."""
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(search_web(query, count))


def format_web_results_for_context(results: list[dict]) -> str:
    """Format web results as context for LLM."""
    if not results:
        return ""
    
    parts = []
    for i, result in enumerate(results, 1):
        parts.append(f"[Web {i}: {result['title']}]\n{result['description']}\nURL: {result['url']}")
    
    return "\n\n".join(parts)
