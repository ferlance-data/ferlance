"""Retrieval evaluation for Ask Lance (PRD 8.1). Run: .venv/bin/python -m tools.eval.rag_eval

Builds a deterministic synthetic shop (about 600 sales and MoMo records), asks 10 questions with
known relevant rows, and scores the retriever: precision@10 (share of the top 10 that are
relevant), hit@10 (at least one relevant row) and p95 latency. Variants are compared on the
same data so a change to retrieval is adopted only if it measurably helps.

Results (2026-11-22, 597 records):
- v1 FTS5 (field names indexed, no date scope): precision@10 0.78, hit@10 9/10, p95 4 ms
- v2 FTS5 (values only, stopwords, date scope, porter): precision@10 0.90, hit@10 9/10, p95 4 ms  <- adopted
- v2 + embeddings (openai/text-embedding-3-small via OpenRouter, RRF): precision@10 0.91, hit@10 10/10,
  but p95 3,000 ms per question (network round trip) and 22 s to index 600 rows; cost $0.0002 per 600 rows.
  Not adopted: it misses the 100 ms latency budget 30 times over for a 0.01 gain. The only question
  it helped ("beverage") is answered from the analytics snapshot Lance already receives.
"""

import random
import statistics
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

PRODUCTS = {"Rice 5kg": 95, "Beans 1kg": 32, "Cooking oil 1L": 48, "Sugar 1kg": 18, "Tomato paste": 9, "Milo 400g": 55, "Sardines": 14, "Bread loaf": 12}
CUSTOMERS = ["Walk-in", "Kofi Mensah", "Abena Boateng", "Yaw Owusu", "Efua Asante", "Kwame Darko"]
CATEGORY = {"Milo 400g": "beverage"}


def records() -> list[dict]:
    rng = random.Random(11)
    rows = []
    start = date(2026, 8, 1)
    for day in range(92):
        for _ in range(rng.randint(4, 8)):
            product = rng.choice(list(PRODUCTS))
            quantity = rng.randint(1, 8)
            rows.append({
                "transaction_date": (start + timedelta(days=day)).isoformat(),
                "product": product,
                "customer": rng.choice(CUSTOMERS),
                "quantity": quantity,
                "amount": PRODUCTS[product] * quantity,
                "currency": "GHS",
            })
    for day in range(0, 92, 3):
        rows.append({"transaction_date": (start + timedelta(days=day)).isoformat(), "customer": rng.choice(CUSTOMERS[1:]), "amount": rng.randint(20, 300),
                     "channel": "MTN MoMo", "reference": "Payment received", "currency": "GHS"})
    return rows


def has(field, *words):
    return lambda r: all(w.lower() in str(r.get(field, "")).lower() for w in words)


QUESTIONS = [
    ("How much rice did Kofi Mensah buy?", None, lambda r: has("product", "rice")(r) and has("customer", "kofi")(r)),
    ("What did Abena Boateng buy?", None, has("customer", "abena")),
    ("Show me cooking oil sales", None, has("product", "cooking oil")),
    ("Which customers bought sardines in September?", (date(2026, 9, 1), date(2026, 9, 30)), lambda r: has("product", "sardines")(r) and r["transaction_date"].startswith("2026-09")),
    ("Milo sales to walk-in customers", None, lambda r: has("product", "milo")(r) and has("customer", "walk")(r)),
    ("Kwame Darko purchases this month", (date(2026, 10, 1), date(2026, 10, 31)), lambda r: has("customer", "kwame")(r) and r["transaction_date"].startswith("2026-10")),
    ("How are my beverage sales doing?", None, lambda r: CATEGORY.get(r.get("product")) == "beverage"),
    ("Mobile money payments received from customers", None, has("channel", "momo")),
    ("tomato paste", None, has("product", "tomato")),
    ("Did Yaw buy bread?", None, lambda r: has("product", "bread")(r) and has("customer", "yaw")(r)),
]


