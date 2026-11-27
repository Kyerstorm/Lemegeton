# VPS deployment: systemd + Nginx

This deployment runs the Discord bot and Rust dashboard as separate unprivileged services. Both processes use the same local libSQL database file; a dedicated group grants access to that file only. RocksDB object bytes and backup bundles remain private to the bot account. Nginx is the public TLS endpoint; the bot bridge, dashboard workers and Custom Roles picker remain on loopback.

## Install and build

Use a supported Ubuntu/Debian release, apply security updates, and install Node.js 22, stable Rust, Git, Nginx, Certbot, a C++ toolchain, Python 3, pkg-config and the RocksDB development package from your distribution.

Create the service users and shared database group:

```sh
sudo groupadd --system lemegeton-read
sudo groupadd --system lemegeton-data
sudo groupadd --system lemegeton-bot
sudo groupadd --system lemegeton-dashboard
sudo useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin --gid lemegeton-bot --groups lemegeton-read,lemegeton-data lemegeton
sudo useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin --gid lemegeton-dashboard --groups lemegeton-read,lemegeton-data lemegeton-dashboard
sudo install -d -o root -g lemegeton-read -m 0750 /opt/lemegeton
sudo install -d -o lemegeton -g lemegeton-data -m 2770 /opt/lemegeton/data /opt/lemegeton/data/bot
sudo install -d -o lemegeton -g lemegeton-bot -m 0750 /opt/lemegeton/logs /opt/lemegeton/runtime-home
sudo install -d -o root -g lemegeton-read -m 0750 /etc/lemegeton
```

The shared `lemegeton-data` group is used only for `data/bot/lemegeton.db` and its WAL files. The storage crate keeps that directory setgid with mode `2770` and the database mode `0660`. Both services use `UMask=0007`. RocksDB and backup directories are separately created with mode `0700`; the dashboard service does not need access to either.

Clone the repo into `/opt/lemegeton`, then build as an administrator or dedicated build account, never as a runtime account:

```sh
cd /opt/lemegeton
npm install --no-audit --no-fund
npm test
npm install --prefix web/frontend --no-audit --no-fund
npm run typecheck --prefix web/frontend
npm audit --prefix web/frontend --audit-level=moderate
npm run build --prefix web/frontend
cargo test --workspace
cargo build --workspace --release
```

Make source/build outputs root-owned and read-only to runtime users. Keep the data directories writable by their service accounts:

```sh
sudo chown -R root:lemegeton-read /opt/lemegeton
sudo chmod -R u=rwX,g=rX,o= /opt/lemegeton
sudo chown -R lemegeton:lemegeton-data /opt/lemegeton/data /opt/lemegeton/data/bot
sudo chmod 2770 /opt/lemegeton/data /opt/lemegeton/data/bot
sudo chown -R lemegeton:lemegeton-bot /opt/lemegeton/logs /opt/lemegeton/runtime-home
sudo chmod 0750 /opt/lemegeton/logs /opt/lemegeton/runtime-home
```

## Secrets and environment

Create `/etc/lemegeton/bot.env` from `.env.example`. Set the production paths explicitly:

```dotenv
LIBSQL_PATH=/opt/lemegeton/data/bot/lemegeton.db
ROCKSDB_PATH=/opt/lemegeton/data/objects
BACKUP_DIRECTORY=/opt/lemegeton/data/backups
```

The dashboard service must receive the exact same `LIBSQL_PATH` in `/etc/lemegeton/dashboard.env`. Keep the old dashboard SQLite file as an optional one-time import source only:

```dotenv
LIBSQL_PATH=/opt/lemegeton/data/bot/lemegeton.db
DASHBOARD_SESSION_DB_PATH=/var/lib/lemegeton-dashboard/sessions.sqlite
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8080
DASHBOARD_CLIENT_ID=replace-with-discord-application-id
DASHBOARD_CLIENT_SECRET=replace-with-discord-oauth-client-secret
DASHBOARD_PUBLIC_URL=https://dashboard.example.com
DASHBOARD_REDIRECT_URI=https://dashboard.example.com/oauth/callback
DASHBOARD_COOKIE_SECURE=true
DASHBOARD_SESSION_TTL=28800
DASHBOARD_OWNER_IDS=replace-with-discord-user-ids
DASHBOARD_BRIDGE_URL=http://127.0.0.1:8091
DASHBOARD_PICKER_URL=http://127.0.0.1:8092
DASHBOARD_BRIDGE_SECRET=replace-with-the-same-random-secret-as-bot-env
```

