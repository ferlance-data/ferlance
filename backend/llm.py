import json
import logging
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
    OPENROUTER_KEY,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_MODELS,
    OPENROUTER_TIMEOUT_SECONDS,
    OPENROUTER_URL,
)
from . import news_context

logger = logging.getLogger(__name__)

# Snapshot limits (keep the whole request under the provider's tokens-per-minute cap).
MAX_SNAPSHOT_CHARS = 12000
MAX_LIST_ITEMS = 15
MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_CHARS = 1500

# Tool limits.
MAX_TOOL_ROUNDS = 2
MAX_QUERY_CHARS = 200

NEWS_TOOL = {
    "type": "function",
    "function": {
        "name": "news_search",
        "description": (
            "Search recent Ghanaian news (free GDELT index) for context on a product, supply, prices or events: "
            "for example a shortage, a price rise, a festival or the weather. Results are headlines only. "
            "Use it only when outside context would change the advice."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Two to five keywords, for example 'rice prices' or 'cooking oil shortage'.",
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
    prompt = (
        "You are Lance, a careful business analyst for an SME in Ghana. Answer the user's question using only the supplied "
        "metrics and any news headlines you retrieve. Never invent values, causes, or recommendations unsupported by the data. "
        "Explain comparisons and rankings plainly. If a metric is unavailable, say so and explain what data is missing. "
        "Keep the answer concise and actionable.\n\n"
        "You may call the news_search tool for outside context (shortages, price rises, festivals, weather). Treat the "
        "business snapshot as the business's own data and news as external leads: name the source of any headline you use, "
        "and never present it as proof or as the business's own figures.\n\n"
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


def _news(query: str) -> str:
    logger.info("Lance news search: %r", query)
    return news_context.digest(news_context.search(query[:MAX_QUERY_CHARS]))


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
    use_tools: bool = True,
) -> str:
    """Run the model, executing any requested searches, until a final text answer is produced."""
    conversation = list(messages)
    tools_enabled = use_tools

    for round_number in range(MAX_TOOL_ROUNDS + 1):
        # The last round never offers tools, which forces a final text answer.
        tools = [NEWS_TOOL] if tools_enabled and round_number < MAX_TOOL_ROUNDS else None
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
            if function.get("name") != "news_search":
                result = "Unknown tool."
            else:
                try:
                    query = str(json.loads(function.get("arguments") or "{}").get("query", "")).strip()
                except (ValueError, AttributeError):
                    query = ""
                result = _news(query) if query else "No query was provided."
            conversation.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})

    raise ValueError("The model did not produce a final answer.")


def ai_available() -> bool:
    return bool(OPENROUTER_KEY or GROQ_API_KEY or AGENTROUTER_API_KEY)


def ask_lance(question: str, analytics: dict[str, Any], history: list[dict[str, str]] | None = None) -> str:
    if not ai_available():
        raise RuntimeError(
            "Ask Lance is not set up on this server yet: add an OpenRouter or Groq API key to the environment. "
            "Instant answers still work without one."
        )
    return _generate(_messages(question, analytics, history), use_tools=True)


def explain(system: str, user: str) -> str:
    """One-shot explanation without tools (the caller supplies any outside context)."""
    if not ai_available():
        raise RuntimeError("AI explanations are not set up on this server: add an OpenRouter or Groq API key.")
    return _generate([{"role": "system", "content": system}, {"role": "user", "content": user}], use_tools=False)


def _generate(messages: list[dict[str, Any]], use_tools: bool) -> str:
    """Try OpenRouter models first, fallback to Groq, then AgentRouter, stopping early on authentication failures."""
    errors: list[str] = []

    if OPENROUTER_KEY:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
        }
        for model in OPENROUTER_MODELS:
            try:
                return _complete(OPENROUTER_URL, headers, model, messages, OPENROUTER_TIMEOUT_SECONDS, use_tools)
            except httpx.HTTPStatusError as error:
                errors.append(f"OpenRouter {model}: {_failure(error.response)}")
                if error.response.status_code in (401, 403):
                    break
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
                errors.append(f"OpenRouter {model}: {type(error).__name__}: {error}")
            except Exception:
                logger.exception("Unexpected Lance provider failure")
                errors.append(f"OpenRouter {model}: unexpected error")
    else:
        errors.append("OpenRouter: OPENROUTER_KEY is not configured")

    if GROQ_API_KEY:
        try:
            return _complete(
                GROQ_API_URL,
                {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                GROQ_MODEL,
                messages,
                GROQ_TIMEOUT_SECONDS,
                use_tools,
            )
        except httpx.HTTPStatusError as error:
            errors.append(f"Groq {GROQ_MODEL}: {_failure(error.response)}")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            errors.append(f"Groq {GROQ_MODEL}: {type(error).__name__}: {error}")
    else:
        errors.append("Groq: GROQ_API_KEY is not configured")

    if AGENTROUTER_API_KEY and AGENTROUTER_API_KEY != OPENROUTER_KEY:
        headers = {
            "Authorization": f"Bearer {AGENTROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        for model in AGENTROUTER_MODELS:
            try:
                return _complete(AGENTROUTER_URL, headers, model, messages, OPENROUTER_TIMEOUT_SECONDS, use_tools)
            except httpx.HTTPStatusError as error:
                errors.append(f"AgentRouter {model}: {_failure(error.response)}")
                if error.response.status_code in (401, 403):
                    break
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
                errors.append(f"AgentRouter {model}: {type(error).__name__}: {error}")
            except Exception:
                logger.exception("Unexpected Lance provider failure")
                errors.append(f"AgentRouter {model}: unexpected error")

    raise RuntimeError("Could not get a response from any AI provider. " + " | ".join(errors))