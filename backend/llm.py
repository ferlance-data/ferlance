import json
import traceback
from typing import Any

import httpx

from .config import (
    AGENTROUTER_API_KEY,
    AGENTROUTER_MODELS,
    AGENTROUTER_URL,
    GROQ_API_KEY,
    GROQ_API_URL,
    GROQ_MODEL,
    GROQ_TIMEOUT_SECONDS,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_TIMEOUT_SECONDS,
    SERPAPI_KEY,
)

# Snapshot limits (keep the whole request under the provider's tokens-per-minute cap).
MAX_SNAPSHOT_CHARS = 12000
MAX_LIST_ITEMS = 15
MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_CHARS = 1500

# Search limits.
SERPAPI_URL = "https://serpapi.com/search"
# SEARCH_TIMEOUT_SECONDS = 15.0
SEARCH_TIMEOUT = httpx.Timeout(connect=20.0, read=40.0, write=20.0, pool=20.0)
SEARCH_ATTEMPTS = 2
MAX_TOOL_ROUNDS = 2
MAX_SEARCH_RESULTS = 3
MAX_RESULT_CHARS = 400
MAX_QUERY_CHARS = 200

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for market research that supports a business decision: "
            "product value, competitor pricing, or typical market prices. "
            "Do not use it for anything else."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A short, specific search query, for example 'bulk rice 25kg wholesale price Accra'.",
                }
            },
            "required": ["query"],
        },
    },
}


def _compact(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_compact(item) for item in value[:MAX_LIST_ITEMS]]
    return value


def _snapshot(analytics: dict[str, Any]) -> str:
    text = json.dumps(_compact(analytics), separators=(",", ":"), default=str)
    if len(text) > MAX_SNAPSHOT_CHARS:
        text = text[:MAX_SNAPSHOT_CHARS] + "...[snapshot truncated]"
    return text


def _messages(question: str, analytics: dict[str, Any], history: list[dict[str, str]] | None) -> list[dict[str, Any]]:
    search_rule = (
        "You may call the web_search tool, but only for market research on products, product value, "
        "and competitor pricing. Use it only when the question requires external market data. "
        "Treat the business snapshot as the business's own data and web results as external data. "
        "State the source (site name or URL) for every external figure, and never present an external "
        "figure as if it came from the business's own metrics.\n\n"
        if SERPAPI_KEY
        else ""
    )
    prompt = (
        "You are Lance, a careful business analyst for an SME. Answer the user's question using only the supplied metrics"
        + (" and any web search results you retrieve. " if SERPAPI_KEY else ". ")
        + "Never invent values, causes, or recommendations unsupported by the data. Explain comparisons and rankings plainly. "
        "If a metric is unavailable, say so and explain what data is missing. Keep the answer concise and actionable.\n\n"
        f"{search_rule}"
        f"Structured business snapshot (JSON, long lists are shortened):\n{_snapshot(analytics)}"
    )
    trimmed_history = [
        {"role": item["role"], "content": item["content"][:MAX_HISTORY_CHARS]}
        for item in (history or [])[-MAX_HISTORY_MESSAGES:]
    ]
    return [
        {"role": "system", "content": prompt},
        *trimmed_history,
        {"role": "user", "content": question},
    ]


def _failure(response: httpx.Response) -> str:
    try:
        message = response.json().get("error", {}).get("message")
    except (ValueError, TypeError, AttributeError):
        message = None
    return str(message or f"HTTP {response.status_code}")


# def _search(query: str) -> str:
#     """Run one web search and return a short plain-text digest for the model."""
#     if not SERPAPI_KEY:
#         return "Search is unavailable because no search API key is configured."
#     try:
#         response = httpx.post(
#             SERPAPI_URL,
#             headers={"Authorization": f"Bearer {SERPAPI_KEY}", "Content-Type": "application/json"},
#             json={
#                 "query": query[:MAX_QUERY_CHARS],
#                 "max_results": MAX_SEARCH_RESULTS,
#                 "search_depth": "basic",
#             },
#             timeout=SEARCH_TIMEOUT_SECONDS,
#         )
#         response.raise_for_status()
#         results = response.json().get("results", [])
#     except (httpx.HTTPError, ValueError) as error:
#         return f"Search failed ({type(error).__name__}). Answer without external data and say so."
#     if not results:
#         return "The search returned no results."
#     return "\n".join(
#         f"- {item.get('title', '')} ({item.get('url', '')}): {str(item.get('content', ''))[:MAX_RESULT_CHARS]}"
#         for item in results
#     )