def evaluate(retrieve, data, label):
    precisions, hits, latencies = [], [], []
    per_question = []
    for question, window, gold in QUESTIONS:
        started = time.perf_counter()
        got = retrieve(question, window)
        latencies.append((time.perf_counter() - started) * 1000)
        relevant = [gold(r) for r in got[:10]]
        precisions.append(sum(relevant) / 10)
        hits.append(any(relevant))
        per_question.append(f"{sum(relevant):>2}/10  {question}")
    p95 = sorted(latencies)[int(0.95 * (len(latencies) - 1))]
    print(f"\n== {label}: precision@10 {statistics.mean(precisions):.2f} · hit@10 {sum(hits)}/{len(hits)} · p95 {p95:.1f} ms")
    print("\n".join(per_question))
    return statistics.mean(precisions)


def fts_retriever(module, data):
    """Wrap backend.rag (or a candidate module) over a throwaway database."""
    from backend import config, db

    tmp = Path(tempfile.mkdtemp())
    config.DB_PATH = tmp / "eval.sqlite3"
    db.initialize(config.DB_PATH)
    module.index_dataset(config.DB_PATH, "b1", "d1", data)
    dataset = {"id": "d1", "filename": "shop.csv"}
    lookup = {module._record_text(r): r for r in data} if hasattr(module, "_record_text") else {}

    def run(question, window):
        kwargs = {"from_date": window[0], "to_date": window[1]} if window and "from_date" in module.retrieve.__code__.co_varnames else {}
        rows = module.retrieve(config.DB_PATH, "b1", question, [dataset], limit=10, **kwargs)
        return [row.get("record") or lookup.get(row["evidence"], {}) for row in rows]

    return run


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from backend import rag

    data = records()
    print(f"{len(data)} records")
    evaluate(fts_retriever(rag, data), data, "current FTS5")


def vector_experiment(data, fts):
    """Hybrid FTS + embeddings via OpenRouter (PRD 8.2). Needs OPENROUTER_KEY; costs a fraction of a cent."""
    import httpx
    import numpy as np

    from backend import config, rag

    model = "openai/text-embedding-3-small"

    def embed(texts):
        started = time.perf_counter()
        response = httpx.post("https://openrouter.ai/api/v1/embeddings", headers={"Authorization": f"Bearer {config.OPENROUTER_KEY}"},
                              json={"model": model, "input": texts}, timeout=60)
        response.raise_for_status()
        body = response.json()
        vectors = np.array([item["embedding"] for item in body["data"]], dtype=np.float32)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True), (time.perf_counter() - started) * 1000, body.get("usage", {})

    texts = [rag._record_text(r) for r in data]
    started = time.perf_counter()
    doc_vectors, _, usage = embed(texts)
    print(f"\nembedded {len(texts)} records in {(time.perf_counter() - started):.1f} s · usage {usage}")
    query_ms = []

    def hybrid(question, window):
        vector, ms, _ = embed([question])
        query_ms.append(ms)
        scores = doc_vectors @ vector[0]
        allowed = [i for i, r in enumerate(data) if not window or window[0].isoformat() <= r["transaction_date"] <= window[1].isoformat()]
        semantic = sorted(allowed, key=lambda i: -scores[i])[:30]
        keyword = [data.index(r) for r in fts(question, window) if r in data]
        fused = {}
        for ranking in (keyword, semantic):
            for rank, index in enumerate(ranking):
                fused[index] = fused.get(index, 0) + 1 / (60 + rank)
        return [data[i] for i in sorted(fused, key=lambda i: -fused[i])]

    evaluate(hybrid, data, f"hybrid FTS + {model}")
    print(f"query embedding round trip: median {statistics.median(query_ms):.0f} ms, p95 {sorted(query_ms)[int(0.95 * (len(query_ms) - 1))]:.0f} ms")


if __name__ == "__main__" and "--vectors" in sys.argv:
    vector_experiment(data, fts_retriever(rag, data))
