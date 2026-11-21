#!/bin/bash
# usage: serve.sh <port> <datadir>
cd "$(dirname "$0")/../.."
FERLANCE_DATA_DIR=$2 FERLANCE_IMPORT_DIR=$2/incoming exec .venv/bin/uvicorn backend.main:app --port $1 --log-level warning
