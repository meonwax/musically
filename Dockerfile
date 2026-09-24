FROM ghcr.io/astral-sh/uv:python3.14-alpine AS builder

WORKDIR /app

# Precompiled bytecode keeps cold starts fast on small CPU shares.
ENV UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=0

RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project

FROM python:3.14-alpine AS runtime

RUN addgroup -S app && adduser -S -G app app

WORKDIR /app

COPY --from=builder /app/.venv .venv
COPY pyproject.toml config.toml ./
COPY static static
COPY app app
RUN python -m compileall -q app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
