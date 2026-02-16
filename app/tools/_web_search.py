"""Web search tool handler."""

import logging

log = logging.getLogger(__name__)


async def handle_web_search(arguments: dict, brave_api_key: str) -> str:
    query = arguments.get("query", "").strip()
    if not query:
        return "Error: query is required."
    count = min(int(arguments.get("count", 5)), 20)
    try:
        from brave_search_python_client import BraveSearch, WebSearchRequest

        bs = BraveSearch(api_key=brave_api_key)
        response = await bs.web(WebSearchRequest(q=query, count=count))
        if not response.web or not response.web.results:
            return f"No results found for: {query}"
        lines = []
        for r in response.web.results:
            title = getattr(r, "title", "")
            url = getattr(r, "url", "")
            desc = getattr(r, "description", "")
            lines.append(f"**{title}**\n{url}\n{desc}")
        return "\n\n".join(lines)
    except Exception as e:
        log.exception("Web search error")
        return f"Search error: {e}"
