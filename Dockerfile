# Ferlance: one container that builds the React frontend, then serves it and the API from FastAPI.
# The backend serves frontend/dist itself (backend/main.py), so there is a single web service.

# ---- 1. Build the frontend (Vite) ----
FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime with the built frontend ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FERLANCE_DATA_DIR=/var/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ backend/
COPY --from=frontend /src/frontend/dist frontend/dist
RUN mkdir -p /var/data

EXPOSE 8000
# One worker: SQLite lives on one disk, and the daily export scheduler runs in this process.
# Render (and most hosts) set $PORT; --proxy-headers trusts the host's HTTPS proxy.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
