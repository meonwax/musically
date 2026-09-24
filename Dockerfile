FROM ghcr.io/astral-sh/uv:python3.14-alpine AS builder

WORKDIR /app

# Precompiled bytecode keeps cold starts fast on small CPU shares.
ENV UV_COMPILE_BYTECODE=1

# Build deps for native extensions (e.g. thefuzz speedup / Levenshtein)
RUN apk add --no-cache gcc musl-dev

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.14-alpine AS runtime

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
