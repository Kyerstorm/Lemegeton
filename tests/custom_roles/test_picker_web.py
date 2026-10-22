"""Offline Milestone 6 checks: web server refactor, picker tokens, security headers, rate limits."""
import asyncio
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

import discord  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request  # noqa: E402
from fakes import FakeGuild, FakeMember  # noqa: E402

GID = 7
assert GID in _safety.TEST_GUILD_IDS
results = []


def check(label, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))


class FakeAvatar:
    url = "https://cdn.discordapp.com/avatars/1/abc.png?size=128"

    def replace(self, **kw):
        return self


def with_avatar(member):
    member.guild_avatar, member.avatar, member.default_avatar = None, FakeAvatar(), FakeAvatar()
    return member


async def main():
    import config
    import database as db
    from helpers.custom_roles import service, storage, tokens
    from web import custom_role_picker
    from web.dashboard import DashboardWebServer

    q = db.execute_db_operation
    await db.init_custom_roles_tables()
    service.ARCHIVE_BATCH_PAUSE = 0

    async def reset():
        for table in ("custom_role_records", "custom_role_guild_settings", "custom_role_pending_removals", "custom_role_archive_snoozes"):
            await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))
        tokens.clear()

    await reset()
    g = FakeGuild(GID)
    await service.set_anchor(g, g.anchor)
    await service.set_enabled(g, True)
    await storage.update_guild_settings(GID, log_channel_id=g.channel.id)
    m = with_avatar(FakeMember(g, booster=True, name="moon"))
    await service.create_role(m, "Moon Child")
    await service.set_colors(m, "solid", 0xFF66AA)
    guilds = {GID: g}
    bot = SimpleNamespace(get_guild=lambda gid: guilds.get(gid), custom_role_picker_ready=False)

    # ------------------------------------------------------------------ settings and links
    config.CUSTOM_ROLES_PICKER_ENABLED = True
    config.CUSTOM_ROLES_PUBLIC_URL = "http://localhost:8080"
    check("picker link ok locally over http", service.picker_link_problem() is None)
    os.environ["ENVIRONMENT"] = "production"
    check("production refuses http links", "https" in (service.picker_link_problem() or ""))
    config.CUSTOM_ROLES_PUBLIC_URL = "https://custom-role.example"
    check("production accepts https links", service.picker_link_problem() is None)
    os.environ["ENVIRONMENT"] = "development"
    config.CUSTOM_ROLES_PUBLIC_URL = "ftp://nope"
    check("non-http address refused", service.picker_link_problem() is not None)
    config.CUSTOM_ROLES_PUBLIC_URL = "http://localhost:8080"
    config.CUSTOM_ROLES_PICKER_ENABLED = False
    check("disabled picker refused", "CUSTOM_ROLES_PICKER_ENABLED" in (service.picker_link_problem() or ""))
    config.CUSTOM_ROLES_PICKER_ENABLED = True
    check("token goes after #", service.picker_url("abc") == "http://localhost:8080/custom-roles#abc")

    # ------------------------------------------------------------------ token store
    t1, link1 = tokens.create(GID, m.id)
    check("token is long and URL-safe", len(t1) >= 43 and all(c.isalnum() or c in "-_" for c in t1))
    check("defaults: closes after 1 hour idle, 3 hours at most",
          (config.CUSTOM_ROLES_PICKER_IDLE_TTL, config.CUSTOM_ROLES_PICKER_MAX_TTL) == (3600, 10800))
    check("new link: closes after the idle time unless used",
          abs(link1.expires_at - (time.time() + config.CUSTOM_ROLES_PICKER_IDLE_TTL)) < 5
          and abs(link1.max_expires_at - (time.time() + config.CUSTOM_ROLES_PICKER_MAX_TTL)) < 5)
    check("lookup finds the link", tokens.lookup(t1) is not None and tokens.lookup(t1).user_id == m.id)
    check("only the hash is stored", t1 not in tokens._links and t1 not in str(tokens._links))
    t2, _ = tokens.create(GID, m.id)
    check("a new link replaces the old one", tokens.lookup(t1) is None and tokens.lookup(t2) is not None)
    other = with_avatar(FakeMember(g, booster=True, name="other"))
    t_other, _ = tokens.create(GID, other.id)
    check("other members' links are separate", tokens.lookup(t2) is not None and tokens.lookup(t_other) is not None)
    tokens.lookup(t2).max_expires_at = time.time() - 1
    check("expired link refused", tokens.lookup(t2) is None)
    check("unknown and oversized tokens refused", tokens.lookup("nope") is None and tokens.lookup("x" * 500) is None)
    t3, _ = tokens.create(GID, m.id)
    check("revoke ends the link", tokens.revoke(GID, m.id) and tokens.lookup(t3) is None)

    # ------------------------------------------------------------------ client address
    def req(headers, remote="198.51.100.1"):
        r = make_mocked_request("GET", "/custom-roles/api/state", headers=headers)
        r._transport_peername = (remote, 1234)
        return r

    spoof = {"X-Forwarded-For": "6.6.6.6, 203.0.113.7"}
    check("trust off: X-Forwarded-For ignored", custom_role_picker.client_ip(req(spoof), trust_proxy=False) == "198.51.100.1",
          custom_role_picker.client_ip(req(spoof), trust_proxy=False))
    check("trust on: rightmost hop (added by the proxy), not the spoofed leftmost",
          custom_role_picker.client_ip(req(spoof), trust_proxy=True) == "203.0.113.7")
    check("trust on: no header -> socket address", custom_role_picker.client_ip(req({}), trust_proxy=True) == "198.51.100.1")
    check("trust on: blank header -> socket address",
          custom_role_picker.client_ip(req({"X-Forwarded-For": " , "}), trust_proxy=True) == "198.51.100.1")

    # ------------------------------------------------------------------ server refactor
    config.DASHBOARD_CLIENT_ID = config.DASHBOARD_CLIENT_SECRET = config.DASHBOARD_SECRET_KEY = None
    server = DashboardWebServer(bot)
    check("dashboard not configured in tests", not server.configured)
    config.CUSTOM_ROLES_PICKER_ENABLED = False
    await server.start()
    check("nothing on (no dashboard, picker off): server doesn't start", server.runner is None)
    config.CUSTOM_ROLES_PICKER_ENABLED = True
    old_host, old_port = config.DASHBOARD_HOST, config.DASHBOARD_PORT
    config.DASHBOARD_HOST, config.DASHBOARD_PORT = "127.0.0.1", 0
    await server.start()
    check("picker on without the dashboard: server starts", server.runner is not None and bot.custom_role_picker_ready)
    await server.stop()
    check("stop marks the picker unavailable", not bot.custom_role_picker_ready)
    config.DASHBOARD_HOST, config.DASHBOARD_PORT = old_host, old_port

    app = DashboardWebServer(bot).build_app()
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        async def get(path, token=None, headers=None):
            h = dict(headers or {})
            if token is not None:
                h["Authorization"] = f"Bearer {token}"
            return await client.get(path, headers=h)

        r = await get("/")
        check("dashboard routes absent when not configured", r.status == 404)
        r = await get("/api/bootstrap")
        check("dashboard API absent when not configured", r.status == 404)

        r = await get("/custom-roles")
        page = await r.text()
        check("picker page served", r.status == 200 and "Custom Role Color Picker" in page)
        for name, value in (("Referrer-Policy", "no-referrer"), ("Cache-Control", "no-store"),
                            ("X-Frame-Options", "DENY"), ("X-Content-Type-Options", "nosniff")):
            check(f"page header {name}: {value}", r.headers.get(name) == value, r.headers.get(name))
        csp = r.headers.get("Content-Security-Policy", "")
        check("CSP: scripts only from self, no inline", "script-src 'self'" in csp and "unsafe-inline" not in csp, csp)
        check("page has no inline scripts, styles or handlers",
              "<script>" not in page and "style=" not in page and " on" + "click" not in page)
        check("page sets meta no-referrer too", 'name="referrer" content="no-referrer"' in page)

        for name in ("picker.js", "picker.css", "theme.css"):
            r = await get(f"/custom-roles/static/{name}")
            check(f"static {name} served with no-referrer", r.status == 200 and r.headers.get("Referrer-Policy") == "no-referrer")
        for bad in ("picker.html", "..%2Fdashboard.js", "dashboard.js", "nope.js"):
            r = await get(f"/custom-roles/static/{bad}")
            check(f"static {bad} refused", r.status == 404, r.status)
        r = await get("/custom-roles/nothing-here")
        check("unknown /custom-role path: 404 with picker headers", r.status == 404 and r.headers.get("Referrer-Policy") == "no-referrer")

        # API: token only in the header
        token, _ = tokens.create(GID, m.id)
        r = await get("/custom-roles/api/state", token)
        body = await r.json()
        check("state with a valid token", r.status == 200 and body["ok"] and body["state"]["role"]["name"] == "Moon Child", body)
        check("state has colors, user and guild",
              body["state"]["role"]["primary"] == "#FF66AA" and body["state"]["user"]["name"] == "moon"
              and body["state"]["guild"]["name"] == "Test Server" and body["state"]["role"]["mode"] == "solid")
        check("state carries both expiry times",
              abs(body["expires_at"] - (time.time() + config.CUSTOM_ROLES_PICKER_IDLE_TTL)) < 5
              and abs(body["max_expires_at"] - (time.time() + config.CUSTOM_ROLES_PICKER_MAX_TTL)) < 5, body)
        check("API header no-referrer + no-store",
              r.headers.get("Referrer-Policy") == "no-referrer" and r.headers.get("Cache-Control") == "no-store")
        r = await get("/custom-roles/api/state")
        check("no token -> 401 expired", r.status == 401 and (await r.json())["error"] == "expired")
        r = await get("/custom-roles/api/state", "wrong-token")
        check("wrong token -> 401", r.status == 401)
        r = await get(f"/custom-roles/api/state?token={token}")
        check("token in the URL -> 400, even if valid", r.status == 400 and (await r.json())["error"] == "token_in_url")
        r = await get(f"/custom-roles/api/state?t={token}", token)
        check("token in the URL refused even with the header", r.status == 400)
        r = await client.get("/custom-roles/api/state", headers={"Authorization": token})
        check("header without 'Bearer ' refused", r.status == 401)

        new_token, _ = tokens.create(GID, m.id)
        r = await get("/custom-roles/api/state", token)
        check("old link stops working after a new one", r.status == 401)
        r = await get("/custom-roles/api/state", new_token)
        check("new link works", r.status == 200)
        tokens.lookup(new_token).max_expires_at = time.time() - 1
        r = await get("/custom-roles/api/state", new_token)
        check("expired link -> 401 with the 'run it again' message",
              r.status == 401 and "Color picker" in (await r.json())["message"])

        # idle expiry: each successful call resets it; never past the hard limit
        token, link = tokens.create(GID, m.id, idle_ttl=100, max_ttl=1000)
        link.last_used = time.time() - 101
        r = await get("/custom-roles/api/state", token)
        check("unused for longer than the idle time -> closed (401)", r.status == 401)
        token, link = tokens.create(GID, m.id, idle_ttl=100, max_ttl=1000)
        link.last_used = time.time() - 90
        r = await get("/custom-roles/api/state", token)
        body = await r.json()
        check("a successful call resets the idle clock", r.status == 200 and abs(link.expires_at - (time.time() + 100)) < 3
              and abs(body["expires_at"] - (time.time() + 100)) < 3, body)
        link.last_used = time.time() - 90
        m.premium_since = None
        r = await get("/custom-roles/api/state", token)
        check("a refused call (403) doesn't reset it", r.status == 403 and time.time() - link.last_used >= 89)
        m.premium_since = discord.utils.utcnow()
        link.max_expires_at = time.time() + 20
        r = await get("/custom-roles/api/state", token)
        body = await r.json()
        check("use never extends past the hard limit", r.status == 200 and body["expires_at"] <= body["max_expires_at"]
              and abs(body["expires_at"] - (time.time() + 20)) < 3, body)
        link.max_expires_at = time.time() - 1
        r = await get("/custom-roles/api/state", token)
        check("hard limit reached -> closed even while in use", r.status == 401)

        # re-checked on every request
        token, _ = tokens.create(GID, m.id)
        m.premium_since = None
        r = await get("/custom-roles/api/state", token)
        body = await r.json()
        check("stopped boosting -> 403 with the boosters message", r.status == 403 and "boost" in body["message"].lower(), body)
        m.premium_since = discord.utils.utcnow()
        await storage.update_guild_settings(GID, enabled=False)
        r = await get("/custom-roles/api/state", token)
        check("feature disabled -> 403 not set up", r.status == 403 and "isn't set up" in (await r.json())["message"])
        await storage.update_guild_settings(GID, enabled=True)
        r = await get("/custom-roles/api/state", token)
        check("back on -> works again with the same link", r.status == 200)
        g.unavailable = True
        r = await get("/custom-roles/api/state", token)
        check("server unavailable -> 503", r.status == 503)
        g.unavailable = False
        m.leave()
        r = await get("/custom-roles/api/state", token)
        check("left the server -> 403", r.status == 403 and (await r.json())["error"] == "not_member")
        g.members.append(m)

        nobody = with_avatar(FakeMember(g, booster=True, name="norole"))
        t_nobody, _ = tokens.create(GID, nobody.id)
        r = await get("/custom-roles/api/state", t_nobody)
        check("no role -> 403 telling them to press Create role", r.status == 403 and "Create role" in (await r.json())["message"])

        # archive and admin remove end the link
        token, _ = tokens.create(GID, other.id)
        await service.create_role(other, "Other Role")
        other.premium_since = None
        await service.archive(g, other.id, "test")
        r = await get("/custom-roles/api/state", token)
        check("archived role -> link revoked (401)", r.status == 401)
        other.premium_since = discord.utils.utcnow()
        await service.restore(other, dm=False)
        token, _ = tokens.create(GID, other.id)
        await service.admin_remove(g, other, m)
        r = await get("/custom-roles/api/state", token)
        check("admin remove -> link revoked (401)", r.status == 401)

        # icon in state
        await q("c", "UPDATE custom_role_records SET icon_png = ? WHERE guild_id = ? AND user_id = ?", (b"\x89PNG\r\n\x1a\n-fake", GID, m.id))
        token, _ = tokens.create(GID, m.id)
        r = await get("/custom-roles/api/state", token)
        icon = (await r.json())["state"]["role"]["icon"]
        check("saved icon image sent as a data URL", icon and icon["type"] == "image" and icon["url"].startswith("data:image/png;base64,"), (r.status, await r.text()))
        await q("c", "UPDATE custom_role_records SET icon_png = NULL, icon_emoji = ? WHERE guild_id = ? AND user_id = ?", ("🌙", GID, m.id))
        r = await get("/custom-roles/api/state", token)
        check("emoji icon sent as text", (await r.json())["state"]["role"]["icon"] == {"type": "emoji", "value": "🌙"})

        # per-token read limit
        old_limit = tokens.READ_LIMIT
        tokens.READ_LIMIT = 5
        token, _ = tokens.create(GID, m.id)
        statuses = [(await get("/custom-roles/api/state", token)).status for _ in range(6)]
        check("read limit per token -> 429", statuses == [200] * 5 + [429], statuses)
        token2, _ = tokens.create(GID, m.id)
        check("a fresh link has its own limit", (await get("/custom-roles/api/state", token2)).status == 200)
        tokens.READ_LIMIT = old_limit
        link = tokens.lookup(token2)
        check("write limit counted separately", all(tokens.allow(link, write=True) for _ in range(tokens.WRITE_LIMIT))
              and not tokens.allow(link, write=True))

        # failed attempts per address; a spoofed X-Forwarded-For doesn't dodge it
        picker = next(mw for mw in app.middlewares if getattr(mw, "__self__", None).__class__.__name__ == "CustomRolePicker").__self__
        old_failed = custom_role_picker.FAILED_LIMIT
        custom_role_picker.FAILED_LIMIT = 4
        config.CUSTOM_ROLES_TRUST_PROXY = False
        picker._failed.clear()
        statuses = [(await get("/custom-roles/api/state", "bad", {"X-Forwarded-For": f"10.0.0.{i}"})).status for i in range(5)]
        check("trust off: spoofed X-Forwarded-For can't dodge the failed-attempt limit",
              statuses == [401] * 4 + [429], statuses)
        good, _ = tokens.create(GID, m.id)
        check("a valid link still works from a blocked address (no shared-proxy lockout)",
              (await get("/custom-roles/api/state", good)).status == 200)
        check("bad tokens from that address stay blocked", (await get("/custom-roles/api/state", "bad")).status == 429)
        picker._failed.clear()
        config.CUSTOM_ROLES_TRUST_PROXY = True
        statuses = [(await get("/custom-roles/api/state", "bad", {"X-Forwarded-For": f"6.6.6.{i}, 203.0.113.7"})).status
                    for i in range(5)]
        check("trust on: changing the leftmost value doesn't dodge the limit", statuses == [401] * 4 + [429], statuses)
        r = await get("/custom-roles/api/state", good, {"X-Forwarded-For": "6.6.6.6, 203.0.113.8"})
        check("trust on: a different real client (rightmost) isn't blocked", r.status == 200, r.status)
        config.CUSTOM_ROLES_TRUST_PROXY = False
        custom_role_picker.FAILED_LIMIT = old_failed
        picker._failed.clear()

        # writes from other sites
        r = await client.post("/custom-roles/api/state", headers={"Origin": "https://evil.example"})
        check("cross-origin write -> 403", r.status == 403 and (await r.json())["error"] == "cross_origin")
        r = await client.post("/custom-roles/api/state", headers={"Origin": "http://localhost:8080"})
        check("same-origin write passes the origin check (405: no write routes yet)", r.status == 405, r.status)

        # post-merge fix 7: every error status keeps the picker's security headers
        for method, path in (("POST", "/custom-roles/api/state"), ("PUT", "/custom-roles/api/color")):
            r = await client.request(method, path)
            body = await r.json()
            check(f"{method} {path}: 405 is a JSON error with picker headers",
                  r.status == 405 and body["error"] == "http_error"
                  and r.headers.get("Content-Security-Policy") == custom_role_picker.CSP
                  and r.headers.get("X-Content-Type-Options") == "nosniff"
                  and r.headers.get("Cache-Control") == "no-store", (r.status, body, dict(r.headers)))

        # post-merge fix 5: rate-limit maps forget addresses and members with nothing left
        old_window, old_fetch_window = custom_role_picker.FAILED_WINDOW, custom_role_picker.FETCH_WINDOW
        old_max = custom_role_picker.MAX_TRACKED
        custom_role_picker.FAILED_WINDOW = custom_role_picker.FETCH_WINDOW = 0.05
        picker._failed.clear()
        for i in range(50):  # a scanner rotating IPv6 addresses
            picker._note_failed(f"2001:db8::{i:x}")
        await asyncio.sleep(0.1)
        picker._failed_allowed("2001:db8::0")
        check("expired address is forgotten when checked", "2001:db8::0" not in picker._failed and len(picker._failed) == 49,
              len(picker._failed))
        custom_role_picker.MAX_TRACKED = 10
        picker._failed_allowed("198.51.100.1")
        check("over MAX_TRACKED every stale address is swept", len(picker._failed) == 0, len(picker._failed))
        picker._fetches.clear()
        picker._fetch_allowed((GID, 1))
        await asyncio.sleep(0.1)
        custom_role_picker.MAX_TRACKED = 0
        picker._fetch_allowed((GID, 2))
        check("fetch map drops stale members too", list(picker._fetches) == [(GID, 2)], list(picker._fetches))
        custom_role_picker.FAILED_WINDOW, custom_role_picker.FETCH_WINDOW = old_window, old_fetch_window
        custom_role_picker.MAX_TRACKED = old_max
        picker._failed.clear()
        picker._fetches.clear()
        for _ in range(custom_role_picker.FAILED_LIMIT):
            picker._note_failed("203.0.113.9")
        check("pruning doesn't weaken the limit itself", not picker._failed_allowed("203.0.113.9"))
        picker._failed.clear()
    finally:
        await client.close()

    # ------------------------------------------------------------------ the panel's Color picker button
    from cogs.customization.custom_roles import CustomRoles
    cog = CustomRoles.__new__(CustomRoles)
    cog.bot = bot

    class Followup:
        def __init__(self, refuse_view=False):
            self.sent, self.refuse_view = [], refuse_view

        async def send(self, embed=None, view=None, ephemeral=None):
            if view is not None and self.refuse_view:
                raise discord.HTTPException(SimpleNamespace(status=400, reason="Bad"), "Invalid url")
            self.sent.append((embed, view, ephemeral))

    class Response:
        async def defer(self, **kw):
            pass

    def inter(user, refuse_view=False):
        return SimpleNamespace(user=user, response=Response(), followup=Followup(refuse_view))

    tokens.clear()
    bot.custom_role_picker_ready = False
    i = inter(m)
    await cog._send_picker_link(i)
    embed, view, ephemeral = i.followup.sent[-1]
    check("server not running: friendly error, no link", "isn't available" in embed.description and view is None
          and not tokens._by_member)
    check("server not running: admins told in the log channel", "web server isn't running" in g.channel.texts()[-1])

    bot.custom_role_picker_ready = True
    i = inter(m)
    await cog._send_picker_link(i)
    embed, view, ephemeral = i.followup.sent[-1]
    url = view.children[0].url
    check("link button with the token after #", url.startswith("http://localhost:8080/custom-roles#") and ephemeral)
    check("button link works", tokens.lookup(url.split("#", 1)[1]) is not None)
    check("reply explains idle + latest expiry and the don't-share warning",
          "1h** without use" in embed.description and "at the latest" in embed.description
          and "<t:" in embed.description and "share" in embed.description, embed.description)
    first = url.split("#", 1)[1]
    i = inter(m, refuse_view=True)
    await cog._send_picker_link(i)
    embed, view, _ = i.followup.sent[-1]
    fallback = embed.fields[0].value if embed.fields else ""
    check("Discord refuses the button: link shown as text", view is None and fallback.startswith("http://localhost:8080/custom-roles#"))
    check("pressing it again stops the old link", tokens.lookup(first) is None and tokens.lookup(fallback.split("#", 1)[1]))

    nobody_i = inter(nobody)
    await cog._send_picker_link(nobody_i)
    check("no role: told to make one, no link", "Create role" in nobody_i.followup.sent[-1][0].description)

    os.environ["ENVIRONMENT"] = "production"
    i = inter(m)
    await cog._send_picker_link(i)
    check("production + http address: no link handed out", i.followup.sent[-1][1] is None
          and "https" in g.channel.texts()[-1])
    os.environ["ENVIRONMENT"] = "development"

    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())
