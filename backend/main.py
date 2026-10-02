import json
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, File, Header, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .analytics import analyze
from .config import ADMIN_EMAILS, COOKIE_SECURE, DB_PATH, MAX_UPLOAD_BYTES, PROCESSED_DIR, RAW_DIR, SECRET_KEY, ensure_storage
from .insights import QUESTION_NAMES, answer_question, generate_insights
from .llm import ask_lance
from .processor import process_file
from .security import create_access_token, create_refresh_token, hash_password, read_access_token, token_hash, verify_password

ensure_storage()
db.initialize(DB_PATH)
app = FastAPI(title="Ferlance MVP", version="0.1.0")
app.mount("/assets", StaticFiles(directory=Path(__file__).parent.parent / "frontend" / "assets"), name="assets")
DATASET_FIELDS = (
    "id",
    "filename",
    "extension",
    "status",
    "source_rows",
    "accepted_rows",
    "rejected_rows",
    "warnings",
    "errors",
    "created_at",
)


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    business_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    full_name: str = Field(default="", max_length=120)
    business_name: str = Field(min_length=1, max_length=120)


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|owner|member)$")


class AskLanceRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = None


def user_from_auth(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required.")
    user_id = read_access_token(authorization.split(" ", 1)[1])
    user = db.one(DB_PATH, "SELECT id, email, role, full_name FROM users WHERE id = ?", (user_id or "",))
    if not user:
        raise HTTPException(401, "Invalid or expired token.")
    return user


def admin_from_auth(user: dict = Depends(user_from_auth)) -> dict:
    if user["role"] != "admin" and user["email"].lower() not in ADMIN_EMAILS:
        raise HTTPException(403, "Administrator privileges are required.")
    return user


def business_for_user(business_id: str, user: dict) -> dict:
    business = db.one(DB_PATH, "SELECT * FROM businesses WHERE id = ? AND user_id = ?", (business_id, user["id"]))
    if not business:
        raise HTTPException(404, "Business not found.")
    return business


def dataset_response(item: dict) -> dict:
    for field in ("warnings", "errors"):
        item[field] = json.loads(item[field])
    return {field: item[field] for field in DATASET_FIELDS}


def read_processed_records(dataset: dict) -> list[dict]:
    if not dataset["processed_path"]:
        return []
    try:
        with Path(dataset["processed_path"]).open("r", encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]
    except (OSError, json.JSONDecodeError):
        raise HTTPException(503, "Processed records are temporarily unavailable.")


def issue_session(user_id: str, response: Response) -> dict:
    refresh_token, expires_at = create_refresh_token()
    db.insert(DB_PATH, "INSERT INTO refresh_sessions VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), user_id, token_hash(refresh_token), expires_at.isoformat(), None, db.now()))
    response.set_cookie("ferlance_refresh", refresh_token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=int((expires_at - datetime.now(timezone.utc)).total_seconds()), path="/api/auth")
    return {"access_token": create_access_token(user_id), "token_type": "bearer"}


def auth_response(user_id: str, business: dict | None, response: Response) -> dict:
    session = issue_session(user_id, response)
    session["business"] = business
    return session


@app.get("/", response_class=FileResponse)
def frontend() -> Path:
    return Path(__file__).parent.parent / "frontend" / "landing.html"


@app.get("/app", response_class=FileResponse)
def application() -> Path:
    return Path(__file__).parent.parent / "frontend" / "index.html"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/signup")
def signup(payload: SignupRequest, response: Response) -> dict:
    email = payload.email.strip().lower()
    if db.one(DB_PATH, "SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "An account with that email already exists.")
    user_id, business_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.insert(DB_PATH, "INSERT INTO users (id, email, password_hash, created_at, role, full_name) VALUES (?, ?, ?, ?, ?, ?)", (user_id, email, hash_password(payload.password), db.now(), "owner", ""))
    db.insert(DB_PATH, "INSERT INTO businesses VALUES (?, ?, ?, ?)", (business_id, user_id, payload.business_name.strip(), db.now()))
    return auth_response(user_id, {"id": business_id, "name": payload.business_name.strip()}, response)


@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response) -> dict:
    user = db.one(DB_PATH, "SELECT * FROM users WHERE email = ?", (payload.email.strip().lower(),))
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")
    business = db.one(DB_PATH, "SELECT id, name FROM businesses WHERE user_id = ? ORDER BY created_at LIMIT 1", (user["id"],))
    return auth_response(user["id"], business, response)


@app.get("/api/auth/me")
def me(user: dict = Depends(user_from_auth)) -> dict:
    business = db.one(DB_PATH, "SELECT id, name FROM businesses WHERE user_id = ? ORDER BY created_at LIMIT 1", (user["id"],))
    return {"user": user, "business": business}


@app.patch("/api/auth/profile")
def update_profile(payload: ProfileUpdate, user: dict = Depends(user_from_auth)) -> dict:
    full_name = payload.full_name.strip()
    business_name = payload.business_name.strip()
    db.insert(DB_PATH, "UPDATE users SET full_name = ? WHERE id = ?", (full_name, user["id"]))
    db.insert(DB_PATH, "UPDATE businesses SET name = ? WHERE user_id = ?", (business_name, user["id"]))
    updated = db.one(DB_PATH, "SELECT id, email, role, full_name FROM users WHERE id = ?", (user["id"],))
    business = db.one(DB_PATH, "SELECT id, name FROM businesses WHERE user_id = ? ORDER BY created_at LIMIT 1", (user["id"],))
    return {"user": updated, "business": business}


@app.get("/api/admin/capabilities")
def admin_capabilities(user: dict = Depends(admin_from_auth)) -> dict:
    return {"role": user["role"], "capabilities": ["view_users", "manage_roles", "manage_profiles", "view_all_businesses"]}


@app.get("/api/admin/users")
def admin_users(user: dict = Depends(admin_from_auth)) -> list[dict]:
    return db.many(DB_PATH, "SELECT id, email, role, full_name, created_at FROM users ORDER BY created_at")


@app.patch("/api/admin/users/{user_id}/role")
def admin_update_role(user_id: str, payload: RoleUpdate, user: dict = Depends(admin_from_auth)) -> dict:
    if not db.one(DB_PATH, "SELECT id FROM users WHERE id = ?", (user_id,)):
        raise HTTPException(404, "User not found.")
    db.insert(DB_PATH, "UPDATE users SET role = ? WHERE id = ?", (payload.role, user_id))
    return db.one(DB_PATH, "SELECT id, email, role, full_name, created_at FROM users WHERE id = ?", (user_id,)) or {}


@app.post("/api/auth/refresh")
def refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias="ferlance_refresh")) -> dict:
    if not refresh_token:
        raise HTTPException(401, "Refresh session is required.")
    session = db.one(DB_PATH, "SELECT * FROM refresh_sessions WHERE token_hash = ? AND revoked_at IS NULL", (token_hash(refresh_token),))
    if not session or datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Refresh session is invalid or expired.")
    db.insert(DB_PATH, "UPDATE refresh_sessions SET revoked_at = ? WHERE id = ?", (db.now(), session["id"]))
    return auth_response(session["user_id"], db.one(DB_PATH, "SELECT id, name FROM businesses WHERE user_id = ? ORDER BY created_at LIMIT 1", (session["user_id"],)), response)


