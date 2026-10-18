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
    from helpers.lunar_roles import service, storage, tokens
    from web import lunar_picker
    from web.dashboard import DashboardWebServer

    q = db.execute_db_operation
    await db.init_lunar_roles_tables()
    service.ARCHIVE_BATCH_PAUSE = 0

    async def reset():
        for table in ("lunar_custom_roles", "lunar_guild_settings", "lunar_pending_removals", "lunar_archive_snoozes"):
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
    bot = SimpleNamespace(get_guild=lambda gid: guilds.get(gid), lunar_picker_ready=False)

    # ------------------------------------------------------------------ settings and links
    config.LUNAR_PICKER_ENABLED = True
    config.LUNAR_PUBLIC_URL = "http://localhost:8080"
    check("picker link ok locally over http", service.picker_link_problem() is None)
    os.environ["ENVIRONMENT"] = "production"
    check("production refuses http links", "https" in (service.picker_link_problem() or ""))
    config.LUNAR_PUBLIC_URL = "https://lunar.example"
    check("production accepts https links", service.picker_link_problem() is None)
    os.environ["ENVIRONMENT"] = "development"
    config.LUNAR_PUBLIC_URL = "ftp://nope"
    check("non-http address refused", service.picker_link_problem() is not None)
    config.LUNAR_PUBLIC_URL = "http://localhost:8080"
    config.LUNAR_PICKER_ENABLED = False
    check("disabled picker refused", "LUNAR_PICKER_ENABLED" in (service.picker_link_problem() or ""))
    config.LUNAR_PICKER_ENABLED = True
    check("token goes after #", service.picker_url("abc") == "http://localhost:8080/lunar#abc")

    # ------------------------------------------------------------------ token store
    t1, exp1 = tokens.create(GID, m.id)
    check("token is long and URL-safe", len(t1) >= 43 and all(c.isalnum() or c in "-_" for c in t1))
    check("expiry is LUNAR_PICKER_TTL from now", abs(exp1 - (time.time() + config.LUNAR_PICKER_TTL)) < 5)
    check("lookup finds the link", tokens.lookup(t1) is not None and tokens.lookup(t1).user_id == m.id)
    check("only the hash is stored", t1 not in tokens._links and t1 not in str(tokens._links))
    t2, _ = tokens.create(GID, m.id)
    check("a new link replaces the old one", tokens.lookup(t1) is None and tokens.lookup(t2) is not None)
    other = with_avatar(FakeMember(g, booster=True, name="other"))
    t_other, _ = tokens.create(GID, other.id)
    check("other members' links are separate", tokens.lookup(t2) is not None and tokens.lookup(t_other) is not None)
    tokens.lookup(t2).expires_at = time.time() - 1
    check("expired link refused", tokens.lookup(t2) is None)
    check("unknown and oversized tokens refused", tokens.lookup("nope") is None and tokens.lookup("x" * 500) is None)
    t3, _ = tokens.create(GID, m.id)
    check("revoke ends the link", tokens.revoke(GID, m.id) and tokens.lookup(t3) is None)

    # ------------------------------------------------------------------ client address
    def req(headers, remote="198.51.100.1"):
        r = make_mocked_request("GET", "/lunar/api/state", headers=headers)
        r._transport_peername = (remote, 1234)
        return r

    spoof = {"X-Forwarded-For": "6.6.6.6, 203.0.113.7"}
    check("trust off: X-Forwarded-For ignored", lunar_picker.client_ip(req(spoof), trust_proxy=False) == "198.51.100.1",
          lunar_picker.client_ip(req(spoof), trust_proxy=False))
    check("trust on: rightmost hop (added by the proxy), not the spoofed leftmost",
          lunar_picker.client_ip(req(spoof), trust_proxy=True) == "203.0.113.7")
    check("trust on: no header -> socket address", lunar_picker.client_ip(req({}), trust_proxy=True) == "198.51.100.1")
    check("trust on: blank header -> socket address",
          lunar_picker.client_ip(req({"X-Forwarded-For": " , "}), trust_proxy=True) == "198.51.100.1")

    # ------------------------------------------------------------------ server refactor
    config.DASHBOARD_CLIENT_ID = config.DASHBOARD_CLIENT_SECRET = config.DASHBOARD_SECRET_KEY = None
    server = DashboardWebServer(bot)
    check("dashboard not configured in tests", not server.configured)
    config.LUNAR_PICKER_ENABLED = False
    await server.start()
    check("nothing on (no dashboard, picker off): server doesn't start", server.runner is None)
    config.LUNAR_PICKER_ENABLED = True
    old_host, old_port = config.DASHBOARD_HOST, config.DASHBOARD_PORT
    config.DASHBOARD_HOST, config.DASHBOARD_PORT = "127.0.0.1", 0
    await server.start()
    check("picker on without the dashboard: server starts", server.runner is not None and bot.lunar_picker_ready)
    await server.stop()
    check("stop marks the picker unavailable", not bot.lunar_picker_ready)
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

        r = await get("/lunar")
        page = await r.text()
        check("picker page served", r.status == 200 and "Lunar Color Picker" in page)
        for name, value in (("Referrer-Policy", "no-referrer"), ("Cache-Control", "no-store"),
                            ("X-Frame-Options", "DENY"), ("X-Content-Type-Options", "nosniff")):
            check(f"page header {name}: {value}", r.headers.get(name) == value, r.headers.get(name))
        csp = r.headers.get("Content-Security-Policy", "")
        check("CSP: scripts only from self, no inline", "script-src 'self'" in csp and "unsafe-inline" not in csp, csp)
        check("page has no inline scripts, styles or handlers",
              "<script>" not in page and "style=" not in page and " on" + "click" not in page)
        check("page sets meta no-referrer too", 'name="referrer" content="no-referrer"' in page)

        for name in ("picker.js", "picker.css", "lunar-theme.css"):
            r = await get(f"/lunar/static/{name}")
            check(f"static {name} served with no-referrer", r.status == 200 and r.headers.get("Referrer-Policy") == "no-referrer")
        for bad in ("picker.html", "..%2Fdashboard.js", "dashboard.js", "nope.js"):
            r = await get(f"/lunar/static/{bad}")
            check(f"static {bad} refused", r.status == 404, r.status)
        r = await get("/lunar/nothing-here")
        check("unknown /lunar path: 404 with picker headers", r.status == 404 and r.headers.get("Referrer-Policy") == "no-referrer")

        # API: token only in the header
        token, _ = tokens.create(GID, m.id)
        r = await get("/lunar/api/state", token)
        body = await r.json()
        check("state with a valid token", r.status == 200 and body["ok"] and body["state"]["role"]["name"] == "Moon Child", body)
        check("state has colors, user and guild",
              body["state"]["role"]["primary"] == "#FF66AA" and body["state"]["user"]["name"] == "moon"
              and body["state"]["guild"]["name"] == "Lunar Lab" and body["state"]["role"]["mode"] == "solid")
        check("state carries the expiry", abs(body["expires_at"] - (time.time() + config.LUNAR_PICKER_TTL)) < 5)
        check("API header no-referrer + no-store",
              r.headers.get("Referrer-Policy") == "no-referrer" and r.headers.get("Cache-Control") == "no-store")
        r = await get("/lunar/api/state")
        check("no token -> 401 expired", r.status == 401 and (await r.json())["error"] == "expired")
        r = await get("/lunar/api/state", "wrong-token")
        check("wrong token -> 401", r.status == 401)
        r = await get(f"/lunar/api/state?token={token}")
        check("token in the URL -> 400, even if valid", r.status == 400 and (await r.json())["error"] == "token_in_url")
        r = await get(f"/lunar/api/state?t={token}", token)
        check("token in the URL refused even with the header", r.status == 400)
        r = await client.get("/lunar/api/state", headers={"Authorization": token})
        check("header without 'Bearer ' refused", r.status == 401)

        new_token, _ = tokens.create(GID, m.id)
        r = await get("/lunar/api/state", token)
        check("old link stops working after a new one", r.status == 401)
        r = await get("/lunar/api/state", new_token)
        check("new link works", r.status == 200)
        tokens.lookup(new_token).expires_at = time.time() - 1
        r = await get("/lunar/api/state", new_token)
        check("expired link -> 401 with the 'run it again' message",
              r.status == 401 and "color-picker" in (await r.json())["message"])

        # re-checked on every request
        token, _ = tokens.create(GID, m.id)
        m.premium_since = None
        r = await get("/lunar/api/state", token)
        body = await r.json()
        check("stopped boosting -> 403 with the boosters message", r.status == 403 and "boost" in body["message"].lower(), body)
        m.premium_since = discord.utils.utcnow()
        await storage.update_guild_settings(GID, enabled=False)
        r = await get("/lunar/api/state", token)
        check("feature disabled -> 403 not set up", r.status == 403 and "isn't set up" in (await r.json())["message"])
        await storage.update_guild_settings(GID, enabled=True)
        r = await get("/lunar/api/state", token)
        check("back on -> works again with the same link", r.status == 200)
        g.unavailable = True
        r = await get("/lunar/api/state", token)
        check("server unavailable -> 503", r.status == 503)
        g.unavailable = False
        m.leave()
        r = await get("/lunar/api/state", token)
        check("left the server -> 403", r.status == 403 and (await r.json())["error"] == "not_member")
        g.members.append(m)

        nobody = with_avatar(FakeMember(g, booster=True, name="norole"))
        t_nobody, _ = tokens.create(GID, nobody.id)
        r = await get("/lunar/api/state", t_nobody)
        check("no role -> 403 telling them to /lunar role", r.status == 403 and "/lunar role" in (await r.json())["message"])

        # archive and admin remove end the link
        token, _ = tokens.create(GID, other.id)
        await service.create_role(other, "Other Role")
        other.premium_since = None
        await service.archive(g, other.id, "test")
        r = await get("/lunar/api/state", token)
        check("archived role -> link revoked (401)", r.status == 401)
        other.premium_since = discord.utils.utcnow()
        await service.restore(other, dm=False)
        token, _ = tokens.create(GID, other.id)
        await service.admin_remove(g, other, m)
        r = await get("/lunar/api/state", token)
        check("admin remove -> link revoked (401)", r.status == 401)

        # icon in state
        await q("c", "UPDATE lunar_custom_roles SET icon_png = ? WHERE guild_id = ? AND user_id = ?", (b"\x89PNG-fake", GID, m.id))
        token, _ = tokens.create(GID, m.id)
        r = await get("/lunar/api/state", token)
        icon = (await r.json())["state"]["role"]["icon"]
        check("saved icon image sent as a data URL", icon["type"] == "image" and icon["url"].startswith("data:image/png;base64,"))
        await q("c", "UPDATE lunar_custom_roles SET icon_png = NULL, icon_emoji = ? WHERE guild_id = ? AND user_id = ?", ("🌙", GID, m.id))
        r = await get("/lunar/api/state", token)
        check("emoji icon sent as text", (await r.json())["state"]["role"]["icon"] == {"type": "emoji", "value": "🌙"})

        # per-token read limit
        old_limit = tokens.READ_LIMIT
        tokens.READ_LIMIT = 5
        token, _ = tokens.create(GID, m.id)
        statuses = [(await get("/lunar/api/state", token)).status for _ in range(6)]
        check("read limit per token -> 429", statuses == [200] * 5 + [429], statuses)
        token2, _ = tokens.create(GID, m.id)
        check("a fresh link has its own limit", (await get("/lunar/api/state", token2)).status == 200)
        tokens.READ_LIMIT = old_limit
        link = tokens.lookup(token2)
        check("write limit counted separately", all(tokens.allow(link, write=True) for _ in range(tokens.WRITE_LIMIT))
              and not tokens.allow(link, write=True))

        # failed attempts per address; a spoofed X-Forwarded-For doesn't dodge it
        picker = next(mw for mw in app.middlewares if getattr(mw, "__self__", None).__class__.__name__ == "LunarPicker").__self__
        old_failed = lunar_picker.FAILED_LIMIT
        lunar_picker.FAILED_LIMIT = 4
        config.LUNAR_TRUST_PROXY = False
        picker._failed.clear()
        statuses = [(await get("/lunar/api/state", "bad", {"X-Forwarded-For": f"10.0.0.{i}"})).status for i in range(5)]
        check("trust off: spoofed X-Forwarded-For can't dodge the failed-attempt limit",
              statuses == [401] * 4 + [429], statuses)
        good, _ = tokens.create(GID, m.id)
        check("a valid link still works from a blocked address (no shared-proxy lockout)",
              (await get("/lunar/api/state", good)).status == 200)
        check("bad tokens from that address stay blocked", (await get("/lunar/api/state", "bad")).status == 429)
        picker._failed.clear()
        config.LUNAR_TRUST_PROXY = True
        statuses = [(await get("/lunar/api/state", "bad", {"X-Forwarded-For": f"6.6.6.{i}, 203.0.113.7"})).status
                    for i in range(5)]
        check("trust on: changing the leftmost value doesn't dodge the limit", statuses == [401] * 4 + [429], statuses)
        r = await get("/lunar/api/state", good, {"X-Forwarded-For": "6.6.6.6, 203.0.113.8"})
        check("trust on: a different real client (rightmost) isn't blocked", r.status == 200, r.status)
        config.LUNAR_TRUST_PROXY = False
        lunar_picker.FAILED_LIMIT = old_failed
        picker._failed.clear()

        # writes from other sites
        r = await client.post("/lunar/api/state", headers={"Origin": "https://evil.example"})
        check("cross-origin write -> 403", r.status == 403 and (await r.json())["error"] == "cross_origin")
        r = await client.post("/lunar/api/state", headers={"Origin": "http://localhost:8080"})
        check("same-origin write passes the origin check (405: no write routes yet)", r.status == 405, r.status)
    finally:
        await client.close()

    # ------------------------------------------------------------------ /lunar color-picker command
    from cogs.customization.lunar_roles import LunarRoles
    cog = LunarRoles.__new__(LunarRoles)
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
    bot.lunar_picker_ready = False
    i = inter(m)
    await LunarRoles.lunar_color_picker.callback(cog, i)
    embed, view, ephemeral = i.followup.sent[-1]
    check("server not running: friendly error, no link", "isn't available" in embed.description and view is None
          and not tokens._by_member)
    check("server not running: admins told in the log channel", "web server isn't running" in g.channel.texts()[-1])

    bot.lunar_picker_ready = True
    i = inter(m)
    await LunarRoles.lunar_color_picker.callback(cog, i)
    embed, view, ephemeral = i.followup.sent[-1]
    url = view.children[0].url
    check("link button with the token after #", url.startswith("http://localhost:8080/lunar#") and ephemeral)
    check("button link works", tokens.lookup(url.split("#", 1)[1]) is not None)
    check("reply shows the expiry and the don't-share warning", "<t:" in embed.description and "share" in embed.description)
    first = url.split("#", 1)[1]
    i = inter(m, refuse_view=True)
    await LunarRoles.lunar_color_picker.callback(cog, i)
    embed, view, _ = i.followup.sent[-1]
    fallback = embed.fields[0].value if embed.fields else ""
    check("Discord refuses the button: link shown as text", view is None and fallback.startswith("http://localhost:8080/lunar#"))
    check("running it again stops the old link", tokens.lookup(first) is None and tokens.lookup(fallback.split("#", 1)[1]))

    nobody_i = inter(nobody)
    await LunarRoles.lunar_color_picker.callback(cog, nobody_i)
    check("no role: told to make one, no link", "/lunar role" in nobody_i.followup.sent[-1][0].description)

    os.environ["ENVIRONMENT"] = "production"
    i = inter(m)
    await LunarRoles.lunar_color_picker.callback(cog, i)
    check("production + http address: no link handed out", i.followup.sent[-1][1] is None
          and "https" in g.channel.texts()[-1])
    os.environ["ENVIRONMENT"] = "development"

    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())