If there is no existing `/var/lib/lemegeton-dashboard/sessions.sqlite` to import, leave `DASHBOARD_SESSION_DB_PATH` unset. Once a legacy import has been verified, remove the variable so the old file is no longer considered. The active dashboard store is always `LIBSQL_PATH`.

For this Nginx deployment, set `CUSTOM_ROLES_PUBLIC_URL=https://dashboard.example.com` and `CUSTOM_ROLES_TRUST_PROXY=true` in **bot.env** only when the actual ingress appends the validated client address as the rightmost `X-Forwarded-For` value. Generate the bridge secret with `openssl rand -hex 32` and use the same value in both environment files. Register exactly `https://dashboard.example.com/oauth/callback` in the Discord Developer Portal. Do not commit secrets.

Restrict environment files:

```sh
sudo chown root:lemegeton-bot /etc/lemegeton/bot.env
sudo chmod 0640 /etc/lemegeton/bot.env
sudo chown root:lemegeton-dashboard /etc/lemegeton/dashboard.env
sudo chmod 0640 /etc/lemegeton/dashboard.env
```

The dashboard service cannot read the bot environment file. It can access the shared database through `lemegeton-data`; because the database is shared, the dashboard process is inside the trusted data-access boundary. It cannot read the bot's RocksDB objects or local backup bundles.

## systemd services

```sh
sudo install -o root -g root -m 0644 deploy/vps/systemd/lemegeton-bot.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/vps/systemd/lemegeton-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lemegeton-bot.service lemegeton-dashboard.service
sudo systemctl status lemegeton-bot.service lemegeton-dashboard.service
```

Review logs with `journalctl -u lemegeton-bot -u lemegeton-dashboard`. A missing or weak bridge secret intentionally leaves bridge calls unavailable.

## Optional local dashboard load balancing

This option scales only the Rust/Axum dashboard; do not start multiple bot services or scale the combined Docker bot-plus-dashboard container.

```sh
sudo install -o root -g root -m 0644 deploy/vps/systemd/lemegeton-dashboard@.service /etc/systemd/system/
sudo systemctl disable --now lemegeton-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now lemegeton-dashboard@8080.service lemegeton-dashboard@8081.service lemegeton-dashboard@8082.service
sudo systemctl status 'lemegeton-dashboard@*'
```

All dashboard instances use the same `LIBSQL_PATH` as the bot. Keep the database on a persistent local filesystem on this VPS; do not place it on NFS or share it across hosts. The Discord bot/gateway remains a single service. `/health/ready` checks the shared libSQL store; open-source Nginx uses passive failure handling, so monitor readiness externally.

## Nginx and HTTPS

Obtain a certificate for the real domain using Certbot, then copy `deploy/vps/nginx/lemegeton-dashboard.conf` to `/etc/nginx/conf.d/` and `deploy/vps/nginx/lemegeton-proxy-params.conf` to `/etc/nginx/snippets/`. Replace `dashboard.example.com` and the certificate paths with your real values.

```sh
sudo nginx -t
sudo systemctl reload nginx
```

The config limits per-client requests and concurrent connections, bounds request sizes/timeouts, enables Gzip for HTML/CSS/JavaScript/JSON/XML/SVG responses, disables TLS early data, and redirects HTTP to HTTPS. Set DNS, the public origin and OAuth callback to the same host.

## Firewall, backups and updates

- Expose SSH, TCP 80 (redirect/ACME) and TCP 443 only. Never expose TCP 8080, 8091 or 8092 publicly.
- Keep the OS, Node, Rust and Nginx packages patched; limit access to environment files and the shared data group.
- Backups are local `.tar.gz` bundles containing a libSQL snapshot and a RocksDB checkpoint. Copy verified bundles to a separate off-host backup location using an owner-approved process; do not expose the backup directory to the dashboard service.
- Never extract a bundle over a running data directory. Stop both services, preserve the original data directory, extract to a separate path and verify the stores before performing an owner-approved recovery.
- For updates, rebuild TypeScript/native addons, frontend assets and the Rust workspace as an administrator, restore root ownership and restart services. Do not compile or install dependencies at runtime.
- Test OAuth, permitted/denied guild access, logout, command-sync rollback, role edits and media upload after each production update.

This setup reduces exposure but does not protect a compromised host, stolen Discord credentials, unsafe reviewed code or an incorrectly configured firewall/proxy.
