"""Offline Milestone 7 checks: picker write APIs, palette, cooldown on the web, preview test switch,
XSS safety, and the theme rules (every value in theme.css)."""
import asyncio
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

import discord  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from fakes import FakeGuild, FakeMember  # noqa: E402

GID = 8
assert GID in _safety.TEST_GUILD_IDS
STATIC = _safety.REPO / "web" / "static" / "custom_roles"
XSS = "<img src=x onerror=alert(1)>"
results = []


def check(label, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))


def png_bytes():
    from PIL import Image
    img = Image.new("RGB", (64, 64), (255, 102, 170))
    for x in range(32, 64):
        for y in range(64):
            img.putpixel((x, y), (40, 120, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class FakeAvatar:
    def __init__(self, key):
        self.url = f"https://cdn.discordapp.com/avatars/{key}/a.png?size=128"

    def replace(self, **kw):
        return self

    async def read(self):
        return png_bytes()


def with_avatar(member, key):
    member.guild_avatar, member.avatar, member.default_avatar = None, FakeAvatar(key), FakeAvatar(key)
    return member


async def main():
    import config
    import database as db
    from helpers.custom_roles import service, storage, tokens
    from web import custom_role_picker
    from utils.dashboard_picker_server import CustomRolePickerServer

    q = db.execute_db_operation
    await db.init_custom_roles_tables()

    async def reset():
        for table in ("custom_role_records", "custom_role_guild_settings", "custom_role_pending_removals", "custom_role_archive_snoozes"):
            await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))
        tokens.clear()

    async def setup_guild(features=()):
        await reset()
        g = FakeGuild(GID, features)
        await service.set_anchor(g, g.anchor)
        await service.set_enabled(g, True)
        await storage.update_guild_settings(GID, log_channel_id=g.channel.id)
        return g

    # ------------------------------------------------------------------ message text for the page
    t = int(time.time()) + 125
    text = custom_role_picker.web_text(f"**Bold** `code` again <t:{t}:R>, <@&1> <@2> <@!3> <#4>")
    check("web_text strips markdown and converts Discord markup",
          text.startswith("Bold code again in 2m") and "a role a member a member a channel" in text and "<" not in text, text)

    config.CUSTOM_ROLES_PICKER_ENABLED = True
    config.CUSTOM_ROLES_PUBLIC_URL = "http://localhost:8080"
    guilds = {}
    bot = SimpleNamespace(get_guild=lambda gid: guilds.get(gid), custom_role_picker_ready=True)
    client = TestClient(TestServer(CustomRolePickerServer(bot).build_app()))
    await client.start_server()

    async def call(method, path, token=None, body=None, headers=None, raw=None):
        h = {"Authorization": f"Bearer {token}"} if token else {}
        h.update(headers or {})
        if body is not None:
            h.setdefault("Content-Type", "application/json")
            raw = json.dumps(body)
        r = await client.request(method, path, headers=h, data=raw)
        try:
            data = await r.json()
        except Exception:
            data = None
        return r.status, data

    try:
        # ------------------------------------------------------------------ solid colors and names
        g = await setup_guild()
        guilds[GID] = g
        m = with_avatar(FakeMember(g, booster=True, name="moon"), "moon")
        await service.create_role(m, "Moon Child")
        role = g.get_role((await storage.get_custom_role(GID, m.id)).role_id)
        tok, _ = tokens.create(GID, m.id)

        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "solid", "primary": "ff66aa"})
        check("solid color saved", status == 200 and body["ok"] and role.colour.value == 0xFF66AA, body)
        check("reply carries fresh state", body["state"]["role"]["primary"] == "#FF66AA" and body["state"]["role"]["mode"] == "solid")
        check("reply message is plain text", "**" not in body["message"] and "`" not in body["message"], body["message"])
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "solid", "primary": "#000"})
        check("black stored as #010101 (same as the command)", body["ok"] and body["state"]["role"]["primary"] == "#010101", body)
        for bad in ({"mode": "solid"}, {"mode": "solid", "primary": "nope"}, {"mode": "solid", "primary": 123},
                    {"mode": "solid", "primary": "#" + "F" * 40}):
            status, body = await call("POST", "/custom-roles/api/color", tok, bad)
            check(f"bad color refused: {str(bad)[:40]}", status == 400 and body["error"] == "bad_color", (status, body))
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "rainbow", "primary": "#FFF"})
        check("unknown style refused", status == 400 and body["error"] == "bad_mode")
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "gradient", "primary": "#FFF"})
        check("gradient without a secondary refused", status == 400 and "Secondary" in body["message"])
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "gradient", "primary": "#FF0000", "secondary": "#0000FF"})
        check("gradient without Enhanced Role Colors: refused by the service, role unchanged",
              status == 200 and not body["ok"] and "3 server boosts" in body["message"].lower()
              and role.secondary_colour is None and body["state"]["role"]["mode"] == "solid", body)
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "holographic"})
        check("holographic without the feature refused too", status == 200 and not body["ok"])

        status, body = await call("POST", "/custom-roles/api/name", tok, {"name": "Admin"})
        check("name filter applies on the web", status == 200 and not body["ok"] and body["state"]["role"]["name"] == "Moon Child", body)
        status, body = await call("POST", "/custom-roles/api/name", tok, {"name": "  Star   Dust  "})
        check("rename works and is cleaned", body["ok"] and role.name == "Star Dust" and body["state"]["role"]["name"] == "Star Dust", body)
        status, body = await call("POST", "/custom-roles/api/name", tok, {"name": 5})
        check("non-text name refused", status == 400 and body["error"] == "bad_name")
        status, body = await call("POST", "/custom-roles/api/name", tok, {"name": "x" * 101})
        check("over-long name refused with the filter's message", not body["ok"] and "100" in body["message"], body)
        check("web changes are logged like commands", any("renamed" in t for t in g.channel.texts()))
        check("log entries show the role name next to its mention (survives deletion)",
              any("renamed" in t and f"<@&{role.id}> (`Star Dust`)" in t for t in g.channel.texts())
              and any("created their role" in t and "(`Moon Child`)" in t for t in g.channel.texts())
              and any("recolored" in t and f"<@&{role.id}> (`" in t for t in g.channel.texts()), g.channel.texts()[-3:])
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "solid", "primary": "#FF66AA"})
        check("write replies carry the (reset) expiry times",
              abs(body["expires_at"] - (time.time() + config.CUSTOM_ROLES_PICKER_IDLE_TTL)) < 5 and body["max_expires_at"] >= body["expires_at"])

        # ------------------------------------------------------------------ request checks
        status, body = await call("POST", "/custom-roles/api/color", tok, raw="mode=solid", headers={"Content-Type": "text/plain"})
        check("non-JSON body refused (415)", status == 415)
        status, body = await call("POST", "/custom-roles/api/color", tok, raw="{nope", headers={"Content-Type": "application/json"})
        check("broken JSON refused (400)", status == 400 and body["error"] == "bad_json")
        status, body = await call("POST", "/custom-roles/api/color", tok, raw="[1, 2]", headers={"Content-Type": "application/json"})
        check("JSON that isn't an object refused", status == 400)
        status, body = await call("POST", "/custom-roles/api/name", tok, {"name": "y" * 3000})
        check("oversized body refused (413)", status == 413)
        status, body = await call("POST", "/custom-roles/api/color", None, {"mode": "solid", "primary": "#FFF"})
        check("write without a link -> 401 with plain-text message", status == 401 and "`" not in body["message"]
              and "/custom-role" in body["message"] and "Color picker" in body["message"], body)
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "solid", "primary": "#FFF"},
                                  headers={"Origin": "https://evil.example"})
        check("write from another site -> 403", status == 403 and body["error"] == "cross_origin")
        status, _ = await call("GET", "/custom-roles/api/color", tok)
        check("GET on a write route -> 405", status == 405)
        status, _ = await call("POST", f"/custom-roles/api/color?token={tok}", tok, {"mode": "solid", "primary": "#FFF"})
        check("token in the URL refused on writes too", status == 400)

        old = tokens.WRITE_LIMIT
        tokens.WRITE_LIMIT = 3
        tok2, _ = tokens.create(GID, m.id)
        statuses = [(await call("POST", "/custom-roles/api/color", tok2, {"mode": "solid", "primary": "#123456"}))[0] for _ in range(4)]
        check("write limit per link -> 429", statuses == [200, 200, 200, 429], statuses)
        status, _ = await call("GET", "/custom-roles/api/state", tok2)
        check("reads aren't blocked by the write limit", status == 200)
        tokens.WRITE_LIMIT = old
        tok = tok2

        m.premium_since = None
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "solid", "primary": "#FFFFFF"})
        check("stopped boosting mid-session -> 403, nothing changed", status == 403 and role.colour.value == 0x123456, (status, body))
        m.premium_since = discord.utils.utcnow()
        tokens.lookup(tok).max_expires_at = time.time() - 1
        status, _ = await call("POST", "/custom-roles/api/color", tok, {"mode": "solid", "primary": "#FFFFFF"})
        check("expired link mid-session -> 401", status == 401)

        # ------------------------------------------------------------------ cooldown on the web
        tok, _ = tokens.create(GID, m.id)
        await service.set_cooldown(g, 300)
        await q("c", "UPDATE custom_role_records SET last_changed_at = NULL WHERE guild_id = ? AND user_id = ?", (GID, m.id))
        status, body = await call("GET", "/custom-roles/api/state", tok)
        check("state: no cooldown running", body["state"]["next_change_at"] is None and body["state"]["cooldown_seconds"] == 300)
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "solid", "primary": "#ABCDEF"})
        check("first change allowed", body["ok"])
        nca = body["state"]["next_change_at"]
        check("state now says when the next change is allowed", isinstance(nca, int) and 295 <= nca - time.time() <= 302, nca)
        status, body = await call("POST", "/custom-roles/api/name", tok, {"name": "Too Soon"})
        check("second change refused with retry_at and plain 'in 5m…' text",
              not body["ok"] and abs(body["retry_at"] - nca) <= 2 and re.search(r"in [45]m", body["message"]) and "<t:" not in body["message"], body)
        await service.set_cooldown(g, 0)

        # ------------------------------------------------------------------ palette
        status, body = await call("GET", "/custom-roles/api/palette", tok)
        check("palette from the avatar as hex", status == 200 and body["ok"] and "#FF66AA" in body["colors"]
              and all(re.fullmatch(r"#[0-9A-F]{6}", c) for c in body["colors"]), body)
        status, _ = await call("GET", "/custom-roles/api/palette")
        check("palette needs the link", status == 401)

        # ------------------------------------------------------------------ XSS: hostile names come back as plain data
        evil = with_avatar(FakeMember(g, booster=True, name=XSS), "evil")
        r = await service.create_role(evil, "Evil Role")
        check("setup: hostile member has a role", r.ok, r.message)
        evil_tok, _ = tokens.create(GID, evil.id)
        status, body = await call("POST", "/custom-roles/api/name", evil_tok, {"name": XSS})
        check("a role name like <img onerror> is allowed by the filter (it's just text)", body["ok"], body)
        status, body = await call("GET", "/custom-roles/api/state", evil_tok)
        check("display name and role name come back exactly as typed (no HTML decoding)",
              body["state"]["user"]["name"] == XSS and body["state"]["role"]["name"] == XSS, body["state"])
        g.name = XSS
        status, body = await call("GET", "/custom-roles/api/state", evil_tok)
        check("server name likewise", body["state"]["guild"]["name"] == XSS)
        g.name = "Test Server"
        status, body = await call("POST", "/custom-roles/api/name", evil_tok, {"name": "Admin" + XSS})
        check("error messages that quote names are plain text", not body["ok"] and isinstance(body["message"], str))

        js = (STATIC / "picker.js").read_text(encoding="utf-8")
        banned = ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
                  "setAttribute(\"style", "setAttribute('style", "setAttribute(\"on", ".onerror", "srcdoc"]
        found = [b for b in banned if b in js]
        check("picker.js never inserts HTML (textContent only)", not found, found)
        for key in ("saved.user.name", "icon.value", "message"):
            check(f"picker.js shows {key} via textContent", re.search(r"textContent\s*=\s*[^;]*" + re.escape(key), js) is not None)
        names = re.findall(r"textContent = [^;]*", js)
        check("names, server name and messages all go through textContent", len(names) >= 15, len(names))
        attr_writes = re.findall(r"\.(src|href)\s*=\s*([^;]+);", js)
        # icon.url / avatar_url are data: URLs from the server; url = a blob: URL of the chosen file;
        # previewUrl = a data: URL from the crop canvas. Never names or other text.
        check("only image URLs (server data:, local blob:/canvas) are used as src, never names",
              attr_writes and all(v.strip() in {"saved.user.avatar_url", "icon.url", "url", "previewUrl"}
                                  for _, v in attr_writes), attr_writes)

        # ------------------------------------------------------------------ test switch: preview Gradient/Holographic
        config.CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS = True
        status, body = await call("GET", "/custom-roles/api/state", tok)
        check("test switch (development): page told to unlock the styles", body["state"]["guild"]["preview_enhanced"] is True
              and body["state"]["guild"]["gradient"] is False)
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "gradient", "primary": "#FF0000", "secondary": "#0000FF"})
        check("test switch: saving a gradient is still refused", not body["ok"] and role.secondary_colour is None)
        os.environ["ENVIRONMENT"] = "production"
        status, body = await call("GET", "/custom-roles/api/state", tok)
        check("test switch ignored in production", body["state"]["guild"]["preview_enhanced"] is False)
        os.environ["ENVIRONMENT"] = "development"

        from cogs.customization.custom_roles import CustomRoles
        switches = {name: (is_set, active) for name, is_set, active, _, _ in CustomRoles._debug_switches()}
        check("startup warning knows the new switch", switches["CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS"] == (True, True))
        cog = CustomRoles.__new__(CustomRoles)
        cog.bot = SimpleNamespace(guilds=[g])
        cog._debug_warned = False
        await cog._warn_debug_switch_channels()
        check("log channel gets the 🚧 warning", any("CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS" in t and "🚧" in t for t in g.channel.texts()))
        import logging
        seen = []
        handler = logging.Handler()
        handler.emit = lambda record: seen.append(record.getMessage())
        logging.getLogger("custom_roles_console").addHandler(handler)
        CustomRoles._warn_debug_switch_console()
        check("console gets the loud !!! banner", any("!!! CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS IS ON" in s for s in seen), seen)
        config.CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS = False

        # ------------------------------------------------------------------ with the real feature
        g2 = await setup_guild(features=["ENHANCED_ROLE_COLORS"])
        guilds[GID] = g2
        b = with_avatar(FakeMember(g2, booster=True, name="grad"), "grad")
        await service.create_role(b, "Grad Role")
        role2 = g2.get_role((await storage.get_custom_role(GID, b.id)).role_id)
        tok, _ = tokens.create(GID, b.id)
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "gradient", "primary": "#FF0000", "secondary": "00F"})
        check("gradient saved where the server has the feature",
              body["ok"] and role2.colour.value == 0xFF0000 and role2.secondary_colour.value == 0x0000FF
              and body["state"]["role"]["secondary"] == "#0000FF", body)
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "holographic", "primary": "#123456"})
        check("holographic ignores the colors sent and uses Discord's preset",
              body["ok"] and body["state"]["role"]["mode"] == "holographic" and body["state"]["role"]["primary"] == "#A9C9FF", body)
        status, body = await call("POST", "/custom-roles/api/color", tok, {"mode": "solid", "primary": "#00FF00"})
        check("back to solid clears the gradient", body["ok"] and role2.secondary_colour is None and body["state"]["role"]["secondary"] is None)
        status, body = await call("GET", "/custom-roles/api/state", tok)
        check("no test-switch flag when the server really has the feature", body["state"]["guild"]["preview_enhanced"] is False)

        # ------------------------------------------------------------------ static files
        status, _ = await call("GET", "/custom-roles/static/favicon.svg")
        r = await client.get("/custom-roles/static/favicon.svg")
        check("favicon served as SVG", r.status == 200 and r.headers["Content-Type"].startswith("image/svg+xml"))
    finally:
        await client.close()

    html = (STATIC / "picker.html").read_text(encoding="utf-8")
    check("page links the favicon", 'rel="icon" href="/custom-roles/static/favicon.svg"' in html)
    check("page has no inline scripts, styles or handlers",
          "<script>" not in html and "style=" not in html and not re.search(r"\son[a-z]+=", html))
    inputs = re.findall(r"<input[^>]*>", html)
    unlabeled = [i for i in inputs if not (re.search(r'id="([^"]+)"', i) and f'for="{re.search(r"id=\"([^\"]+)\"", i).group(1)}"' in html)
                 and "aria-label" not in i]
    check("every input in the page has a label", not unlabeled, unlabeled)
    check("tabs use the ARIA tabs pattern", html.count('role="tab"') == 3 and 'role="tablist"' in html and html.count('role="tabpanel"') == 3)
    check("status lines are announced", html.count('role="status"') == 6)

    css = (STATIC / "picker.css").read_text(encoding="utf-8")
    lengths = re.findall(r"(?<![\w-])\d*\.?\d+(?:px|rem|em)\b", css)
    colors = re.findall(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(|(?<![\w-])(?:white|black|red|blue|green|gr[ae]y|yellow|orange|purple|pink)(?![\w-])", css)
    fonts = re.findall(r"font-family:(?!\s*var\()[^;]+", css)
    check("picker.css has no px/rem/em lengths", not lengths, lengths)
    check("picker.css has no colors", not colors, colors)
    check("picker.css has no font names", not fonts, fonts)
    radius = re.findall(r"border-radius:(?!\s*var\()[^;]+", css)
    check("picker.css radii all come from the theme", not radius, radius)
    theme = (STATIC / "theme.css").read_text(encoding="utf-8")
    decls = [l for l in theme.splitlines() if re.match(r"\s*--cr-[\w-]+:", l)]
    uncommented = [l.strip() for l in decls if "/*" not in l]
    check("every theme value has its own comment", decls and not uncommented, uncommented)
    used = set(re.findall(r"var\((--cr-[\w-]+)\)", css + js))
    defined = {re.match(r"\s*(--cr-[\w-]+):", l).group(1) for l in decls}
    check("every variable picker.css/js uses is defined in the theme", used <= defined, used - defined)
    check("picker.js only reads theme colors by name", "getPropertyValue" in js)

    from cogs.customization import custom_roles as cog_mod
    check("the Color form points to the picker", "Color picker" in cog_mod.COLOR_FORM_TIP)

    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())