@app.post("/api/auth/logout")
def logout(response: Response, refresh_token: str | None = Cookie(default=None, alias="ferlance_refresh")) -> dict[str, str]:
    if refresh_token:
        db.insert(DB_PATH, "UPDATE refresh_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL", (db.now(), token_hash(refresh_token)))
    response.delete_cookie("ferlance_refresh", path="/api/auth")
    return {"status": "signed_out"}


@app.post("/api/businesses/{business_id}/datasets")
def upload_dataset(business_id: str, file: UploadFile = File(...), user: dict = Depends(user_from_auth)) -> dict:
    business_for_user(business_id, user)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx"}:
        raise HTTPException(415, "Unsupported file type. Upload a CSV or XLSX file.")
    dataset_id = str(uuid.uuid4())
    raw_path = RAW_DIR / f"{dataset_id}{suffix}"
    with raw_path.open("wb") as target:
        total_bytes = 0
        while chunk := file.file.read(1024 * 1024):
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                raw_path.unlink(missing_ok=True)
                raise HTTPException(413, "Uploaded file is too large.")
            target.write(chunk)
    result = process_file(raw_path, suffix)
    processed_path: Path | None = None
    status = "failed" if not result.rows else "partial" if result.rejected_rows or result.errors else "processed"
    if result.rows:
        processed_path = PROCESSED_DIR / f"{dataset_id}.jsonl"
        with processed_path.open("w", encoding="utf-8") as target:
            for row in result.rows:
                target.write(json.dumps(row) + "\n")
    db.insert(DB_PATH, "INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (dataset_id, business_id, file.filename or "dataset", suffix, str(raw_path), str(processed_path) if processed_path else None, status, result.source_rows, len(result.rows), result.rejected_rows, json.dumps(result.warnings), json.dumps(result.errors), db.now()))
    response = db.one(DB_PATH, "SELECT * FROM datasets WHERE id = ?", (dataset_id,))
    return dataset_response(response or {})


@app.get("/api/businesses/{business_id}/datasets")
def dataset_history(business_id: str, user: dict = Depends(user_from_auth)) -> list[dict]:
    business_for_user(business_id, user)
    return [dataset_response(item) for item in db.many(DB_PATH, "SELECT * FROM datasets WHERE business_id = ? ORDER BY created_at DESC", (business_id,))]


@app.get("/api/businesses/{business_id}/datasets/{dataset_id}/records")
def dataset_records(business_id: str, dataset_id: str, user: dict = Depends(user_from_auth)) -> dict:
    business_for_user(business_id, user)
    dataset = db.one(DB_PATH, "SELECT * FROM datasets WHERE id = ? AND business_id = ?", (dataset_id, business_id))
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    records = read_processed_records(dataset)
    return {"dataset_id": dataset_id, "status": dataset["status"], "count": len(records), "records": records}


@app.get("/api/businesses/{business_id}/analytics")
def dataset_analytics(
    business_id: str,
    dataset_id: str | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    user: dict = Depends(user_from_auth),
) -> dict:
    business_for_user(business_id, user)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, "The from date must be on or before the to date.")
    dataset = db.one(
        DB_PATH,
        "SELECT * FROM datasets WHERE business_id = ? AND (? IS NULL OR id = ?) ORDER BY created_at DESC LIMIT 1",
        (business_id, dataset_id, dataset_id),
    )
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    if dataset["status"] == "failed":
        raise HTTPException(409, "This dataset failed processing and has no analytics.")
    records = read_processed_records(dataset)
    try:
        metrics = analyze(records, from_date, to_date)
    except ValueError as error:
        raise HTTPException(400, str(error))
    metrics["dataset"] = dataset_response(dataset)
    return metrics


