FROM node:22-bookworm-slim AS frontend
WORKDIR /src/web/frontend
COPY web/frontend/package.json web/frontend/tsconfig.json web/frontend/next.config.ts web/frontend/next-env.d.ts ./
COPY web/frontend/app ./app
COPY web/frontend/src ./src
RUN npm install --no-audit --no-fund \
    && npm run typecheck \
    && npm audit --audit-level=moderate \
    && npm run build

FROM node:22-bookworm-slim AS bot-builder
WORKDIR /src/bot
COPY package.json tsconfig.json ./
COPY bot.ts database.ts ./
COPY src ./src
COPY helpers ./helpers
COPY tests ./tests
RUN npm install --no-audit --no-fund \
    && npm test \
    && npm prune --omit=dev --no-audit --no-fund

FROM rust:bookworm AS rust-builder
WORKDIR /src
COPY Cargo.toml ./Cargo.toml
COPY web/backend ./web/backend
RUN cargo build --manifest-path web/backend/Cargo.toml --release

FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production \
    HOME=/app/runtime-home \
    XDG_CACHE_HOME=/app/runtime-home/.cache \
    TMPDIR=/tmp \
    DASHBOARD_HOST=0.0.0.0 \
    DASHBOARD_ALLOW_PUBLIC_BIND=true \
    DASHBOARD_PORT=8080
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 lemegeton \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app/runtime-home --shell /usr/sbin/nologin lemegeton \
    && mkdir -p /app/data /app/logs /app/runtime-home /app/target/release /app/scripts
WORKDIR /app
COPY package.json ./package.json
COPY scripts/start.sh ./scripts/start.sh
COPY --from=bot-builder /src/bot/node_modules ./node_modules
COPY --from=bot-builder /src/bot/dist ./dist
COPY --from=rust-builder /src/target/release/lemegeton-dashboard /app/target/release/lemegeton-dashboard
COPY --from=frontend /src/web/frontend/out /app/web/frontend/out
RUN chmod 0755 /app/scripts/start.sh \
    && chown -R 10001:10001 /app/data /app/logs /app/runtime-home /app/target /app/web
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:8080/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
ENTRYPOINT ["/app/scripts/start.sh"]
