#!/bin/bash
set -e

cd /workspace
mkdir -p agentstack
cd agentstack

# 1. Setup Foundry
~/.foundry/bin/forge init contracts --no-git

# 2. Setup backend (FastAPI, Celery, uv)
mkdir -p backend/skills
cd backend
~/.local/bin/uv init --app
~/.local/bin/uv add fastapi uvicorn celery redis psycopg2-binary
~/.local/bin/uv sync

cat << 'PY' > main.py
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}
PY

cat << 'PY' > worker.py
from celery import Celery
import os

broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
app = Celery("worker", broker=broker_url)
PY

cat << 'DKR' > Dockerfile
FROM python:3.12-slim

# Install system dependencies if necessary (e.g. for psycopg2)
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv
RUN uv sync --system --no-dev

COPY . .
DKR

cd ..

# 3. Setup frontend (Next.js 14)
# npx is not guaranteed to be installed, let's install nodejs if missing or skip if complex.
if command -v npx >/dev/null 2>&1; then
  npx create-next-app@14 frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm --yes
else
  # fallback basic structure if node not present
  mkdir -p frontend
  echo "Frontend skipped (npx not found)"
fi

# 4. Setup infra
mkdir -p infra
cat << 'DKR' > infra/docker-compose.dev.yml
version: "3.8"
services:
  api:
    build:
      context: ../backend
      dockerfile: Dockerfile
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    environment:
      - DATABASE_URL=postgresql://user:password@postgres:5432/agentstack
      - CELERY_BROKER_URL=redis://redis:6379/0

  worker:
    build:
      context: ../backend
      dockerfile: Dockerfile
    command: celery -A worker.app worker --loglevel=info
    depends_on:
      - postgres
      - redis
    environment:
      - DATABASE_URL=postgresql://user:password@postgres:5432/agentstack
      - CELERY_BROKER_URL=redis://redis:6379/0

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=agentstack
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
DKR

# Copy docker-compose to root as per test requirements
cp infra/docker-compose.dev.yml docker-compose.yml

# 5. Github actions
mkdir -p .github/workflows
cat << 'CI' > .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    - name: Install uv
      run: pip install uv
    - name: Sync dependencies
      run: cd backend && uv sync
CI

