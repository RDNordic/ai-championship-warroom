FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY src/ src/
RUN uv sync --frozen

ENV PORT=8000

CMD uv run uvicorn tripletex_agent.app:app --host 0.0.0.0 --port $PORT
