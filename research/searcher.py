"""Web search across multiple languages using DuckDuckGo."""

import logging
import time

from duckduckgo_search import DDGS

log = logging.getLogger(__name__)


def search_category(category: dict, languages: list[dict], config: dict) -> list[dict]:
    """Search a single category across all configured languages.

    Returns a list of result dicts with keys:
        title, url, snippet, language, category, query
    """
    max_results = config["search"].get("max_results_per_query", 10)
    delay = config["search"].get("request_delay_seconds", 3)
    results = []

    queries_by_lang = category.get("queries", {})

    for lang in languages:
        lang_code = lang["code"]
        region = lang.get("region", "wt-wt")
        lang_queries = queries_by_lang.get(lang_code, [])

        for query in lang_queries:
            try:
                hits = _do_search(query, region, max_results)
                for hit in hits:
                    results.append({
                        "title": hit.get("title", ""),
                        "url": hit.get("href", ""),
                        "snippet": hit.get("body", ""),
                        "language": lang_code,
                        "language_name": lang["name"],
                        "category": category["name"],
                        "query": query,
                    })
                log.info(f"  [{lang_code}] '{query}' -> {len(hits)} results")
            except Exception as e:
                log.warning(f"  [{lang_code}] '{query}' failed: {e}")
            time.sleep(delay)

    return results


def _do_search(query: str, region: str, max_results: int) -> list[dict]:
    """Execute a single DuckDuckGo search with retry."""
    for attempt in range(3):
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, region=region, max_results=max_results))
        except Exception as e:
            if attempt < 2:
                wait = (attempt + 1) * 5
                log.warning(f"  Search retry in {wait}s: {e}")
                time.sleep(wait)
            else:
                raise
    return []
