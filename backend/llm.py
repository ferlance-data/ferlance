from typing import Any

import httpx

from .config import (
    GROQ_API_KEY,
    GROQ_API_URL,
    GROQ_MODEL,
    GROQ_TIMEOUT_SECONDS,
    OPENROUTER_APP_NAME,
    OPENROUTER_KEY,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_MODELS,
    OPENROUTER_SITE_URL,
    OPENROUTER_TIMEOUT_SECONDS,
    OPENROUTER_URL,
)


def _messages(question: str, analytics: dict[str, Any], history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    prompt = (
        "You are Lance, a careful business analyst for an SME. Answer the user's question using only the supplied metrics. "
        "Never invent values, causes, or recommendations unsupported by the metrics. Explain comparisons and rankings plainly. "
        "If a metric is unavailable, say so and explain what data is missing. Keep the answer concise and actionable.\n\n"
        f"Structured business snapshot:\n{analytics}"
    )
    messages = [{"role": "system", "content": prompt}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})
    return messages


def _response_text(response: httpx.Response) -> str:
    response.raise_for_status()
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("The model returned an empty response.")
    return content.strip()


def _failure(response: httpx.Response) -> str:
    try:
        message = response.json().get("error", {}).get("message")
    except (ValueError, TypeError):
        message = None
    return str(message or f"HTTP {response.status_code}")


def ask_lance(question: str, analytics: dict[str, Any], history: list[dict[str, str]] | None = None) -> str:
    """Try five OpenRouter models, then Groq, with bounded provider attempts."""
    messages = _messages(question, analytics, history)
    errors: list[str] = []
    if OPENROUTER_KEY:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-Title": OPENROUTER_APP_NAME,
        }
        for model in OPENROUTER_MODELS[:5]:
            try:
                response = httpx.post(OPENROUTER_URL, headers=headers, json={"model": model, "temperature": 0.2, "max_tokens": OPENROUTER_MAX_TOKENS, "messages": messages}, timeout=OPENROUTER_TIMEOUT_SECONDS)
                return _response_text(response)
            except httpx.HTTPStatusError as error:
                errors.append(f"OpenRouter {model}: {_failure(error.response)}")
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
                errors.append(f"OpenRouter {model}: {type(error).__name__}")
    else:
        errors.append("OpenRouter: OPENROUTER_KEY is not configured")

    if GROQ_API_KEY:
        try:
            response = httpx.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "temperature": 0.2, "max_tokens": OPENROUTER_MAX_TOKENS, "messages": messages},
                timeout=GROQ_TIMEOUT_SECONDS,
            )
            return _response_text(response)
        except httpx.HTTPStatusError as error:
            errors.append(f"Groq {GROQ_MODEL}: {_failure(error.response)}")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            errors.append(f"Groq {GROQ_MODEL}: {type(error).__name__}")
    else:
        errors.append("Groq: GROQ_API_KEY is not configured")
    raise RuntimeError("Lance could not get a response after five OpenRouter models and the Groq fallback. " + " | ".join(errors))
