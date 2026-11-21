"""Free, keyless news context for Ghana from the GDELT DOC 2.0 API.

GDELT indexes world news, is free for any use with attribution and needs no key. It is
slow to answer and asks for at most one request every five seconds, so this module is
strictly best effort: answers are cached, requests are spaced out, and any failure returns
an empty list. Nothing in Ferlance depends on it. Results are leads to read, not evidence.

Only short product or topic keywords are sent; never customer names or business figures.
"""

import logging
import re
import threading
import time
from collections import OrderedDict
from datetime import date
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
MIN_SPACING_SECONDS = 5.5
# Kept short: news is a nice-to-have and must never hold up an answer the user is waiting for.
TIMEOUT = httpx.Timeout(4.0)
MAX_WAIT_SECONDS = 1.0
MAX_RESULTS = 5
CACHE_SIZE = 256
CACHE_SECONDS = 6 * 3600

_lock = threading.Lock()
_last_request = 0.0
_cache: "OrderedDict[tuple, tuple[float, list[dict[str, str]]]]" = OrderedDict()


def _keywords(text: str) -> str:
    """Plain words only, up to six. Pack sizes such as "5kg" or "400g" are dropped: news never mentions them,
    and GDELT rejects very short or symbol-heavy queries."""
    words = [word for word in re.sub(r"[^\w\s]", " ", text).split() if len(word) >= 3 and not any(ch.isdigit() for ch in word)]
    return " ".join(words[:6])


def search(topic: str, start: date | None = None, end: date | None = None, client: Any = httpx) -> list[dict[str, str]]:
    """Recent Ghanaian news about a topic, newest first. Returns [] when nothing useful comes back."""
    global _last_request
    keywords = _keywords(topic)
    if not keywords:
        return []
    key = (keywords.casefold(), start, end)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]

    phrase = f'"{keywords}"' if " " in keywords else keywords
    params = {"query": f"{phrase} sourcecountry:GH", "mode": "artlist", "format": "json", "maxrecords": str(MAX_RESULTS), "sort": "datedesc"}
    if start and end:
        params["startdatetime"] = start.strftime("%Y%m%d000000")
        params["enddatetime"] = end.strftime("%Y%m%d235959")
    else:
        params["timespan"] = "3months"

    if not _lock.acquire(timeout=MAX_WAIT_SECONDS):
        return []  # another lookup is in flight; skip rather than queue the user behind it
    try:
        wait = MIN_SPACING_SECONDS - (time.monotonic() - _last_request)
        if wait > MAX_WAIT_SECONDS:
            return []
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            response = client.get(GDELT_URL, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            # GDELT answers rate-limit notices as plain text, which fails JSON parsing.
            logger.info("News context unavailable: %s", type(error).__name__)
            return []
    finally:
        _lock.release()

    results = [
        {
            "title": str(article.get("title", ""))[:200],
            "url": str(article.get("url", "")),
            "source": str(article.get("domain", "")),
            "date": str(article.get("seendate", ""))[:8],
        }
        for article in body.get("articles", []) or []
        if str(article.get("url", "")).startswith(("http://", "https://"))
    ][:MAX_RESULTS]
    _cache[key] = (time.monotonic(), results)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return results


def digest(results: list[dict[str, str]]) -> str:
    """Plain-text list for a model prompt."""
    if not results:
        return "No news results."
    return "\n".join(f"- [{index}] {item['title']} ({item['source']}, {item['date']})" for index, item in enumerate(results, 1))
