from typing import Any

import httpx

from .config import GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL


def ask_lance(question: str, analytics: dict[str, Any], history: list[dict[str, str]] | None = None) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("Groq is not configured. Add GROQ_API_KEY to .env and restart the server.")
    prompt = (
        "You are Lance, a careful business analyst for an SME. Answer the user's question using only the supplied metrics. "
        "Never invent values, causes, or recommendations unsupported by the metrics. Explain comparisons and rankings plainly. "
        "If a metric is unavailable, say so and explain what data is missing. Keep the answer concise and actionable.\n\n"
        f"Structured business snapshot:\n{analytics}"
    )
    messages = [{"role": "system", "content": prompt}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})
    try:
        response = httpx.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": GROQ_MODEL, "temperature": 0.2, "messages": messages},
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        return body["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as error:
        try:
            message = error.response.json().get("error", {}).get("message")
        except (ValueError, TypeError):
            message = None
        detail = f" Groq said: {message}" if message else ""
        raise RuntimeError(f"Lance could not use the configured Groq model.{detail}") from error
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
        raise RuntimeError("Lance could not reach the Groq model right now.") from error
        