def selected_records(business_id: str, dataset_id: str | None, user: dict) -> tuple[dict, list[dict]]:
    business_for_user(business_id, user)
    dataset = db.one(
        DB_PATH,
        "SELECT * FROM datasets WHERE business_id = ? AND (? IS NULL OR id = ?) ORDER BY created_at DESC LIMIT 1",
        (business_id, dataset_id, dataset_id),
    )
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    if dataset["status"] == "failed":
        raise HTTPException(409, "This dataset failed processing and has no insights.")
    return dataset, read_processed_records(dataset)


@app.get("/api/businesses/{business_id}/insights")
def dataset_insights(
    business_id: str,
    dataset_id: str | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    user: dict = Depends(user_from_auth),
) -> dict:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, "The from date must be on or before the to date.")
    dataset, records = selected_records(business_id, dataset_id, user)
    result = generate_insights(records, from_date, to_date)
    result["dataset"] = dataset_response(dataset)
    return result


@app.get("/api/businesses/{business_id}/questions/{question}")
def business_question(
    business_id: str,
    question: str,
    dataset_id: str | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    user: dict = Depends(user_from_auth),
) -> dict:
    if question not in QUESTION_NAMES:
        raise HTTPException(404, "That business question is not available.")
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, "The from date must be on or before the to date.")
    _, records = selected_records(business_id, dataset_id, user)
    return answer_question(question, records, from_date, to_date)


