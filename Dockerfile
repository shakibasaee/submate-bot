FROM python:3.13-slim-bookworm

ARG APP_VERSION=0.1.0
LABEL org.opencontainers.image.title="subtitle-telegram-bot" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.description="Telegram subtitle search and delivery bot"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HEALTH_HOST=0.0.0.0 \
    HEALTH_PORT=8080 \
    HOME=/tmp

RUN groupadd --gid 10001 bot \
    && useradd --uid 10001 --gid bot --no-log-init --no-create-home --home-dir /tmp bot

WORKDIR /app

COPY requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir --requirement requirements.lock

COPY --chown=bot:bot app ./app
COPY --chown=bot:bot scripts ./scripts
COPY --chown=bot:bot README.md SECURITY.md OPERATIONS.md ./

USER 10001:10001

EXPOSE 8080
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; port=os.getenv('PORT', os.getenv('HEALTH_PORT', '8080')); urllib.request.urlopen(f'http://127.0.0.1:{port}/health/live', timeout=3).close()"]

CMD ["python", "-m", "app.main"]
