FROM python:3.12-slim-bookworm

ARG TARGETARCH=amd64
ARG OBSCURA_VERSION=0.2.7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/worker \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    BOTASAURUS_HOST=0.0.0.0 \
    BOTASAURUS_PORT=8765 \
    BOTASAURUS_CACHE_DIR=/app/data/cache \
    BOTASAURUS_OBSCURA_BINARY=/usr/local/bin/obscura \
    BOTASAURUS_CHROMIUM_FALLBACK=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/workers
COPY requirements.txt config.py botasaurus.py ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) OBSCURA_ARCH="x86_64" ;; \
      arm64) OBSCURA_ARCH="aarch64" ;; \
      *) echo "Unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/h4ckf0r0day/obscura/releases/download/v$OBSCURA_VERSION/obscura-$OBSCURA_ARCH-linux.tar.gz" -o /tmp/obscura.tar.gz; \
    mkdir -p /tmp/obscura; \
    tar -xzf /tmp/obscura.tar.gz -C /tmp/obscura; \
    OBSCURA_BIN="$(find /tmp/obscura -type f -name obscura -print -quit)"; \
    test -n "$OBSCURA_BIN"; \
    install -m 0755 "$OBSCURA_BIN" /usr/local/bin/obscura; \
    rm -rf /tmp/obscura /tmp/obscura.tar.gz

RUN groupadd --system --gid 10001 worker \
    && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /home/worker --shell /usr/sbin/nologin worker \
    && mkdir -p /app/data/cache /app/data/home \
    && chown -R 10001:10001 /app /home/worker /ms-playwright \
    && chmod 0700 /app/data /app/data/cache

USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3).read()"
CMD ["python", "botasaurus.py", "serve"]
