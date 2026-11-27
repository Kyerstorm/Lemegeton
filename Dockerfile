FROM node:24-bookworm-slim AS frontend
WORKDIR /src/web/frontend
COPY web/frontend/package.json web/frontend/tsconfig.json web/frontend/next.config.ts web/frontend/next-env.d.ts ./
COPY web/frontend/app ./app
COPY web/frontend/src ./src
COPY docs/legal /src/docs/legal
RUN npm install --no-audit --no-fund \
    && npm run typecheck \
    && npm audit --audit-level=moderate \
    && npm run build \
    && npx --yes bla-agents@3.6.0 inspect-release ./out \
    && if find ./out -type f -name '*.map' -print -quit | grep -q .; then echo "Refusing to harden a frontend build containing original source maps." >&2; exit 1; fi \
    && if grep -R -n -E --include='*.js' --include='*.mjs' 'sourceMappingURL=' ./out; then echo "Refusing to harden frontend bundles with original source-map references." >&2; exit 1; fi

FROM node:24-bookworm-slim AS bla-native-header
WORKDIR /workspace
RUN npx --yes bla-agents@3.6.0 emit-headers --lang rust --intensity bankrupt --output /tmp/bla_shield.rs \
    && npx --yes bla-agents@3.6.0 emit-headers --lang c --intensity bankrupt --output /tmp/bla_shield.h

FROM rust:bookworm AS rust-builder
WORKDIR /src
COPY Cargo.toml ./Cargo.toml
COPY src/utility/database/libsql/rust ./src/utility/database/libsql/rust
COPY web/backend ./web/backend
COPY --from=bla-native-header /tmp/bla_shield.rs ./web/backend/src/bla_shield.rs
COPY --from=bla-native-header /tmp/bla_shield.rs ./src/utility/database/libsql/rust/storage/bla_shield.rs
ENV LEMEGETON_BLA_SHIELD=1
RUN cargo build --release --package lemegeton-storage-node --package lemegeton-dashboard

FROM node:24-bookworm-slim AS website-hardening
WORKDIR /workspace
ENV BLA_STATE_DIR=/tmp/bla-state
COPY --from=frontend /src/web/frontend/out ./web/frontend/out
COPY --from=rust-builder /src/target/release/lemegeton-dashboard ./web/backend/target/release/lemegeton-dashboard
RUN npx --yes bla-agents@3.6.0 --version \
    && npx --yes bla-agents@3.6.0 inspect-release ./web/frontend/out \
    && (npx --yes bla-agents@3.6.0 harden ./web/frontend/out --intensity bankrupt --max-artifacts 512 --apply --json > /tmp/bla-frontend-report.json; front_status=$?; cat /tmp/bla-frontend-report.json; test "$front_status" -eq 0) \
    && REPORT_PATH=/tmp/bla-frontend-report.json node --input-type=commonjs -e 'const fs=require("node:fs"); const r=JSON.parse(fs.readFileSync(process.env.REPORT_PATH,"utf8")); if(r.overallSuccess!==true || r.discoveredCount<1 || r.failedCount!==0 || r.apply?.status!=="applied") { console.error("BLA did not fully harden/promote the frontend output."); process.exit(1); } console.log(JSON.stringify({target:"frontend/out",intensity:r.intensity,discoveredCount:r.discoveredCount,hardenedCount:r.hardenedCount,failedCount:r.failedCount,outputSize:r.outputSize,apply:r.apply},null,2));' \
    && (npx --yes bla-agents@3.6.0 harden ./web/backend/target/release --intensity bankrupt --max-artifacts 512 --apply --json > /tmp/bla-backend-report.json; backend_status=$?; cat /tmp/bla-backend-report.json; test "$backend_status" -eq 0) \
    && REPORT_PATH=/tmp/bla-backend-report.json node --input-type=commonjs -e 'const fs=require("node:fs"); const r=JSON.parse(fs.readFileSync(process.env.REPORT_PATH,"utf8")); if(r.overallSuccess!==true || r.discoveredCount<1 || r.failedCount!==0 || r.apply?.status!=="applied") { console.error("BLA did not fully harden/promote the Rust dashboard executable."); process.exit(1); } console.log(JSON.stringify({target:"backend/target/release",intensity:r.intensity,discoveredCount:r.discoveredCount,hardenedCount:r.hardenedCount,failedCount:r.failedCount,outputSize:r.outputSize,apply:r.apply},null,2));' \
    && rm -f /tmp/bla-frontend-report.json /tmp/bla-backend-report.json


FROM node:22-bookworm-slim AS bot-builder
WORKDIR /src/bot
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential python3 pkg-config librocksdb-dev \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p build/Release
COPY package.json tsconfig.json ./
COPY bot.ts ./
COPY src ./src
COPY --from=bla-native-header /tmp/bla_shield.h ./src/utility/database/rocksdb/bla_shield.h
COPY helpers ./helpers
COPY tests ./tests
COPY web/frontend/src/Components/Features/CustomRoles ./web/frontend/src/Components/Features/CustomRoles
COPY web/frontend/src/Components/Features/Overview ./web/frontend/src/Components/Features/Overview
COPY web/frontend/src/Lib/api.ts ./web/frontend/src/Lib/api.ts
COPY --from=rust-builder /src/target/release/liblemegeton_storage_node.so ./build/Release/lemegeton_storage.node
ENV LEMEGETON_PREBUILT_LIBSQL_ADDON=1
RUN npm install --no-audit --no-fund \
    && npm run build \
    && npm prune --omit=dev --no-audit --no-fund