def _search(query: str) -> str:
    """Run one SerpAPI Google search and return a short plain-text digest for the model."""
    print(f"[search] query={query!r}")
    if not SERPAPI_KEY:
        return "Search is unavailable because no search API key is configured."

    body: dict[str, Any] = {}
    for attempt in range(1, SEARCH_ATTEMPTS + 1):
        try:
            response = httpx.get(
                SERPAPI_URL,
                params={
                    "engine": "google",
                    "q": query[:MAX_QUERY_CHARS],
                    "api_key": SERPAPI_KEY,
                    "num": MAX_SEARCH_RESULTS,
                    "gl": "gh",
                    "hl": "en",
                },
                timeout=SEARCH_TIMEOUT,
            )
            response.raise_for_status()
            body = response.json()
            break
        except httpx.TimeoutException:
            print(f"[search] timeout on attempt {attempt}/{SEARCH_ATTEMPTS}")
            if attempt == SEARCH_ATTEMPTS:
                return "Search timed out. Answer without external data and say so."
        except httpx.HTTPStatusError as error:
            print(f"[search] HTTP {error.response.status_code}: {error.response.text[:300]}")
            return f"Search failed (HTTP {error.response.status_code}). Answer without external data and say so."
        except (httpx.HTTPError, ValueError) as error:
            print(f"[search] {type(error).__name__}")
            return f"Search failed ({type(error).__name__}). Answer without external data and say so."

    if body.get("error"):
        print(f"[search] SerpAPI error: {body['error']}")
        return f"Search failed: {body['error']}. Answer without external data and say so."

    lines: list[str] = []
    for item in body.get("shopping_results", [])[:MAX_SEARCH_RESULTS]:
        lines.append(f"- {item.get('title', '')} | {item.get('price', 'price n/a')} | {item.get('source', '')}")
    for item in body.get("organic_results", [])[:MAX_SEARCH_RESULTS]:
        lines.append(
            f"- {item.get('title', '')} ({item.get('link', '')}): {str(item.get('snippet', ''))[:MAX_RESULT_CHARS]}"
        )
    return "\n".join(lines) if lines else "The search returned no results."

def _chat(
    url: str,
    headers: dict[str, str],
    model: str,
    messages: list[dict[str, Any]],
    timeout: float,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": OPENROUTER_MAX_TOKENS,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError:
        raise ValueError(
            f"Non-JSON response (status={response.status_code}, "
            f"content-type={response.headers.get('content-type')}, "
            f"url={response.url}): {response.text[:300]!r}"
        )
    return body["choices"][0]["message"]


def _complete(
    url: str,
    headers: dict[str, str],
    model: str,
    messages: list[dict[str, Any]],
    timeout: float,
) -> str:
    """Run the model, executing any requested searches, until a final text answer is produced."""
    conversation = list(messages)
    tools_enabled = bool(SERPAPI_KEY)

    for round_number in range(MAX_TOOL_ROUNDS + 1):
        # The last round never offers tools, which forces a final text answer.
        tools = [SEARCH_TOOL] if tools_enabled and round_number < MAX_TOOL_ROUNDS else None
        try:
            message = _chat(url, headers, model, conversation, timeout, tools)
        except httpx.HTTPStatusError as error:
            # Some models reject malformed tool calls with a 400; retry once without tools.
            if tools and error.response.status_code == 400:
                tools_enabled = False
                continue
            raise

        calls = message.get("tool_calls")
        if not calls:
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("The model returned an empty response.")
            return content.strip()

        conversation.append(
            {"role": "assistant", "content": message.get("content") or "", "tool_calls": calls}
        )
        for call in calls:
            function = call.get("function", {})
            if function.get("name") != "web_search":
                result = "Unknown tool."
            else:
                try:
                    query = str(json.loads(function.get("arguments") or "{}").get("query", "")).strip()
                except (ValueError, AttributeError):
                    query = ""
                result = _search(query) if query else "No query was provided."
            conversation.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})

    raise ValueError("The model did not produce a final answer.")


def ask_lance(question: str, analytics: dict[str, Any], history: list[dict[str, str]] | None = None) -> str:
    """Try Groq first, then AgentRouter models, stopping early on authentication failures."""
    messages = _messages(question, analytics, history)
    errors: list[str] = []

    if GROQ_API_KEY:
        try:
            return _complete(
                GROQ_API_URL,
                {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                GROQ_MODEL,
                messages,
                GROQ_TIMEOUT_SECONDS,
            )
        except httpx.HTTPStatusError as error:
            errors.append(f"Groq {GROQ_MODEL}: {_failure(error.response)}")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            errors.append(f"Groq {GROQ_MODEL}: {type(error).__name__}: {error}")
    else:
        errors.append("Groq: GROQ_API_KEY is not configured")

    if AGENTROUTER_API_KEY:
        headers = {
            "Authorization": f"Bearer {AGENTROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        for model in AGENTROUTER_MODELS:
            try:
                return _complete(AGENTROUTER_URL, headers, model, messages, OPENROUTER_TIMEOUT_SECONDS)
            except httpx.HTTPStatusError as error:
                errors.append(f"AgentRouter {model}: {_failure(error.response)}")
                if error.response.status_code in (401, 403):
                    break
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
                errors.append(f"AgentRouter {model}: {type(error).__name__}: {error}")
            except Exception:
                traceback.print_exc()
                errors.append(f"AgentRouter {model}: unexpected error")
    else:
        errors.append("AgentRouter: AGENTROUTER_API_KEY is not configured")

    raise RuntimeError("Lance could not get a response from any provider. " + " | ".join(errors))