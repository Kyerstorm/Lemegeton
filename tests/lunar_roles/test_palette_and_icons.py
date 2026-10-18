"""Offline Milestone 4 checks: icons (image + emoji), palette, select menus."""
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

import discord  # noqa: E402
from discord.asset import Asset  # noqa: E402
from PIL import Image  # noqa: E402
from fakes import FakeGuild, FakeMember, FakeIconAsset  # noqa: E402

GID = 5
assert GID in _safety.TEST_GUILD_IDS
results = []


def check(label, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))


def png_bytes(img, fmt="PNG", **kw):
    out = io.BytesIO()
    img.save(out, format=fmt, **kw)
    return out.getvalue()


async def main():
    import config
    import database as db
    from helpers.lunar_roles import images, service, storage

    q = db.execute_db_operation
    await db.init_lunar_roles_tables()
    config.LUNAR_MASS_ARCHIVE_THRESHOLD = 10

    async def reset():
        for table in ("lunar_custom_roles", "lunar_guild_settings", "lunar_pending_removals", "lunar_archive_snoozes"):
            await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))

    async def setup(features=()):
        await reset()
        g = FakeGuild(GID, features)
        await service.set_anchor(g, g.anchor)
        await service.set_enabled(g, True)
        return g

    async def record(m):
        return await storage.get_custom_role(GID, m.id)

    # ------------------------------------------------------------ image preparation
    wide = Image.new("RGB", (1200, 400), (0, 0, 255))
    wide.paste((255, 255, 255), (500, 100, 700, 300))
    out = Image.open(io.BytesIO(images.prepare_icon(png_bytes(wide))))
    check("output is a 64x64 PNG", out.format == "PNG" and out.size == (64, 64))
    check("wide image: center square kept (white middle, blue sides)",
          out.getpixel((32, 32))[:3] == (255, 255, 255) and out.getpixel((2, 2))[:3] == (0, 0, 255))
    tall = Image.new("RGB", (100, 900), (0, 255, 0))
    check("tall image cropped to square", Image.open(io.BytesIO(images.prepare_icon(png_bytes(tall)))).size == (64, 64))

    rot = Image.new("RGB", (300, 200), (0, 0, 255))
    rot.paste((255, 0, 0), (0, 0, 150, 200))  # left half red
    exif = Image.Exif()
    exif[0x0112] = 6  # display rotated 90° clockwise -> left half ends up on top
    out = Image.open(io.BytesIO(images.prepare_icon(png_bytes(rot, "JPEG", exif=exif.tobytes(), quality=95))))
    top, bottom = out.getpixel((32, 4)), out.getpixel((32, 60))
    check("JPEG camera rotation applied", top[0] > 200 and top[2] < 80 and bottom[2] > 200, (top, bottom))

    for name, data, words in [
        ("over 256 KB", b"\x89PNG\r\n\x1a\n" + b"0" * (257 * 1024), "256 KB"),
        ("GIF content", png_bytes(Image.new("RGB", (8, 8)), "GIF"), "PNG or JPEG"),
        ("WebP content", png_bytes(Image.new("RGB", (8, 8)), "WEBP"), "PNG or JPEG"),
        ("text", b"hello", "PNG or JPEG"),
        ("cut off", png_bytes(Image.new("RGB", (64, 64), (9, 9, 9)))[:40], "couldn't read"),
        ("5000px wide", png_bytes(Image.new("RGB", (5000, 10))), "too large in pixels"),
        ("4096x4096+ pixel bomb", png_bytes(Image.new("1", (12000, 12000))), "too large in pixels"),
    ]:
        try:
            images.prepare_icon(data)
            check(f"refuses {name}", False)
        except images.ImageError as exc:
            check(f"refuses {name}", words in exc.message, exc.message)
    apng = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(apng, format="PNG", save_all=True,
                                             append_images=[Image.new("RGB", (8, 8), (4, 5, 6))])
    try:
        images.prepare_icon(apng.getvalue())
        check("refuses animated PNG", False)
    except images.ImageError as exc:
        check("refuses animated PNG", "Animated" in exc.message)
    try:
        images.check_declared_size(300 * 1024)
        check("declared size checked before download", False)
    except images.ImageError:
        check("declared size checked before download", True)

    # ------------------------------------------------------------ emoji check
    for good in ["🌙", "👍🏽", "🏳️‍🌈", "👨‍👩‍👧", "1️⃣", "🇵🇰", "❤️", " 🌙 "]:
        try:
            check(f"emoji ok: {good!r}", images.check_emoji(good) == good.strip())
        except images.ImageError as exc:
            check(f"emoji ok: {good!r}", False, exc.message)
    for bad in ["", "abc", "<:moon:123456>", "<a:spin:123>", ":crescent_moon:", "🌙🌙", "🇵🇰🇬🇧", "a🌙", "1"]:
        try:
            images.check_emoji(bad)
            check(f"emoji refused: {bad!r}", False)
        except images.ImageError:
            check(f"emoji refused: {bad!r}", True)

    # ------------------------------------------------------------ palette extraction
    avatar = Image.new("RGBA", (100, 100), (220, 30, 30, 255))     # red: most of it
    avatar.paste((30, 60, 220, 255), (0, 60, 100, 90))               # blue: 30%
    avatar.paste((40, 200, 60, 255), (0, 90, 100, 100))              # green: 10%
    avatar.paste((222, 32, 31, 255), (0, 0, 10, 10))                 # near-red: deduped
    avatar.paste((200, 0, 200, 0), (90, 0, 100, 60))                 # transparent purple: ignored
    colors = images.extract_palette(png_bytes(avatar))
    def near(c, rgb):
        return all(abs(((c >> s) & 255) - v) < 20 for s, v in zip((16, 8, 0), rgb))
    check("palette: most prominent first (red, blue, green)",
          len(colors) >= 3 and near(colors[0], (220, 30, 30)) and near(colors[1], (30, 60, 220)) and near(colors[2], (40, 200, 60)),
          [f"#{c:06X}" for c in colors])
    check("palette: near-duplicates dropped", sum(near(c, (220, 30, 30)) for c in colors) == 1, [f"#{c:06X}" for c in colors])
    check("palette: transparent pixels ignored", not any(near(c, (200, 0, 200)) for c in colors))
    check("palette: at most 25", len(images.extract_palette(png_bytes(Image.effect_noise((128, 128), 100).convert("RGB")))) <= 25)
    sw = Image.open(io.BytesIO(images.render_swatches(colors)))
    check("swatch image renders", sw.format == "PNG" and sw.width > 100)

    # ------------------------------------------------------------ which avatar
    class M:
        pass
    m = M()
    m.guild_avatar = Asset._from_guild_avatar(None, 1, 2, "a_guildhash")
    m.avatar = Asset._from_avatar(None, 2, "mainhash")
    m.default_avatar = Asset._from_default_avatar(None, 1)
    check("server avatar preferred, animated -> still png",
          "/guilds/1/users/2/avatars/a_guildhash.png?size=128" in service.palette_avatar(m).url, service.palette_avatar(m).url)
    m.guild_avatar = None
    m.avatar = Asset._from_avatar(None, 2, "a_animatedmain")
    check("main avatar next, animated -> still png", service.palette_avatar(m).url.endswith("/a_animatedmain.png?size=128"))
    m.avatar = None
    check("default avatar last", "/embed/avatars/1.png" in service.palette_avatar(m).url)

    # palette cache: second call doesn't download again
    reads = []

    class FakeAvatar:
        url = "https://cdn.test/avatars/1/abc.png?size=128"

        def replace(self, **kw):
            return self

        async def read(self):
            reads.append(1)
            return png_bytes(avatar)
    pm = M()
    pm.guild_avatar, pm.avatar, pm.default_avatar = None, FakeAvatar(), None
    pm.id = 1
    r1 = await service.get_palette(pm)
    r2 = await service.get_palette(pm)
    check("palette cached per avatar", r1.ok and r2.ok and len(reads) == 1 and r1.data == r2.data)

    # ------------------------------------------------------------ icons without the perk (Lunar Lab)
    g = await setup()
    m = FakeMember(g, booster=True, name="moon")
    await service.create_role(m, "Moon Role")
    ok_png = png_bytes(Image.new("RGB", (200, 200), (250, 240, 120)))
    r = await service.set_icon(m, image=ok_png)
    check("no perk: valid image -> 'image is fine, but… Boost Level 2'",
          not r.ok and r.message.startswith("Your image is fine") and "Boost Level 2" in r.message, r.message)
    r = await service.set_icon(m, image=b"GIF89a....")
    check("no perk: invalid image still gets the image error first", not r.ok and "PNG or JPEG" in r.message, r.message)
    r = await service.set_icon(m, emoji="🌙")
    check("no perk: valid emoji -> 'emoji is fine, but…'", not r.ok and r.message.startswith("Your emoji is fine"), r.message)
    r = await service.set_icon(m, emoji="<:moon:1>")
    check("no perk: custom emoji refused with emoji error", not r.ok and "Custom server emojis" in r.message)
    r = await service.remove_icon(m)
    check("no perk: remove without icon -> perk message", not r.ok and "Boost Level 2" in r.message, r.message)
    r = await service.set_icon(m, image=ok_png, emoji="🌙")
    check("image + emoji together refused", not r.ok and "not both" in r.message)
    other = FakeMember(g, booster=True, name="norole")
    r = await service.set_icon(other, emoji="🌙")
    check("no role yet -> told to run /lunar role", not r.ok and "/lunar role" in r.message)
    plain = FakeMember(g, name="plain")
    r = await service.set_icon(plain, emoji="🌙")
    check("non-booster refused", not r.ok and "boosters" in r.message)

    # ------------------------------------------------------------ icons with the perk
    g = await setup(features=["ROLE_ICONS"])
    m = FakeMember(g, booster=True, name="star")
    await service.create_role(m, "Star Role")
    role_id = (await record(m)).role_id
    r = await service.set_icon(m, image=ok_png)
    rec = await record(m)
    role = g.get_role(role_id)
    applied = Image.open(io.BytesIO(role.display_icon.data)) if isinstance(role.display_icon, FakeIconAsset) else None
    check("perk: image applied to the same role", r.ok and r.data.id == role_id and applied and applied.size == (64, 64), r.message)
    check("perk: PNG saved for restore", rec.icon_png == role.display_icon.data and rec.icon_emoji is None)
    r = await service.set_icon(m, emoji="🌙")
    rec = await record(m)
    check("perk: emoji replaces image", r.ok and role.display_icon == "🌙" and rec.icon_emoji == "🌙" and rec.icon_png is None)
    check("perk: emoji reply shows it", "🌙" in r.message)

    # hidden icon note
    badge = g.add_role("Staff Badge", role.position + 1)
    badge.display_icon = "⭐"
    m.roles.append(badge)
    r = await service.set_icon(m, emoji="🌙")
    check("icon Heads up when a higher role has an icon",
          r.ok and any("**Staff Badge** role is higher and has its own icon" in n for n in r.notes), r.notes)
    m.roles.remove(badge)

    # restore re-applies emoji, then image
    m.premium_since = None
    await service.archive(g, m.id, "stopped boosting")
    m.premium_since = discord.utils.utcnow()
    await service.restore(m)
    new_role = g.get_role((await record(m)).role_id)
    check("restore re-applies the saved emoji", new_role.display_icon == "🌙")
    await service.set_icon(m, image=ok_png)
    saved_png = (await record(m)).icon_png
    m.premium_since = None
    await service.archive(g, m.id, "stopped boosting")
    m.premium_since = discord.utils.utcnow()
    await service.restore(m)
    new_role = g.get_role((await record(m)).role_id)
    check("restore re-applies the saved image", isinstance(new_role.display_icon, FakeIconAsset)
          and new_role.display_icon.data == saved_png)

    # archive keeps an icon set outside the bot
    await q("c", "UPDATE lunar_custom_roles SET icon_png = NULL, icon_emoji = NULL WHERE guild_id = ? AND user_id = ?", (GID, m.id))
    g.get_role((await record(m)).role_id).display_icon = "🔥"
    m.premium_since = None
    await service.archive(g, m.id, "stopped boosting")
    check("archive saves an emoji set in Server Settings", (await record(m)).icon_emoji == "🔥")
    m.premium_since = discord.utils.utcnow()
    await service.restore(m)

    r = await service.remove_icon(m)
    rec = await record(m)
    check("remove icon clears role and saved icon",
          r.ok and g.get_role(rec.role_id).display_icon is None and rec.icon_png is None and rec.icon_emoji is None)
    r = await service.remove_icon(m)
    check("remove again -> nothing to remove", not r.ok and "doesn't have an icon" in r.message)

    # ------------------------------------------------------------ palette menus
    from cogs.customization import lunar_roles as cog_mod

    class Resp:
        def __init__(self):
            self.sent, self.deferred = [], False

        async def defer(self, **kw):
            self.deferred = True

        async def send_message(self, content=None, **kw):
            self.sent.append(content)

    class Inter:
        def __init__(self, user):
            self.user, self.guild, self.response, self.edits = user, user.guild, Resp(), []

        async def edit_original_response(self, **kw):
            self.edits.append(kw)

    g = await setup()  # no gradient perk
    owner = FakeMember(g, booster=True, name="owner")
    await service.create_role(owner, "Glow Role")
    view = cog_mod.PaletteView(owner, [0xFF0000, 0x00FF00, 0x0000FF], gradient_ok=False)
    check("no perk: secondary menu disabled with gradient placeholder",
          view.secondary_select.disabled and "Enhanced Role Colors" in view.secondary_select.placeholder)
    check("menus: hex labels, 'Clear secondary' option",
          [o.label for o in view.primary_select.options] == ["#FF0000", "#00FF00", "#0000FF"]
          and view.secondary_select.options[0].label == "Clear secondary")
    stranger = FakeMember(g, booster=True, name="stranger")
    si = Inter(stranger)
    check("someone else can't use the menus", await view.interaction_check(si) is False and "belongs to someone else" in si.response.sent[0])
    oi = Inter(owner)
    check("owner can use the menus", await view.interaction_check(oi) is True)

    view.primary_select._values = ["00FF00"]
    await view._on_primary(oi)
    role = g.get_role((await record(owner)).role_id)
    check("primary pick -> solid color on the same role", role.colour.value == 0x00FF00 and (await record(owner)).color_mode == "solid")
    check("palette message updated with result", oi.edits and "✅" in oi.edits[-1]["embed"].description)

    # Heads up from palette picks
    vip = g.add_role("VIP", role.position + 1, colour=0xFFFF00)
    owner.roles.append(vip)
    view.primary_select._values = ["0000FF"]
    await view._on_primary(oi)
    fields = {f.name: f.value for f in oi.edits[-1]["embed"].fields}
    check("palette pick shows hidden-color Heads up", "**VIP** role is higher" in fields.get("⚠️ Heads up", ""), fields)
    owner.roles.remove(vip)

    g.features.append("ENHANCED_ROLE_COLORS")
    view2 = cog_mod.PaletteView(owner, [0xFF0000, 0x00FF00], gradient_ok=True)
    check("perk: secondary menu enabled", not view2.secondary_select.disabled and "makes a gradient" in view2.secondary_select.placeholder)
    view2.secondary_select._values = ["FF0000"]
    await view2._on_secondary(oi)  # secondary first: builds on current colour (#0000FF)
    rec = await record(owner)
    check("secondary first -> gradient from current colour", rec.color_mode == "gradient" and rec.primary_color == 0x0000FF
          and rec.secondary_color == 0xFF0000, rec)
    view2.primary_select._values = ["00FF00"]
    await view2._on_primary(oi)
    rec = await record(owner)
    check("then primary -> gradient keeps the secondary", rec.color_mode == "gradient" and rec.primary_color == 0x00FF00
          and rec.secondary_color == 0xFF0000)
    view2.secondary_select._values = [cog_mod.CLEAR_SECONDARY]
    await view2._on_secondary(oi)
    rec = await record(owner)
    check("clear secondary -> solid again", rec.color_mode == "solid" and rec.primary_color == 0x00FF00)

    edited = {}

    class Msg:
        async def edit(self, **kw):
            edited.update(kw)
    view2.message = Msg()
    await view2.on_timeout()
    check("after 5 minutes: menus disabled and message says expired",
          all(i.disabled for i in view2.children) and "expired" in edited["embed"].description)
    check("palette timeout is 5 minutes", view2.timeout == 300)

    # palette keeps the picked colours shown
    view3 = cog_mod.PaletteView(owner, [0xFF0000, 0x00FF00, 0x0000FF], gradient_ok=True)
    i3 = Inter(owner)
    view3.primary_select._values = ["00FF00"]
    await view3._on_primary(i3)
    check("picked primary stays selected in the menu",
          [o.label for o in view3.primary_select.options if o.default] == ["#00FF00"] and i3.edits[-1].get("view") is view3)
    view3.secondary_select._values = ["0000FF"]
    await view3._on_secondary(i3)
    check("picked secondary stays selected, primary still selected",
          [o.label for o in view3.secondary_select.options if o.default] == ["#0000FF"]
          and [o.label for o in view3.primary_select.options if o.default] == ["#00FF00"])
    view3.secondary_select._values = [cog_mod.CLEAR_SECONDARY]
    await view3._on_secondary(i3)
    check("after clear, no secondary shown as selected", not any(o.default for o in view3.secondary_select.options))

    # ------------------------------------------------------------ live upload path (the real command handler)
    import logging as _logging

    class Capture(_logging.Handler):
        def __init__(self):
            super().__init__()
            self.lines = []

        def emit(self, rec):
            self.lines.append(rec.getMessage())
    cap = Capture()
    service.logger.addHandler(cap)

    class FakeFlags:
        def __init__(self, animated=False):
            self.animated, self.value = animated, (32 if animated else 0)

    class FakeAttachment:
        def __init__(self, data, filename, content_type, animated=False, declared=None):
            self.data, self.filename, self.content_type = data, filename, content_type
            self.size = len(data) if declared is None else declared
            self.width = self.height = 64
            self.flags = FakeFlags(animated)
            self.url = "https://cdn.discordapp.com/ephemeral-attachments/1/2/" + filename + "?ex=1&is=2&hm=3"
            self.proxy_url = "https://media.discordapp.net/ephemeral-attachments/1/2/" + filename
            self.reads = []

        async def read(self, *, use_cached=False):
            self.reads.append(use_cached)
            return self.data

    class Followup:
        def __init__(self):
            self.sent = []

        async def send(self, embed=None, ephemeral=None, **kw):
            self.sent.append(embed)

    class CmdInter:
        def __init__(self, user):
            self.user, self.guild, self.response, self.followup = user, user.guild, Resp(), Followup()

    g = await setup()  # Lunar Lab: no Role Icons perk
    up = FakeMember(g, booster=True, name="uploader")
    await service.create_role(up, "Upload Role")
    cog = cog_mod.LunarRoles(type("Bot", (), {})())
    handler = cog_mod.LunarRoles.lunar_icon.callback

    async def upload(att):
        inter = CmdInter(up)
        await handler(cog, inter, image=att, emoji=None)
        return inter.followup.sent[-1].description

    # Same kinds of files as make_test_images.py, built in memory.
    apng_upload = io.BytesIO()
    Image.new("RGB", (64, 64), (255, 0, 0)).save(apng_upload, format="PNG", save_all=True,
                                                 append_images=[Image.new("RGB", (64, 64), (0, 0, 255))], duration=300)
    uploads = {
        "05_animated.png": apng_upload.getvalue(),
        "07_gif_renamed.png": png_bytes(Image.new("RGB", (64, 64), (255, 0, 0)), "GIF"),  # GIF bytes, .png name
        "01_ok_square.png": png_bytes(Image.new("RGB", (256, 256), (250, 240, 120))),
    }

    def file_bytes(name):
        return uploads[name]

    # 1) Discord passes the original file through
    msg = await upload(FakeAttachment(file_bytes("05_animated.png"), "05_animated.png", "image/png"))
    check("live path: original APNG refused by content", "Animated" in msg, msg)
    msg = await upload(FakeAttachment(file_bytes("07_gif_renamed.png"), "07_gif_renamed.png", "image/png"))
    check("live path: original GIF-named-.png refused by content", "PNG or JPEG" in msg, msg)

    # 2) Discord re-processed the upload: still PNG frame, but flagged animated
    still = png_bytes(Image.new("RGB", (64, 64), (255, 0, 0)))
    msg = await upload(FakeAttachment(still, "05_animated.png", "image/png", animated=True))
    check("live path: Discord 'animated' flag refuses even if bytes are a still PNG", "Animated" in msg, msg)
    # 3) Discord re-processed a GIF into PNG bytes but reports image/gif
    msg = await upload(FakeAttachment(still, "07_gif_renamed.png", "image/gif"))
    check("live path: Discord-reported image/gif refuses even if bytes are PNG", "PNG or JPEG" in msg, msg)

    # 4) original URL used, never the media proxy; diagnostics logged
    att = FakeAttachment(file_bytes("01_ok_square.png"), "01_ok_square.png", "image/png")
    cap.lines.clear()
    msg = await upload(att)
    check("live path: downloads the original (use_cached=False)", att.reads == [False])
    check("live path: valid PNG reaches the perk check", "Your image is fine" in msg, msg)
    check("live path: logs filename/content type/flags", any("filename='01_ok_square.png'" in l and "content_type='image/png'" in l
                                                             and "flags=0" in l and "?ex=" not in l for l in cap.lines), cap.lines)
    check("live path: logs first bytes of the download", any("first bytes 89 50 4e 47 0d 0a 1a 0a" in l for l in cap.lines), cap.lines)

    # 5) size reported vs downloaded differs -> warning
    cap.lines.clear()
    await upload(FakeAttachment(file_bytes("01_ok_square.png"), "01_ok_square.png", "image/png", declared=999))
    check("live path: warns when Discord changed the file", any("the file was changed" in l for l in cap.lines))

    # 6) too big: refused before downloading
    big = FakeAttachment(b"x", "huge.png", "image/png", declared=600 * 1024)
    msg = await upload(big)
    check("live path: >256 KB refused before download", "256 KB" in msg and big.reads == [])
    service.logger.removeHandler(cap)

    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())
