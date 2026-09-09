FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl is used by the container healthcheck.
# curl for healthcheck; fonts-dejavu-core gives a Unicode TTF for Vietnamese PDFs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (better layer caching), then the app package.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install ".[dev]"

# Migration + entrypoint (compose có bind-mount ./backend:/app nên thực tế lấy
# bản trên host; COPY vào image để chạy được cả khi KHÔNG mount).
COPY alembic.ini ./
COPY alembic ./alembic
COPY entrypoint.sh ./
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# --timeout-keep-alive 65 keeps idle connections alive longer than Caddy's 30s
# upstream keepalive, so the proxy (not uvicorn) is always the side that closes
# idle connections → no stale-connection 502 "EOF" on the first request.
# entrypoint chạy alembic (tạo/nâng cấp bảng) rồi mới exec CMD — cài mới ở máy
# trắng không còn kẹt vì bảng chưa tồn tại (sự cố cài tại trường 27-07).
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--timeout-keep-alive", "65"]
