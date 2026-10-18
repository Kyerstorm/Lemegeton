"""Small stand-ins for discord.py objects used by the offline Lunar tests."""
import asyncio
import copy
import datetime
import itertools

import discord

_ids = itertools.count(7000)


def forbidden():
    return discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "Missing Permissions")


def apply_colours(role, kw):
    if "colour" in kw:
        role.colour = kw["colour"]
    for key in ("secondary", "tertiary"):
        if f"{key}_colour" in kw:
            setattr(role, f"{key}_colour", kw.get(f"{key}_colour") or kw.get(f"{key}_color"))


class FakeIconAsset(discord.Asset):
    """Stands in for an uploaded role icon; keeps the bytes so tests can inspect them."""

    def __init__(self, data):
        self._state, self._url, self._animated, self._key = None, "https://cdn.test/icon.png", False, "icon"
        self.data = data

    async def read(self):
        return self.data


def icon_value(value):
    if isinstance(value, bytes):
        return FakeIconAsset(value)
    return value  # str emoji or None


class FakeRole:
    def __init__(self, guild, name, position, default=False):
        self.guild, self.id, self.name, self.position = guild, next(_ids), name, position
        self._default = default
        self.colour = discord.Colour(0)
        self.secondary_colour = None
        self.tertiary_colour = None
        self.display_icon = None
        self.permissions = discord.Permissions.none()
        self.mention = f"<@&{self.id}>"
        self.members = []
        self.fail_delete = False

    def is_default(self):
        return self._default

    def is_bot_managed(self):
        return False

    def __ge__(self, other):
        return self.position >= other.position

    async def edit(self, **kw):
        if "name" in kw:
            self.name = kw["name"]
        apply_colours(self, kw)
        if "display_icon" in kw:
            self.display_icon = icon_value(kw["display_icon"])

    async def delete(self, reason=None):
        if self.fail_delete:
            raise forbidden()
        self.guild.deleted.append(self.id)
        self.guild.roles.remove(self)
        for m in self.guild.members:
            if self in m.roles:
                m.roles.remove(self)


class FakeMessage:
    def __init__(self, channel, kwargs):
        self.channel, self.id, self.kwargs = channel, next(_ids), kwargs


class FakePartial:
    def __init__(self, channel, mid):
        self.channel, self.id = channel, mid

    async def edit(self, **kw):
        self.channel.edits.append((self.id, kw))


class FakeChannel:
    def __init__(self):
        self.id = next(_ids)
        self.sent = []
        self.edits = []
        self.mention = f"<#{self.id}>"

    async def send(self, **kw):
        msg = FakeMessage(self, kw)
        self.sent.append(msg)
        return msg

    def get_partial_message(self, mid):
        return FakePartial(self, mid)

    def texts(self):
        return [m.kwargs["embed"].description for m in self.sent]


class FakeGuild:
    def __init__(self, gid, features=()):
        self.id = gid
        self.name = "Lunar Lab"
        self.features = list(features)
        self.unavailable = False
        self.chunked = True
        self.chunk_behaviour = None  # None | "fail" | "hang"
        self.deleted = []
        self.members = []
        self.channel = FakeChannel()
        self.everyone = FakeRole(self, "@everyone", 0, default=True)
        self.anchor = FakeRole(self, "Anchor", 1)
        self.bot_role = FakeRole(self, "Lunar Test", 2)
        self.bot_role.permissions = discord.Permissions(manage_roles=True)
        self.roles = [self.everyone, self.anchor, self.bot_role]
        self.me = type("Me", (), {})()
        self.me.top_role = self.bot_role
        self.me.guild_permissions = discord.Permissions(manage_roles=True)

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)

    def get_channel(self, cid):
        return self.channel if cid == self.channel.id else None

    def add_role(self, name, position, colour=0):
        for r in self.roles:
            if not r.is_default() and r.position >= position:
                r.position += 1
        role = FakeRole(self, name, position)
        role.colour = discord.Colour(colour)
        self.roles.append(role)
        return role

    async def chunk(self, cache=True):
        if self.chunk_behaviour == "fail":
            raise discord.ClientException("chunk failed")
        if self.chunk_behaviour == "hang":
            await asyncio.sleep(10)
        self.chunked = True

    async def create_role(self, **kw):
        for r in self.roles:
            if not r.is_default():
                r.position += 1
        role = FakeRole(self, kw["name"], 1)
        apply_colours(role, kw)
        if "display_icon" in kw:
            role.display_icon = icon_value(kw["display_icon"])
        self.roles.append(role)
        return role

    async def fetch_roles(self):
        return list(self.roles)

    async def edit_role_positions(self, positions, reason=None):
        for r, p in positions.items():
            r.position = p


class FakeMember:
    def __init__(self, guild, booster=False, roles=(), name=None):
        self.id, self.guild = next(_ids), guild
        self.premium_since = datetime.datetime.now(datetime.timezone.utc) if booster else None
        self.roles = [guild.everyone, *roles]
        self.name = name or f"member{self.id}"
        self.display_name = self.name
        self.mention = f"<@{self.id}>"
        self.bot = False
        self.dms = []
        guild.members.append(self)

    async def add_roles(self, *roles, reason=None):
        self.roles.extend(r for r in roles if r not in self.roles)

    async def remove_roles(self, *roles, reason=None):
        self.roles = [r for r in self.roles if r not in roles]

    async def send(self, content=None, embed=None):
        self.dms.append(content if content is not None else embed)

    def snapshot(self):
        """A 'before' copy for on_member_update."""
        clone = copy.copy(self)
        clone.roles = list(self.roles)
        return clone

    def leave(self):
        self.guild.members.remove(self)

    def __str__(self):
        return self.name