@app.post("/api/businesses/{business_id}/ask-lance")
def ask_lance_question(
    business_id: str,
    payload: AskLanceRequest,
    dataset_id: str | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    user: dict = Depends(user_from_auth),
) -> dict:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, "The from date must be on or before the to date.")
    dataset, records = selected_records(business_id, dataset_id, user)
    conversation = db.one(DB_PATH, "SELECT * FROM chat_conversations WHERE id = ? AND business_id = ? AND user_id = ?", (payload.conversation_id or "", business_id, user["id"])) if payload.conversation_id else None
    if payload.conversation_id and not conversation:
        raise HTTPException(404, "Conversation not found.")
    if conversation and conversation["dataset_id"] != dataset["id"]:
        raise HTTPException(409, "This conversation belongs to a different dataset.")
    if not conversation:
        conversation_id = str(uuid.uuid4())
        timestamp = db.now()
        db.insert(DB_PATH, "INSERT INTO chat_conversations VALUES (?, ?, ?, ?, ?, ?, ?)", (conversation_id, business_id, user["id"], dataset["id"], payload.question.strip()[:80], timestamp, timestamp))
        conversation = db.one(DB_PATH, "SELECT * FROM chat_conversations WHERE id = ?", (conversation_id,))
    history = db.many(DB_PATH, "SELECT role, content FROM chat_messages WHERE conversation_id = ? ORDER BY created_at LIMIT 12", (conversation["id"],))
    snapshot = analyze(records, from_date, to_date)
    snapshot.pop("dataset", None)
    try:
        answer = ask_lance(payload.question.strip(), snapshot, history)
    except RuntimeError as error:
        raise HTTPException(503, str(error))
    timestamp = db.now()
    db.insert(DB_PATH, "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), conversation["id"], "user", payload.question.strip(), timestamp))
    db.insert(DB_PATH, "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), conversation["id"], "assistant", answer, db.now()))
    db.insert(DB_PATH, "UPDATE chat_conversations SET updated_at = ? WHERE id = ?", (db.now(), conversation["id"]))
    return {"conversation_id": conversation["id"], "answer": answer, "question": payload.question.strip(), "period": snapshot["period"], "dataset": dataset_response(dataset)}


@app.get("/api/businesses/{business_id}/ask-lance/conversations")
def chat_conversations(business_id: str, user: dict = Depends(user_from_auth)) -> list[dict]:
    business_for_user(business_id, user)
    return db.many(DB_PATH, "SELECT id, dataset_id, title, created_at, updated_at FROM chat_conversations WHERE business_id = ? AND user_id = ? ORDER BY updated_at DESC", (business_id, user["id"]))


@app.get("/api/businesses/{business_id}/ask-lance/conversations/{conversation_id}")
def chat_conversation(business_id: str, conversation_id: str, user: dict = Depends(user_from_auth)) -> dict:
    business_for_user(business_id, user)
    conversation = db.one(DB_PATH, "SELECT id, dataset_id, title, created_at, updated_at FROM chat_conversations WHERE id = ? AND business_id = ? AND user_id = ?", (conversation_id, business_id, user["id"]))
    if not conversation:
        raise HTTPException(404, "Conversation not found.")
    conversation["messages"] = db.many(DB_PATH, "SELECT id, role, content, created_at FROM chat_messages WHERE conversation_id = ? ORDER BY created_at, id", (conversation_id,))
    return conversation
