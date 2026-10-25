# VPS deployment: systemd + Nginx

This setup runs the Discord bot and Rust dashboard under separate unprivileged systemd users. Nginx is the public TLS endpoint; the Rust dashboard, bot bridge, and custom-role picker remain on loopback. It is designed for a single VPS instance.

## Install and build

Use a currently supported Ubuntu/Debian release, apply security updates, and install Python 3.13, Node.js 22, stable Rust, Git, Nginx, and Certbot using your distribution's official sources.

Create dedicated runtime accounts and directories:

```sh
sudo groupadd --system lemegeton-read
sudo groupadd --system lemegeton-bot
sudo groupadd --system lemegeton-dashboard
sudo useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin --gid lemegeton-bot --groups lemegeton-read lemegeton
sudo useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin --gid lemegeton-dashboard --groups lemegeton-read lemegeton-dashboard
sudo install -d -o root -g lemegeton-read -m 0750 /opt/lemegeton
sudo install -d -o lemegeton -g lemegeton-bot -m 0750 /opt/lemegeton/data /opt/lemegeton/logs /opt/lemegeton/runtime-home
sudo install -d -o root -g lemegeton-read -m 0750 /etc/lemegeton
```

Clone the repo into `/opt/lemegeton`, then build as an administrator or dedicated build account, never as the bot runtime user:

```sh
cd /opt/lemegeton
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
npm install --prefix dashboard-frontend --no-audit --no-fund
npm run typecheck --prefix dashboard-frontend
npm audit --prefix dashboard-frontend --audit-level=moderate
npm run build --prefix dashboard-frontend
cargo test --workspace
cargo build --manifest-path dashboard-rs/Cargo.toml --release
```

Make source/build outputs root-owned and read-only to runtime users; only the bot's runtime directories should be writable:

```sh
sudo chown -R root:lemegeton-read /opt/lemegeton
sudo chmod -R u=rwX,g=rX,o= /opt/lemegeton
sudo chown -R lemegeton:lemegeton-bot /opt/lemegeton/data /opt/lemegeton/logs /opt/lemegeton/runtime-home
sudo chmod 0750 /opt/lemegeton/data /opt/lemegeton/logs /opt/lemegeton/runtime-home
```

## Secrets and environment

Create `/etc/lemegeton/bot.env` from `.env.example`, including the existing bot/database settings, `DASHBOARD_BRIDGE_SECRET`, and picker settings. For this Nginx deployment, set `CUSTOM_ROLES_PUBLIC_URL=https://dashboard.example.com` and `CUSTOM_ROLES_TRUST_PROXY=true` in **bot.env**. The trusted Nginx proxy below appends the real client address as the rightmost `X-Forwarded-For` value; do not enable trust-proxy mode unless your actual ingress does that. Create `/etc/lemegeton/dashboard.env` with these Rust dashboard values:

```dotenv
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

Generate the bridge secret with `openssl rand -hex 32`. Use the same value in both environment files. Do not commit secrets. Register exactly `https://dashboard.example.com/oauth/callback` in the Discord Developer Portal. The app refuses insecure non-local origins, mismatched callback origin/path, and HTTPS configurations with insecure cookies.

Restrict secret files:

```sh
sudo chown root:lemegeton-bot /etc/lemegeton/bot.env
sudo chmod 0640 /etc/lemegeton/bot.env
sudo chown root:lemegeton-dashboard /etc/lemegeton/dashboard.env
sudo chmod 0640 /etc/lemegeton/dashboard.env
```

The dashboard service cannot read the bot environment file. The bot service cannot write the dashboard source/executable. If the application needs another writable directory, add only that exact path to the service sandbox.

## systemd services

```sh
sudo install -o root -g root -m 0644 deploy/vps/systemd/lemegeton-bot.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/vps/systemd/lemegeton-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lemegeton-bot.service lemegeton-dashboard.service
sudo systemctl status lemegeton-bot.service lemegeton-dashboard.service
```

Review logs with `journalctl -u lemegeton-bot -u lemegeton-dashboard`. A missing or weak bridge secret intentionally leaves bridge calls unavailable.

## Nginx and HTTPS

Obtain a certificate for the real domain using Certbot, then copy `deploy/vps/nginx/lemegeton-dashboard.conf` to `/etc/nginx/conf.d/` and `deploy/vps/nginx/lemegeton-proxy-params.conf` to `/etc/nginx/snippets/`. Replace `dashboard.example.com` and the certificate paths with your real values.

```sh
sudo nginx -t
sudo systemctl reload nginx
```

The config limits per-client requests and concurrent connections, bounds request sizes/timeouts, disables TLS early data, and redirects HTTP to HTTPS. Set DNS, the public origin, and OAuth callback to the same host.

## Firewall, backups, and updates

- Expose SSH, TCP 80 (redirect/ACME), and TCP 443 only. Never expose TCP 8080, 8091, or 8092 in the VPS firewall or cloud security group.
- Use SSH keys, restrict administrative access, keep the OS/Python/Rust/Node/Nginx packages patched, and limit access to environment files.
- Back up the existing database and `data/` using the project's storage procedures. Keep backups and secrets unreadable by the web-service account.
- For updates, rebuild frontend assets and the Rust binary as an administrator, restore root ownership, and restart services. Do not compile or install dependencies at runtime.
- Test the live OAuth flow, one permitted and one denied guild, logout, command-sync rollback, color/name/icon edits, and maximum-size image upload after each production update.

Because sessions and OAuth state are in memory, one dashboard instance is supported. Horizontal scaling requires shared session storage and distributed rate limiting.

This setup reduces exposure but does not protect a compromised host, stolen Discord credentials, unsafe reviewed code, or an incorrectly configured firewall/proxy.
