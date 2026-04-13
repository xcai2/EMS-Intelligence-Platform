"""
Web search integration using Brave Search API.
"""
import asyncio
import httpx
from typing import Optional
from backend.core.config import BRAVE_API_KEY, BRAVE_SEARCH_URL, WEB_SEARCH_RESULTS

# ---------------------------------------------------------------------------
# Rate limiter — Brave free tier: ~1 req/sec.
# Semaphore(1) allows only one in-flight Brave request at a time.
# The 1.1 s sleep inside the semaphore block spaces requests naturally so
# concurrent callers (e.g. 12 companies fetching in parallel) never exceed
# ~1 req/sec and won't 429.
# ---------------------------------------------------------------------------
_brave_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _brave_semaphore
    if _brave_semaphore is None:
        _brave_semaphore = asyncio.Semaphore(1)
    return _brave_semaphore


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
    freshness: str | None = None,
) -> tuple[list[dict], str | None]:
    """
    Search web and return (results, error_message).

    Serialised through a module-level semaphore + 1.1 s post-request sleep to
    stay within Brave's free-tier rate limit (~1 req/sec).

    Args:
        freshness: Brave date filter — "pd" past day, "pw" past week,
                   "pm" past month, "py" past year.  None = no filter.
    """
    if not BRAVE_API_KEY:
        return [], "BRAVE_API_KEY not set"

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params: dict = {
        "q": query,
        "count": count,
        "safesearch": "moderate",
    }
    if freshness:
        params["freshness"] = freshness

    async with _get_semaphore():
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
            for result in data.get("web", {}).get("results", [])[:count]:
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
        finally:
            # Keep the slot locked for 1.1 s so the next waiter fires no
            # sooner than ~1 second after this request completed/failed.
            await asyncio.sleep(1.1)


def search_web_sync(query: str, count: int = WEB_SEARCH_RESULTS) -> list[dict]:
    """Synchronous version of web search for non-async contexts."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(search_web(query, count))


async def fetch_page_text(url: str, max_chars: int = 3000) -> str:
    """Fetch and extract main text content from a web page."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                url,
                timeout=8.0,
                headers={"User-Agent": "Mozilla/5.0 (compatible; CapExIntel/1.0)"},
            )
            resp.raise_for_status()
            html = resp.text

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines)[:max_chars]
    except Exception:
        return ""


async def enrich_web_results(results: list[dict], max_pages: int = 3) -> list[dict]:
    """Fetch full page text for top results to give LLM more context."""
    tasks = [fetch_page_text(r["url"]) for r in results[:max_pages]]
    page_texts = await asyncio.gather(*tasks)
    for r, text in zip(results[:max_pages], page_texts):
        if text:
            r["full_text"] = text
    return results


def format_web_results_for_context(results: list[dict]) -> str:
    """Format web results as context for LLM."""
    if not results:
        return ""
    parts = []
    for i, result in enumerate(results, 1):
        section = f"[Web {i}: {result['title']}]\n{result['description']}\nURL: {result['url']}"
        if result.get("full_text"):
            section += f"\n\n--- Page Content ---\n{result['full_text']}"
        parts.append(section)
    return "\n\n".join(parts)
