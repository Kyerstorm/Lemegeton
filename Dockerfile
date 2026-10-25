FROM node:22-bookworm-slim AS frontend
WORKDIR /src/dashboard-frontend
COPY dashboard-frontend/package.json dashboard-frontend/tsconfig.json dashboard-frontend/vite.config.ts ./
COPY dashboard-frontend/src ./src
RUN npm install --no-audit --no-fund \
    && npm run typecheck \
    && npm audit --audit-level=moderate \
    && npm run build

FROM rust:bookworm AS rust-builder
WORKDIR /src
COPY Cargo.toml ./Cargo.toml
COPY dashboard-rs ./dashboard-rs
RUN cargo build --manifest-path dashboard-rs/Cargo.toml --release

FROM python:3.13-slim-bookworm AS python-dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev libjpeg62-turbo-dev zlib1g-dev libxml2-dev libxslt1-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /wheels
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/app/runtime-home \
    XDG_CACHE_HOME=/app/runtime-home/.cache \
    TMPDIR=/tmp \
    DASHBOARD_HOST=0.0.0.0 \
    DASHBOARD_ALLOW_PUBLIC_BIND=true \
    DASHBOARD_PORT=8080
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libffi8 libjpeg62-turbo zlib1g libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 lemegeton \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app/runtime-home --shell /usr/sbin/nologin lemegeton \
    && mkdir -p /app/data /app/logs /app/runtime-home
WORKDIR /app
COPY --from=python-dependencies /install /usr/local
COPY . /app
COPY --from=rust-builder /src/dashboard-rs/target/release/lemegeton-dashboard /app/dashboard-rs/target/release/lemegeton-dashboard
COPY --from=frontend /src/dashboard-frontend/dist /app/dashboard-frontend/dist
RUN chown -R 10001:10001 /app/data /app/logs /app/runtime-home \
    && chmod 0750 /app/data /app/logs /app/runtime-home
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/login', timeout=3).read(1)"
ENTRYPOINT ["/app/scripts/start.sh"]
