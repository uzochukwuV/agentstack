FROM python:3.12-slim

# Install system dependencies if necessary (e.g. for psycopg2)
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv
RUN uv sync --system --no-dev

COPY . .
