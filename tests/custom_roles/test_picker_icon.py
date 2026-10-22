"""Offline Milestone 8 checks: role icon originals and crops, the 256/128/64 output, the SSRF-safe
link fetcher, the icon APIs (upload, link, emoji, edit current crop, remove) and the image CSP."""
import asyncio
import io
import json
import re
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

import aiohttp  # noqa: E402
import discord  # noqa: E402
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from fakes import FakeGuild, FakeIconAsset, FakeMember  # noqa: E402
from PIL import Image  # noqa: E402

GID = 9
assert GID in _safety.TEST_GUILD_IDS
results = []


def check(label, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))


def encode(img, fmt="PNG", **kw):
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


def quarters(size=600):
    """Red top-left, green top-right, blue bottom-left, white bottom-right."""
    img = Image.new("RGB", (size, size))
    h = size // 2
    for box, colour in (((0, 0, h, h), (255, 0, 0)), ((h, 0, size, h), (0, 255, 0)),
                        ((0, h, h, size), (0, 0, 255)), ((h, h, size, size), (255, 255, 255))):
        img.paste(colour, box)
    return img


def noise(side):
    return Image.frombytes("RGBA", (side, side), os.urandom(side * side * 4))


PNG_OK = encode(quarters())
AVATAR = encode(Image.new("RGB", (32, 32), (88, 101, 242)))


class FakeAvatar:
    url = "https://cdn.discordapp.com/avatars/9/a.png?size=128"

    def replace(self, **kw):
        return self

    async def read(self):
        return AVATAR


def with_avatar(member):
    member.guild_avatar, member.avatar, member.default_avatar = None, FakeAvatar(), FakeAvatar()
    return member