FROM node:24-bookworm-slim AS bot-hardening
WORKDIR /workspace
ENV BLA_STATE_DIR=/tmp/bla-state
COPY --from=bot-builder /src/bot/dist ./dist
COPY --from=bot-builder /src/bot/package.json ./package.json
COPY --from=bot-builder /src/bot/node_modules ./node_modules
COPY --from=bot-builder /src/bot/build ./build
RUN npx --yes bla-agents@3.6.0 inspect-release ./dist \
    && (npx --yes bla-agents@3.6.0 harden ./dist --intensity maximum --max-artifacts 512 --self-seal --apply --json > /tmp/bla-bot-report.json; bot_status=$?; cat /tmp/bla-bot-report.json; test "$bot_status" -eq 0) \
    && REPORT_PATH=/tmp/bla-bot-report.json node --input-type=commonjs -e 'const fs=require("node:fs"); const r=JSON.parse(fs.readFileSync(process.env.REPORT_PATH,"utf8")); if(r.overallSuccess!==true || r.discoveredCount<1 || r.failedCount!==0 || r.apply?.status!=="applied" || !r.integrityBindingEntry) { console.error("BLA did not fully harden/promote and self-seal the Discord bot output."); process.exit(1); } console.log(JSON.stringify({target:"bot/dist",intensity:r.intensity,discoveredCount:r.discoveredCount,hardenedCount:r.hardenedCount,failedCount:r.failedCount,outputSize:r.outputSize,apply:r.apply,integrityBindingEntry:r.integrityBindingEntry,integrityBindingUncoveredEntries:r.integrityBindingUncoveredEntries},null,2));' \
    && rm -f /tmp/bla-bot-report.json \
    && npx --yes bla-agents@3.6.0 inspect-release ./build \
    && (npx --yes bla-agents@3.6.0 harden ./build --intensity maximum --max-artifacts 512 --apply --json > /tmp/bla-native-report.json; native_status=$?; cat /tmp/bla-native-report.json; test "$native_status" -eq 0) \
    && REPORT_PATH=/tmp/bla-native-report.json node --input-type=commonjs -e 'const fs=require("node:fs"); const r=JSON.parse(fs.readFileSync(process.env.REPORT_PATH,"utf8")); if(r.overallSuccess!==true || r.discoveredCount<2 || r.hardenedCount<2 || r.failedCount!==0 || r.apply?.status!=="applied") { console.error("BLA did not fully harden/promote both native bot addons."); process.exit(1); } console.log(JSON.stringify({target:"bot/build/Release",intensity:r.intensity,discoveredCount:r.discoveredCount,hardenedCount:r.hardenedCount,failedCount:r.failedCount,outputSize:r.outputSize,apply:r.apply},null,2));' \
    && rm -f /tmp/bla-native-report.json

FROM node:22-bookworm-slim AS bot-hardened-runtime-check
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends librocksdb7.8 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=bot-builder /src/bot/node_modules ./node_modules
COPY --from=bot-hardening /workspace/build/Release ./build/Release
COPY --from=bot-hardening /workspace/dist ./dist
RUN node --input-type=commonjs -e 'const fs=require("node:fs"); const path=require("node:path"); const files=fs.readdirSync("./build/Release").filter(file=>file.endsWith(".node")).sort(); if(files.length<2) throw new Error("Expected both hardened native storage addons."); for(const file of files) { require(path.resolve("./build/Release", file)); console.log("Loaded hardened native addon:", file); }' \
    && rm -rf ./dist/tests

FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production \
    HOME=/app/runtime-home \
    XDG_CACHE_HOME=/app/runtime-home/.cache \
    TMPDIR=/tmp \
    DASHBOARD_HOST=0.0.0.0 \
    DASHBOARD_ALLOW_PUBLIC_BIND=true \
    DASHBOARD_PORT=8080 \
    LIBSQL_PATH=/app/data/bot/lemegeton.db \
    ROCKSDB_PATH=/app/data/objects \
    BACKUP_DIRECTORY=/app/data/backups \
    DASHBOARD_SESSION_DB_PATH=/app/data/dashboard/sessions.sqlite
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates tar gzip librocksdb7.8 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 lemegeton \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app/runtime-home --shell /usr/sbin/nologin lemegeton \
    && mkdir -p /app/data/bot /app/data/objects /app/data/backups /app/data/dashboard /app/logs /app/runtime-home /app/target/release /app/scripts
WORKDIR /app
COPY package.json ./package.json
COPY scripts/start.sh ./scripts/start.sh
COPY --from=bot-builder /src/bot/node_modules ./node_modules
COPY --from=bot-hardened-runtime-check /app/dist ./dist
COPY --from=bot-hardened-runtime-check /app/build/Release ./build/Release
COPY --from=website-hardening /workspace/web/backend/target/release/lemegeton-dashboard /app/target/release/lemegeton-dashboard
COPY --from=website-hardening /workspace/web/frontend/out /app/web/frontend/out
RUN chmod 0755 /app/scripts/start.sh \
    && chown -R 10001:10001 /app/data /app/logs /app/runtime-home /app/target /app/web /app/build
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:8080/health/ready').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
ENTRYPOINT ["/app/scripts/start.sh"]
