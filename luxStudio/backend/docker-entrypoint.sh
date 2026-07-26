#!/bin/sh
set -eu

python scripts/init_postgres.py
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8750