async def main():
    import config
    import database as db
    from helpers.custom_roles import images, safe_fetch, service, storage, tokens
    from web import custom_role_picker
    from web.dashboard import DashboardWebServer

    q = db.execute_db_operation
    await db.init_custom_roles_tables()

    async def reset():
        for table in ("custom_role_records", "custom_role_guild_settings", "custom_role_pending_removals", "custom_role_archive_snoozes"):
            await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))
        tokens.clear()

    async def setup(features=()):
        await reset()
        g = FakeGuild(GID, features)
        await service.set_anchor(g, g.anchor)
        await service.set_enabled(g, True)
        await storage.update_guild_settings(GID, log_channel_id=g.channel.id)
        return g

    # ================================================================== images: originals, crops, sizes
    check("default original limit is 8 MB", config.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES == 8 * 1024 * 1024)
    icon = images.make_icon(PNG_OK)
    out = Image.open(io.BytesIO(icon.png))
    check("big centre crop -> 256x256 PNG", out.format == "PNG" and out.size == (256, 256) and icon.side == 256)
    check("centre crop recorded in the original's pixels", icon.crop == (0, 0, 600))
    icon = images.make_icon(PNG_OK, (0, 0, 300))
    px = Image.open(io.BytesIO(icon.png)).convert("RGB").getpixel((128, 128))
    check("crop square is cut where asked (top-left = red)", px == (255, 0, 0) and icon.crop == (0, 0, 300), px)
    icon = images.make_icon(PNG_OK, (300, 300, 300))
    px = Image.open(io.BytesIO(icon.png)).convert("RGB").getpixel((128, 128))
    check("bottom-right crop = white", px == (255, 255, 255), px)
    check("crop of 200 px -> 128 (never upscaled past the crop)", images.make_icon(PNG_OK, (0, 0, 200)).side == 128)
    check("crop of 100 px -> 64", images.make_icon(PNG_OK, (0, 0, 100)).side == 64)
    check("tiny crop (20 px) -> 64 (Discord's minimum)", images.make_icon(PNG_OK, (0, 0, 20)).side == 64)
    for bad, label in (((550, 0, 100), "past the right edge"), ((-1, 0, 100), "negative x"), ((0, 0, 8), "smaller than 16 px"),
                       ((0, 0, 601), "bigger than the image"), (("a", 0, 100), "not numbers")):
        try:
            images.make_icon(PNG_OK, bad)
            check(f"crop refused: {label}", False)
        except images.ImageError as exc:
            check(f"crop refused: {label}", "crop" in exc.message, exc.message)

    big_noise = encode(noise(256))  # already 256 px, so nothing smooths it
    icon = images.make_icon(big_noise)
    check("256 px over 256 KB -> falls back to 128 (largest that fits)", icon.side == 128 and len(icon.png) <= images.MAX_ICON_BYTES,
          (icon.side, len(icon.png)))
    check("LANCZOS PNG output stays under Discord's 256 KB", len(images.make_icon(PNG_OK).png) <= images.MAX_ICON_BYTES)

    # originals: up to 8 MB accepted, kept exactly; pixel/bomb limits unchanged
    large = encode(noise(1100), "PNG")  # ~4.8 MB, incompressible
    check("setup: original over 256 KB", len(large) > 4 * 1024 * 1024, len(large))
    check("a several-MB original is accepted", images.make_icon(large).side == 256)
    old_limit = config.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES
    config.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES = 1024 * 1024
    try:
        images.make_icon(large)
        check("over the (configurable) original limit refused", False)
    except images.ImageError as exc:
        check("over the (configurable) original limit refused", "1 MB" in exc.message, exc.message)
    config.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES = old_limit
    for data, words, label in ((encode(Image.new("RGB", (9000, 10))), "9000 px wide", "9000 px wide"),
                               (encode(Image.new("1", (20000, 20000))), "far too large in pixels", "pixel bomb"),
                               (b"GIF89a....", "PNG or JPEG", "GIF")):
        try:
            images.make_icon(data)
            check(f"still refused: {label}", False)
        except images.ImageError as exc:
            check(f"still refused: {label}", words in exc.message, exc.message)

    # ================================================================== pixel limits (Milestone 9) and HEIC
    check("limits: 8192 px a side, 16 million pixels", (images.MAX_ICON_SIDE, images.MAX_ICON_PIXELS) == (8192, 16_000_000))
    check("8192 px wide is accepted", images.inspect_source(encode(Image.new("RGB", (8192, 100)))) == ("PNG", 8192, 100))
    check("the Eiffel photo's size (2900x5367) is accepted now",
          images.inspect_source(encode(Image.new("RGB", (2900, 5367)), "JPEG")) == ("JPEG", 2900, 5367))
    check("12 MP phone photo size (4032x3024) is accepted", images.pixel_limit_error(4032, 3024) is None)
    rotated_tall = Image.Exif()
    rotated_tall[0x0112] = 6
    for data, expected, label in (
        (encode(Image.new("RGB", (9000, 50))), "This image is 9000 px wide; the limit is 8192 px per side.", "too wide"),
        (encode(Image.new("RGB", (50, 9000))), "This image is 9000 px tall; the limit is 8192 px per side.", "too tall"),
        (encode(Image.new("RGB", (9000, 100)), "JPEG", exif=rotated_tall.tobytes()),
         "This image is 9000 px tall; the limit is 8192 px per side.", "phone photo turned upright is named as tall"),
        (encode(Image.new("1", (9000, 9000))),
         "This image is 9000x9000 px; the limit is 8192 px per side. Try a 12 MP photo or a screenshot.", "both sides"),
        (encode(Image.new("1", (8064, 6048))),
         "This image is 8064x6048 px (48.8 million pixels); the limit is 16 million pixels. Try a 12 MP photo or a screenshot.",
         "48 MP photo"),
        (encode(Image.new("1", (4000, 4001))),
         "This image is 4000x4001 px (16.1 million pixels); the limit is 16 million pixels. Try a 12 MP photo or a screenshot.",
         "just over 16 MP (rounded up, never '16.0')"),
    ):
        try:
            images.inspect_source(data)
            check(f"pixel limit message: {label}", False)
        except images.ImageError as exc:
            check(f"pixel limit message: {label}", exc.message == expected, exc.message)
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + os.urandom(200)
    heif = b"\x00\x00\x00\x10ftypmif1\x00\x00\x00\x00" + os.urandom(200)
    avif = b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00avifmif1miaf" + os.urandom(200)
    check("HEIC/HEIF recognised by bytes, AVIF and PNG aren't",
          images.is_heif(heic) and images.is_heif(heif) and not images.is_heif(avif) and not images.is_heif(PNG_OK))
    for data, expected, label in ((heic, images.HEIC_MESSAGE, "HEIC"), (heif, images.HEIC_MESSAGE, "HEIF"),
                                  (avif, images.TYPE_MESSAGE, "AVIF (not called HEIC)")):
        try:
            images.make_icon(data)
            check(f"refused with the right message: {label}", False)
        except images.ImageError as exc:
            check(f"refused with the right message: {label}", exc.message == expected, exc.message)
    check("HEIC message wording", images.HEIC_MESSAGE == "iPhone HEIC photos aren't supported. Save it as JPEG or PNG "
          "(or take a screenshot) and try again.")
    try:
        images.check_attachment_metadata("image/heic", False)
        check("/custom-role icon: Discord's image/heic type gets the HEIC message", False)
    except images.ImageError as exc:
        check("/custom-role icon: Discord's image/heic type gets the HEIC message", exc.message == images.HEIC_MESSAGE)

    # phone photo rotation: crop coordinates are in the picture as displayed
    rot = Image.new("RGB", (300, 200), (0, 0, 255))
    rot.paste((255, 0, 0), (0, 0, 150, 200))  # left half red
    exif = Image.Exif()
    exif[0x0112] = 6  # shown rotated 90° clockwise -> 200x300, red on top
    jpeg = encode(rot, "JPEG", exif=exif.tobytes(), quality=95)
    check("inspect_source reports the displayed size (rotated)", images.inspect_source(jpeg) == ("JPEG", 200, 300),
          images.inspect_source(jpeg))
    top = Image.open(io.BytesIO(images.make_icon(jpeg, (0, 0, 200)).png)).convert("RGB").getpixel((64, 64))
    bottom = Image.open(io.BytesIO(images.make_icon(jpeg, (0, 100, 200)).png)).convert("RGB").getpixel((64, 64))
    check("crop on a rotated photo uses displayed coordinates", top[0] > 200 and top[2] < 80 and bottom[2] > 200, (top, bottom))

    # ================================================================== link safety: URL and address rules
    for url, words, label in (
        ("http://example.com/a.png", "https://", "plain http"),
        ("ftp://example.com/a.png", "https://", "ftp"),
        ("https://user:pw@example.com/a.png", "username", "credentials in the link"),
        ("https://example.com:8443/a.png", "443", "another port"),
        ("https://localhost/a.png", "private", "localhost"),
        ("https://foo.localhost/a.png", "private", "*.localhost"),
        ("https://exa mple.com/a.png", "spaces", "spaces"),
        ("https://" + "a" * 2050 + ".com/", "too long", "over 2048 characters"),
        ("", "Paste", "empty"),
        (None, "Paste", "not text"),
    ):
        try:
            safe_fetch.check_url(url)
            check(f"link refused: {label}", False)
        except safe_fetch.FetchError as exc:
            check(f"link refused: {label}", words in exc.message, exc.message)
    check("https on 443 (explicit) accepted", safe_fetch.check_url("https://example.com:443/a.png")[1] == "example.com")

    allowed = {"8.8.8.8": True, "2606:4700:4700::1111": True, "::ffff:8.8.8.8": True, "64:ff9b::808:808": True,
               "127.0.0.1": False, "10.1.2.3": False, "172.16.0.1": False, "192.168.1.1": False, "169.254.169.254": False,
               "100.64.0.1": False, "0.0.0.0": False, "224.0.0.1": False, "233.252.0.1": False, "255.255.255.255": False,
               "198.18.0.1": False, "192.0.2.1": False, "::1": False, "fe80::1": False, "fc00::1": False,
               "::ffff:127.0.0.1": False, "::ffff:10.0.0.1": False, "64:ff9b::7f00:1": False, "64:ff9b::a00:1": False,
               "2002:7f00:1::": False, "2002:c0a8:101::": False, "2001:0:4136:e378:8000:63bf:3fff:fdd2": False,
               "::127.0.0.1": False, "fe80::1%eth0": False, "not-an-ip": False}
    wrong = {a: want for a, want in allowed.items() if safe_fetch.address_allowed(a) != want}
    check(f"allow-list: {len(allowed)} addresses (public only; 6to4/NAT64/Teredo/mapped unwrapped)", not wrong, wrong)

    for url in ("https://127.0.0.1/a.png", "https://192.168.1.1/a.png", "https://10.0.0.1/x.png", "https://[::1]/a.png",
                "https://169.254.169.254/latest/meta-data/", "https://[::ffff:127.0.0.1]/a.png", "https://[64:ff9b::7f00:1]/a.png",
                "https://[2002:7f00:1::]/a.png", "https://0.0.0.0/a.png", "https://2130706433/a.png"):
        try:
            await safe_fetch.fetch_image(url, 1024 * 1024)
            check(f"private target refused before connecting: {url}", False)
        except safe_fetch.FetchError as exc:
            # A decimal IP resolves to 127.0.0.1 on Linux (-> "private") but not at all on Windows (-> "couldn't find").
            expected = {safe_fetch.PRIVATE_MESSAGE} | ({"I couldn't find that website. Check the link."} if "2130706433" in url else set())
            check(f"private target refused before connecting: {url}", exc.message in expected, exc.message)

    loop = asyncio.get_running_loop()
    real_getaddrinfo = loop.getaddrinfo

    async def mixed(host, port, **kw):
        return [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("10.0.0.5", 443))]
    loop.getaddrinfo = mixed
    try:
        await safe_fetch.resolve_public("rebind.example")
        check("DNS answer with ANY private address refused", False)
    except safe_fetch.FetchError as exc:
        check("DNS answer with ANY private address refused", exc.message == safe_fetch.PRIVATE_MESSAGE)

    async def public(host, port, **kw):
        return [(2, 1, 6, "", ("93.184.216.34", 443)), (10, 1, 6, "", ("2606:2800:220:1::1", 443, 0, 0))]
    loop.getaddrinfo = public
    check("all-public DNS answer accepted", await safe_fetch.resolve_public("ok.example") == ["2606:2800:220:1::1", "93.184.216.34"])
    loop.getaddrinfo = real_getaddrinfo

    pinned = safe_fetch.PinnedResolver("ok.example", ["93.184.216.34", "2606:2800:220:1::1"])
    got = await pinned.resolve("ok.example", 443, 0)
    check("pinned resolver hands out only the checked addresses", sorted(r["host"] for r in got) == ["2606:2800:220:1::1", "93.184.216.34"])
    got4 = await pinned.resolve("ok.example", 443, __import__("socket").AF_INET)
    check("pinned resolver respects the address family", [r["host"] for r in got4] == ["93.184.216.34"])
    try:
        await pinned.resolve("other.example", 443, 0)
        check("pinned resolver refuses any other host", False)
    except OSError:
        check("pinned resolver refuses any other host", True)

    # ================================================================== link fetching against a local test site
    limit = 300 * 1024
    big_body = os.urandom(limit + 10)

    async def ok_png(request):
        return web.Response(body=PNG_OK, content_type="image/png")

    async def ok_jpg(request):
        return web.Response(body=jpeg, content_type="image/jpeg")

    async def redirect(request):
        raise web.HTTPFound("/ok.png")

    async def html(request):
        return web.Response(text="<html>not an image</html>", content_type="text/html")

    async def declared_big(request):
        return web.Response(body=big_body, content_type="image/png")

    async def chunked_big(request):
        response = web.StreamResponse(headers={"Content-Type": "image/png"})
        response.enable_chunked_encoding()
        await response.prepare(request)
        for _ in range(8):
            await response.write(os.urandom(64 * 1024))
        return response

    async def slow(request):
        await asyncio.sleep(3)
        return web.Response(body=PNG_OK, content_type="image/png")

    async def fake_png(request):
        return web.Response(body=b"this is not a picture", content_type="image/png")

    async def missing(request):
        return web.Response(status=404, text="nope")

    async def heic_photo(request):
        return web.Response(body=b"\x00\x00\x00\x18ftypheic" + bytes(100), content_type="image/heic")

    site = web.Application()
    for path, handler in (("/ok.png", ok_png), ("/ok.jpg", ok_jpg), ("/redirect", redirect), ("/page", html),
                          ("/declared-big.png", declared_big), ("/chunked-big.png", chunked_big), ("/slow.png", slow),
                          ("/fake.png", fake_png), ("/missing.png", missing), ("/photo.heic", heic_photo)):
        site.router.add_get(path, handler)
    server = TestServer(site, host="127.0.0.1")
    await server.start_server()
    seen_hosts = []

    async def to_local(host):
        seen_hosts.append(host)
        return ["127.0.0.1"]

    opts = {"resolve": to_local, "allow_http": True, "allowed_port": server.port}
    base = f"http://picker-test.example:{server.port}"
    data, kind, host = await safe_fetch.fetch_image(f"{base}/ok.png", limit, **opts)
    check("fetch: PNG downloaded through the pinned address (name never looked up for real)",
          data == PNG_OK and kind == "PNG" and host == "picker-test.example" and seen_hosts == ["picker-test.example"])
    data, kind, _ = await safe_fetch.fetch_image(f"{base}/ok.jpg", limit, **opts)
    check("fetch: JPEG downloaded", data == jpeg and kind == "JPEG")
    for path, words, label in (("/redirect", "redirects", "redirect (302)"), ("/page", "isn't a PNG or JPEG", "web page"),
                               ("/declared-big.png", "larger than", "Content-Length over the limit"),
                               ("/chunked-big.png", "larger than", "no Content-Length, cut off while streaming"),
                               ("/missing.png", "error (404)", "404"), ("/photo.heic", "iPhone HEIC photos", "HEIC photo")):
        try:
            await safe_fetch.fetch_image(f"{base}{path}", limit, **opts)
            check(f"fetch refused: {label}", False)
        except safe_fetch.FetchError as exc:
            check(f"fetch refused: {label}", words in exc.message, exc.message)
    started = time.monotonic()
    try:
        await safe_fetch.fetch_image(f"{base}/slow.png", limit, timeout=0.5, **opts)
        check("fetch refused: too slow", False)
    except safe_fetch.FetchError as exc:
        check("fetch refused: too slow (time limit covers the whole fetch)", "too long" in exc.message
              and time.monotonic() - started < 2, exc.message)
    check("link time limit is 10 seconds", safe_fetch.LINK_TIMEOUT == 10.0)

    # ================================================================== icon APIs
    config.CUSTOM_ROLES_PICKER_ENABLED = True
    config.CUSTOM_ROLES_PUBLIC_URL = "http://localhost:8080"
    config.DASHBOARD_CLIENT_ID = config.DASHBOARD_CLIENT_SECRET = config.DASHBOARD_SECRET_KEY = None
    guilds = {}
    bot = SimpleNamespace(get_guild=lambda gid: guilds.get(gid), custom_role_picker_ready=True)
    app = DashboardWebServer(bot).build_app()
    picker = next(mw.__self__ for mw in app.middlewares if type(getattr(mw, "__self__", None)).__name__ == "CustomRolePicker")
    picker.fetch_options = opts
    client = TestClient(TestServer(app))
    await client.start_server()

    async def call(method, path, token, body=None, form=None, headers=None):
        h = {"Authorization": f"Bearer {token}"} if token else {}
        h.update(headers or {})
        kw = {}
        if body is not None:
            kw["json"] = body
        if form is not None:
            kw["data"] = form
        r = await client.request(method, path, headers=h, **kw)
        return r

    def upload_form(image, crop=None):
        form = aiohttp.FormData()
        form.add_field("image", image, filename="original", content_type="application/octet-stream")
        if crop is not None:
            form.add_field("crop", json.dumps(crop))
        return form

    try:
        g = await setup(features=["ROLE_ICONS"])
        guilds[GID] = g
        m = with_avatar(FakeMember(g, booster=True, name="iconic"))
        await service.create_role(m, "Icon Role")
        role = g.get_role((await storage.get_custom_role(GID, m.id)).role_id)
        tok, _ = tokens.create(GID, m.id)

        r = await call("GET", "/custom-roles", None)
        csp = r.headers["Content-Security-Policy"]
        img_src = next(part.strip() for part in csp.split(";") if part.strip().startswith("img-src"))
        check("CSP: images only from 'self', data: and blob: (no remote URLs)", img_src == "img-src 'self' data: blob:", csp)

        r = await call("GET", "/custom-roles/api/state", tok)
        state = (await r.json())["state"]
        check("avatar sent as a data: URL (no remote images on the page)", state["user"]["avatar_url"].startswith("data:image/png;base64,"))
        check("state lists the original size limit", state["icon_source_max"] == config.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES)
        check("no http(s) URL anywhere in the state", "http" not in json.dumps(state).replace("http://localhost", ""), state)

        r = await call("POST", "/custom-roles/api/icon", tok, form=upload_form(PNG_OK, {"x": 300, "y": 0, "size": 300}))
        body = await r.json()
        rec = await storage.get_custom_role(GID, m.id)
        applied = Image.open(io.BytesIO(role.display_icon.data)).convert("RGB") if isinstance(role.display_icon, FakeIconAsset) else None
        check("upload + crop: icon set on the role", r.status == 200 and body["ok"] and applied is not None
              and applied.size == (256, 256) and applied.getpixel((128, 128)) == (0, 255, 0), (r.status, body.get("message")))
        check("original stored exactly as uploaded (byte for byte)", rec.icon_source == PNG_OK)
        check("crop stored relative to the original", json.loads(rec.icon_crop) == {"x": 300, "y": 0, "size": 300})
        check("state: icon has a source and its crop (for Edit current crop)",
              body["state"]["role"]["icon"]["has_source"] and body["state"]["role"]["icon"]["crop"] == {"x": 300, "y": 0, "size": 300})
        check("icon in state is a data: URL", body["state"]["role"]["icon"]["url"].startswith("data:image/png;base64,"))
        check("icon change logged with the role name", any("set the icon of" in t and "(`Icon Role`)" in t for t in g.channel.texts()))

        r = await call("GET", "/custom-roles/api/icon/source", tok)
        check("Edit current crop: the original comes back untouched", r.status == 200 and await r.read() == PNG_OK
              and r.headers["Content-Type"].startswith("image/png") and r.headers.get("X-Picker-Expires-At"))

        lists = await storage.list_roles(GID)
        check("list queries don't load images (originals can be MB)", lists and lists[0].icon_source is None and lists[0].icon_png is None)

        # restore keeps the original and crop (upserts never touch them)
        m.premium_since = None
        await service.archive(g, m.id, "test")
        m.premium_since = discord.utils.utcnow()
        await service.restore(m, dm=False)
        rec = await storage.get_custom_role(GID, m.id)
        check("archive + restore keep the original and the crop", rec.icon_source == PNG_OK and json.loads(rec.icon_crop)["x"] == 300
              and rec.status == "active")
        role = g.get_role(rec.role_id)
        tok, _ = tokens.create(GID, m.id)

        for crop, label in (({"x": 500, "y": 0, "size": 300}, "outside the image"), ({"x": 0, "y": 0}, "missing size"),
                            ({"x": 0.5, "y": 0, "size": 100}, "not whole numbers"), ({"x": True, "y": 0, "size": 100}, "true/false")):
            r = await call("POST", "/custom-roles/api/icon", tok, form=upload_form(PNG_OK, crop))
            body = await r.json()
            check(f"bad crop refused: {label}", (r.status == 400 and body["error"] == "bad_crop") or (r.status == 200 and not body["ok"]),
                  (r.status, body))
        r = await call("POST", "/custom-roles/api/icon", tok, form=upload_form(b"hello"))
        check("non-image upload refused with the usual message", not (await r.json())["ok"])
        r = await call("POST", "/custom-roles/api/icon", tok, body={"image": "x"})
        check("upload must be multipart (415)", r.status == 415)
        config.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES = 256 * 1024
        r = await call("POST", "/custom-roles/api/icon", tok, form=upload_form(large))
        check("upload over the original limit -> 413", r.status == 413 and "256 KB" in (await r.json())["message"])
        config.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES = old_limit
        r = await call("POST", "/custom-roles/api/icon", tok, form=upload_form(PNG_OK), headers={"Origin": "https://evil.example"})
        check("upload from another site -> 403", r.status == 403)
        r = await call("POST", "/custom-roles/api/icon", None, form=upload_form(PNG_OK))
        check("upload without the link -> 401", r.status == 401)

        r = await call("POST", "/custom-roles/api/icon", tok, form=upload_form(PNG_OK))
        rec = await storage.get_custom_role(GID, m.id)
        check("no crop sent -> centre square", (await r.json())["ok"] and json.loads(rec.icon_crop) == {"x": 0, "y": 0, "size": 600})

        # emoji
        r = await call("POST", "/custom-roles/api/icon/emoji", tok, body={"emoji": "🌙"})
        body = await r.json()
        rec = await storage.get_custom_role(GID, m.id)
        check("emoji icon set (same checks as /custom-role icon)", body["ok"] and role.display_icon == "🌙"
              and body["state"]["role"]["icon"] == {"type": "emoji", "value": "🌙"})
        check("emoji clears the stored original and crop", rec.icon_source is None and rec.icon_crop is None and rec.icon_png is None)
        r = await call("POST", "/custom-roles/api/icon/emoji", tok, body={"emoji": "hello"})
        check("text that isn't an emoji refused", not (await r.json())["ok"])
        r = await call("POST", "/custom-roles/api/icon/emoji", tok, body={"emoji": "🌙🌙"})
        check("two emoji refused", not (await r.json())["ok"])
        r = await call("POST", "/custom-roles/api/icon/emoji", tok, body={"emoji": 5})
        check("non-text emoji refused (400)", r.status == 400)
        r = await call("GET", "/custom-roles/api/icon/source", tok)
        check("Edit current crop with an emoji icon -> 404", r.status == 404)

        # remove
        await call("POST", "/custom-roles/api/icon", tok, form=upload_form(PNG_OK))
        r = await call("DELETE", "/custom-roles/api/icon", tok)
        body = await r.json()
        rec = await storage.get_custom_role(GID, m.id)
        check("remove: icon gone, original and crop cleared", body["ok"] and role.display_icon is None
              and rec.icon_source is None and rec.icon_crop is None and body["state"]["role"]["icon"] is None)
        r = await call("DELETE", "/custom-roles/api/icon", tok, headers={"Origin": "https://evil.example"})
        check("remove from another site -> 403", r.status == 403)

        # link fetch through the API
        r = await call("POST", "/custom-roles/api/icon/fetch", tok, body={"url": f"{base}/ok.png"})
        check("fetch API returns the image bytes for the crop editor (nothing applied)",
              r.status == 200 and await r.read() == PNG_OK and r.headers["Content-Type"].startswith("image/png")
              and role.display_icon is None and r.headers.get("X-Picker-Expires-At"))
        r = await call("POST", "/custom-roles/api/icon/fetch", tok, body={"url": f"{base}/redirect"})
        check("fetch API: redirect refused (422)", r.status == 422 and "redirects" in (await r.json())["message"])
        r = await call("POST", "/custom-roles/api/icon/fetch", tok, body={"url": f"{base}/fake.png"})
        check("fetch API: image/png that isn't a picture refused", r.status == 422 and (await r.json())["error"] == "bad_image")
        picker.fetch_options = {}
        r = await call("POST", "/custom-roles/api/icon/fetch", tok, body={"url": "https://127.0.0.1/a.png"})
        check("fetch API: private address refused", r.status == 422 and "private" in (await r.json())["message"])
        r = await call("POST", "/custom-roles/api/icon/fetch", tok, body={"url": "http://example.com/a.png"})
        check("fetch API: http refused", r.status == 422 and "https" in (await r.json())["message"])
        picker.fetch_options = opts
        picker._fetches.clear()
        tok, _ = tokens.create(GID, m.id)  # fresh link: this one already used its 20 writes a minute

        old_fetch_limit = custom_role_picker.FETCH_LIMIT
        custom_role_picker.FETCH_LIMIT = 2
        statuses = [(await call("POST", "/custom-roles/api/icon/fetch", tok, body={"url": f"{base}/ok.png"})).status for _ in range(3)]
        check("fetch API: per-member limit -> 429", statuses == [200, 200, 429], statuses)
        custom_role_picker.FETCH_LIMIT = old_fetch_limit
        picker._fetches.clear()
        tok, _ = tokens.create(GID, m.id)
        for _ in range(custom_role_picker.FETCH_CONCURRENCY):
            await picker._fetch_slots.acquire()
        r = await call("POST", "/custom-roles/api/icon/fetch", tok, body={"url": f"{base}/ok.png"})
        check("fetch API: global concurrency limit -> 503 busy", r.status == 503 and (await r.json())["error"] == "busy")
        for _ in range(custom_role_picker.FETCH_CONCURRENCY):
            picker._fetch_slots.release()

        # without the Role Icons perk
        g2 = await setup()
        guilds[GID] = g2
        n = with_avatar(FakeMember(g2, booster=True, name="noperk"))
        await service.create_role(n, "No Perk")
        tok2, _ = tokens.create(GID, n.id)
        r = await call("POST", "/custom-roles/api/icon/fetch", tok2, body={"url": f"{base}/ok.png"})
        check("no perk: links aren't fetched at all (403)", r.status == 403 and (await r.json())["error"] == "no_icons")
        r = await call("POST", "/custom-roles/api/icon", tok2, form=upload_form(PNG_OK))
        body = await r.json()
        check("no perk: upload checked, then refused with 'Your image is fine'", not body["ok"] and "Your image is fine" in body["message"])
        r = await call("POST", "/custom-roles/api/icon/emoji", tok2, body={"emoji": "🌙"})
        check("no perk: emoji checked, then refused", "Your emoji is fine" in (await r.json())["message"])

        config.CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS = True
        r = await call("GET", "/custom-roles/api/state", tok2)
        check("test switch: page told to unlock the icon tab", (await r.json())["state"]["guild"]["preview_icons"] is True)
        r = await call("POST", "/custom-roles/api/icon/fetch", tok2, body={"url": f"{base}/ok.png"})
        check("test switch: link fetch works for testing", r.status == 200)
        r = await call("POST", "/custom-roles/api/icon", tok2, form=upload_form(PNG_OK))
        check("test switch: setting the icon is still refused", "Your image is fine" in (await r.json())["message"])
        os.environ["ENVIRONMENT"] = "production"
        r = await call("GET", "/custom-roles/api/state", tok2)
        check("test switch ignored in production", (await r.json())["state"]["guild"]["preview_icons"] is False)
        os.environ["ENVIRONMENT"] = "development"
        from cogs.customization.custom_roles import CustomRoles
        switches = {name: (is_set, on) for name, is_set, on, _, _ in CustomRoles._debug_switches()}
        check("startup warning knows CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS", switches["CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS"] == (True, True))
        config.CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS = False

        # /custom-role icon (the command) keeps the original too
        g3 = await setup(features=["ROLE_ICONS"])
        guilds[GID] = g3
        c = with_avatar(FakeMember(g3, booster=True, name="cmd"))
        await service.create_role(c, "Cmd Role")
        result = await service.set_icon(c, image=large)
        rec = await storage.get_custom_role(GID, c.id)
        check("/custom-role icon path: several-MB original kept with a centre crop",
              result.ok and rec.icon_source == large and json.loads(rec.icon_crop) == {"x": 0, "y": 0, "size": 1100}, result.message)
        check("/custom-role icon path: final icon is 256 px (or the largest that fits)", "256x256" in result.message or "128x128" in result.message,
              result.message)
    finally:
        await client.close()
        await server.close()

    static = _safety.REPO / "web" / "static" / "custom_roles"
    html_text = (static / "picker.html").read_text(encoding="utf-8")
    for needle, label in (('name="icon-source"', "Upload / Link / Emoji switch"), ('id="icon-file"', "file input"),
                          ('id="dropzone"', "drop zone"), ('id="icon-url"', "link box"), ('id="emoji-input"', "emoji box"),
                          ('id="crop-stage"', "crop area"), ('id="crop-zoom"', "zoom slider"), ('id="edit-crop"', "Edit current crop"),
                          ('id="remove-icon"', "Remove current icon"), ('id="set-icon"', "Set icon")):
        check(f"icon tab has: {label}", needle in html_text)
    check("drop zone text from the spec", "Drop an image here, or click to browse" in html_text)
    check("link help text from the spec", "Links that redirect won't work, so paste the image's own address." in html_text)
    js = (static / "picker.js").read_text(encoding="utf-8")
    check("picker.js sends the original + crop, never re-encodes it", 'form.append("image", iconEdit.blob' in js
          and "toBlob" not in js)
    check("picker.js reads the size from the header BEFORE the browser decodes the image",
          0 < js.index("headerSize(head, isPng)") < js.index("URL.createObjectURL(blob)"))
    check("picker.js uses the same limits and messages as the server",
          "const MAX_SIDE = 8192;" in js and "const MAX_PIXELS = 16000000;" in js
          and f'const PHOTO_HINT = "{images.PHOTO_HINT}";' in js and f'const HEIC_MESSAGE = "{images.HEIC_MESSAGE}";' in js)
    check("the only canvas is the 128 px preview (far under iPhone Safari's ~16.7 MP canvas limit)",
          js.count('createElement("canvas")') == 1 and "const PREVIEW_SIDE = 128;" in js)
    check("picker.js doesn't wait on decode() or animation frames (they stall in background tabs)",
          not re.search(r"\.decode\s*\(", js) and not re.search(r"requestAnimationFrame\s*\(", js))

    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node")
    if node:
        work = tempfile.mkdtemp(prefix="custom_role_header_")
        samples = {
            "bomb.png": encode(Image.new("1", (20000, 20000))),
            "wide.png": encode(Image.new("RGB", (9000, 10))),
            "ok.png": PNG_OK,
            "ok.jpg": jpeg,  # 300x200 stored, shown turned upright (EXIF orientation 6)
            "big-endian-exif.jpg": encode(Image.new("RGB", (300, 200)), "JPEG",
                                          exif=b"Exif\x00\x00MM\x00\x2a\x00\x00\x00\x08\x00\x01\x01\x12\x00\x03"
                                               b"\x00\x00\x00\x01\x00\x08\x00\x00\x00\x00\x00\x00"),
            "progressive.jpg": encode(quarters(320), "JPEG", progressive=True),
            "photo.heic": heic,
            "photo.avif": avif,
        }
        for name, data in samples.items():
            with open(os.path.join(work, name), "wb") as f:
                f.write(data)
        limit_cases = [(9000, 50), (50, 9000), (9000, 9000), (8064, 6048), (4000, 4001), (8192, 1953), (4032, 3024),
                       (8192, 8192), (1, 16_000_000), (16_000_001, 1)]
        with open(os.path.join(work, "cases.json"), "w", encoding="utf-8") as f:
            json.dump(limit_cases, f)
        script = os.path.join(work, "run.js")
        with open(script, "w", encoding="utf-8") as f:
            f.write(
                'const fs = require("fs");\n'
                'const src = fs.readFileSync(process.argv[2], "utf8").split("\\r\\n").join("\\n");\n'
                '// the image-checking block: constants, headerSize, exifOrientation, isHeif, pixelLimitError\n'
                'const start = src.indexOf("  const PNG_SIGNATURE");\n'
                'const last = src.indexOf("  function pixelLimitError(");\n'
                'const end = src.indexOf("\\n  }\\n", last) + 4;\n'
                'const lib = new Function(src.slice(start, end) + "\\nreturn { headerSize, isHeif, pixelLimitError };")();\n'
                "const out = { sizes: {}, heif: {}, limits: [] };\n"
                "for (const file of process.argv.slice(4)) {\n"
                "  const b = fs.readFileSync(file);\n"
                "  const bytes = new Uint8Array(b.buffer, b.byteOffset, Math.min(b.length, 262144));\n"
                "  const name = file.split(/[\\\\/]/).pop();\n"
                "  out.heif[name] = lib.isHeif(bytes);\n"
                "  if (bytes[0] === 0x89 || bytes[0] === 0xFF) { out.sizes[name] = lib.headerSize(bytes, bytes[0] === 0x89); }\n"
                "}\n"
                'for (const [w, h] of JSON.parse(fs.readFileSync(process.argv[3], "utf8"))) { out.limits.push(lib.pixelLimitError(w, h)); }\n'
                "console.log(JSON.stringify(out));\n"
            )
        proc = subprocess.run([node, script, str(static / "picker.js"), os.path.join(work, "cases.json"),
                               *(os.path.join(work, n) for n in samples)],
                              capture_output=True, text=True, timeout=60)
        result = json.loads(proc.stdout or "{}")
        expected = {"bomb.png": {"w": 20000, "h": 20000}, "wide.png": {"w": 9000, "h": 10}, "ok.png": {"w": 600, "h": 600},
                    "ok.jpg": {"w": 200, "h": 300}, "big-endian-exif.jpg": {"w": 200, "h": 300},
                    "progressive.jpg": {"w": 320, "h": 320}}
        check("header sizes read correctly in JS (PNG, JPEG upright via EXIF in both byte orders, progressive, bomb)",
              result.get("sizes") == expected, (result.get("sizes"), proc.stderr[-300:]))
        check("JS spots HEIC by its bytes, not AVIF/PNG/JPEG",
              result.get("heif") == {n: n == "photo.heic" for n in samples}, result.get("heif"))
        python_limits = [images.pixel_limit_error(w, h) for w, h in limit_cases]
        check("JS pixel-limit messages match the server's word for word", result.get("limits") == python_limits,
              list(zip(result.get("limits") or [], python_limits)))
    else:
        print("SKIP node not installed: JS header-size check not run")

    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())
