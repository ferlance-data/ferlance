"""Ask Lance: grounded, saved conversations over every included business dataset."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config, dataset_store, db
from ..analytics import analyze
from ..deps import DateRange, current_user, date_range, owned_business
from ..llm import ask_lance
from ..rag import context as rag_context

router = APIRouter(prefix="/api/businesses/{business_id}/ask-lance", tags=["ask lance"])
HISTORY_LIMIT = 12


class AskLanceRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = None


def _analytics_by_currency(records: list[dict], start: date | None, end: date | None) -> dict:
    """Never add amounts across currencies: split the snapshot when more than one is present."""
    currencies = {record.get("currency") or config.DEFAULT_CURRENCY for record in records}
    if len(currencies) <= 1:
        return analyze(records, start, end)
    return {
        "period": analyze(records, start, end)["period"],
        "currency": "MIXED",
        "monetary_aggregation_available": False,
        "warnings": [
            "Business-wide records contain multiple currencies. Amounts are grouped by currency and must not be added or compared without conversion."
        ],
        "by_currency": {
            currency: analyze([r for r in records if (r.get("currency") or config.DEFAULT_CURRENCY) == currency], start, end)
            for currency in sorted(currencies)
        },
    }


@router.post("")
def ask(
    payload: AskLanceRequest,
    dataset_id: str | None = None,
    dates: DateRange = Depends(date_range),
    business: dict = Depends(owned_business),
    user: dict = Depends(current_user),
) -> dict:
    question = payload.question.strip()
    datasets = dataset_store.analysable(business["id"])
    if not datasets:
        raise HTTPException(404, "No accepted business data is available for Lance yet. Import a file first.")
    pinned = next((item for item in datasets if item["id"] == dataset_id), datasets[0])
    conversation = None
    if payload.conversation_id:
        conversation = db.one(
            config.DB_PATH,
            "SELECT * FROM chat_conversations WHERE id = ? AND business_id = ? AND user_id = ?",
            (payload.conversation_id, business["id"], user["id"]),
        )
        if not conversation:
            raise HTTPException(404, "Conversation not found.")
    conversation_id = conversation["id"] if conversation else str(uuid.uuid4())
    history = (
        db.many(
            config.DB_PATH,
            "SELECT role, content FROM (SELECT role, content, created_at, id FROM chat_messages "
            "WHERE conversation_id = ? ORDER BY created_at DESC, id DESC LIMIT ?) ORDER BY created_at, id",
            (conversation_id, HISTORY_LIMIT),
        )
        if conversation
        else []
    )
    try:
        records = dataset_store.records_for(datasets)
        snapshot = rag_context(
            config.DB_PATH,
            business["id"],
            question,
            datasets,
            dates.start,
            dates.end,
            _analytics_by_currency(records, dates.start, dates.end),
        )
    except dataset_store.RecordsUnavailableError as error:
        raise HTTPException(503, str(error))
    try:
        answer = ask_lance(question, snapshot, history)
    except RuntimeError as error:
        raise HTTPException(503, str(error))

    # Persist only after a successful answer so failures never leave empty conversations.
    timestamp = db.now()
    if conversation is None:
        db.insert(
            config.DB_PATH,
            "INSERT INTO chat_conversations VALUES (?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, business["id"], user["id"], pinned["id"], question[:80], timestamp, timestamp),
        )
    db.insert(config.DB_PATH, "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), conversation_id, "user", question, timestamp))
    db.insert(config.DB_PATH, "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), conversation_id, "assistant", answer, db.now()))
    db.insert(config.DB_PATH, "UPDATE chat_conversations SET updated_at = ? WHERE id = ?", (db.now(), conversation_id))
    return {
        "conversation_id": conversation_id,
        "answer": answer,
        "question": question,
        "period": snapshot["analytics"]["period"],
        "dataset": dataset_store.serialize(pinned),
        "scope": snapshot["scope"],
        "datasets_considered": len(datasets),
        "evidence_count": len(snapshot["retrieved_evidence"]),
    }


@router.get("/conversations")
def conversations(business: dict = Depends(owned_business), user: dict = Depends(current_user)) -> list[dict]:
    return db.many(
        config.DB_PATH,
        "SELECT id, dataset_id, title, created_at, updated_at FROM chat_conversations "
        "WHERE business_id = ? AND user_id = ? ORDER BY updated_at DESC",
        (business["id"], user["id"]),
    )


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, business: dict = Depends(owned_business), user: dict = Depends(current_user)) -> dict:
    item = db.one(
        config.DB_PATH,
        "SELECT id, dataset_id, title, created_at, updated_at FROM chat_conversations WHERE id = ? AND business_id = ? AND user_id = ?",
        (conversation_id, business["id"], user["id"]),
    )
    if not item:
        raise HTTPException(404, "Conversation not found.")
    item["messages"] = db.many(
        config.DB_PATH,
        "SELECT id, role, content, created_at FROM chat_messages WHERE conversation_id = ? ORDER BY created_at, id",
        (conversation_id,),
    )
    return item
