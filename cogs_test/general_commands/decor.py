# cogs/decor.py
#
# Discord Avatar Decoration Retriever
#
# Requires:
#   discord.py >= 2.4
#   aiohttp
#
# One command:
#
#   /decor
#
# Options:
#   user  - Get a user's currently equipped decoration
#   asset - Get a decoration directly by Discord asset hash
#   sku   - Find a cached decoration by SKU ID
#   name  - Find a cached decoration by name
#
# Examples:
#
#   /decor user:@Someone
#   /decor asset:a_fed43ab12698df65902ba06727e20c0e
#   /decor sku:1144058844004233369
#   /decor name:Halloween
#
# IMPORTANT:
# Discord officially exposes the equipped decoration's:
#     avatar_decoration_data.asset
#     avatar_decoration_data.sku_id
#
# The actual avatar-decoration CDN endpoint is:
#     https://cdn.discordapp.com/avatar-decoration-presets/{asset}.png
#
# This cog does NOT use a user token or Discord client token.
# It uses the normal bot/API-visible user information.

from __future__ import annotations

import asyncio
import io
import re
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


# ============================================================
# CONFIGURATION
# ============================================================

CACHE_TTL = 60 * 60 * 24
HTTP_TIMEOUT = 15
MAX_DOWNLOAD_SIZE = 10 * 1024 * 1024

# Discord avatar decoration hashes are normally hexadecimal,
# optionally prefixed with "a_" for animated assets.
ASSET_PATTERN = re.compile(
    r"^(?:a_)?[a-fA-F0-9]{8,128}$"
)

SKU_PATTERN = re.compile(
    r"^\d{1,25}$"
)

# CDN host we are willing to download from.
DISCORD_CDN_HOSTS = {
    "cdn.discordapp.com",
    "media.discordapp.net",
}


# ============================================================
# DATA MODEL
# ============================================================

@dataclass(slots=True)
class DecorationEntry:
    asset: str
    sku_id: Optional[int] = None
    name: Optional[str] = None
    discovered_at: float = 0.0

    @property
    def url(self) -> str:
        return (
            "https://cdn.discordapp.com/"
            f"avatar-decoration-presets/{self.asset}.png"
        )


# ============================================================
# COG
# ============================================================

class Decor(commands.Cog):
    """
    Discord Avatar Decoration retrieval system.

    The cog intentionally uses the official bot-visible user data
    rather than Discord's private client endpoints (for now).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # asset -> DecorationEntry
        self.asset_cache: dict[str, DecorationEntry] = {}

        # sku -> DecorationEntry
        self.sku_cache: dict[int, DecorationEntry] = {}

        # normalized name -> DecorationEntry
        self.name_cache: dict[str, DecorationEntry] = {}

        # Downloaded bytes:
        # asset -> (timestamp, bytes, extension, content_type)
        self.file_cache: dict[
            str,
            tuple[float, bytes, str, str]
        ] = {}

        # Prevent two users from downloading the exact same asset
        # simultaneously.
        self.download_locks: dict[str, asyncio.Lock] = {}

        # HTTP session is created lazily because a Cog can be
        # constructed before the bot's event loop is fully ready.
        self.session: Optional[aiohttp.ClientSession] = None

    # ========================================================
    # LIFECYCLE
    # ========================================================

    async def cog_load(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=HTTP_TIMEOUT,
                connect=5,
                sock_read=HTTP_TIMEOUT,
            ),
            headers={
                "User-Agent": (
                    "DiscordBot/1.0 "
                    "(Avatar Decoration Retriever)"
                )
            },
        )

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

        self.session = None

    # ========================================================
    # HELPERS
    # ========================================================

    @staticmethod
    def normalize_name(value: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            value.strip().lower(),
        )

    @staticmethod
    def valid_asset(asset: str) -> bool:
        return bool(
            asset
            and ASSET_PATTERN.fullmatch(asset.strip())
        )

    @staticmethod
    def valid_sku(sku: str) -> bool:
        return bool(
            sku
            and SKU_PATTERN.fullmatch(sku.strip())
        )

    @staticmethod
    def extension_from_content_type(
        content_type: str,
        asset: str,
    ) -> str:
        content_type = content_type.lower()

        if "gif" in content_type:
            return "gif"

        if "webp" in content_type:
            return "webp"

        if "avif" in content_type:
            return "avif"

        if "jpeg" in content_type or "jpg" in content_type:
            return "jpg"

        if "png" in content_type:
            return "png"

        # Avatar decorations are officially PNG.
        # This fallback is therefore intentionally conservative.
        if asset.startswith("a_"):
            return "webp"

        return "png"

    @staticmethod
    def filename_for(
        asset: str,
        extension: str,
    ) -> str:
        return f"discord_decoration_{asset}.{extension}"

    def remember(
        self,
        asset: str,
        sku_id: Optional[int] = None,
        name: Optional[str] = None,
    ) -> DecorationEntry:

        existing = self.asset_cache.get(asset)

        if existing:
            if sku_id is not None:
                existing.sku_id = sku_id

            if name:
                existing.name = name

            if sku_id is not None:
                self.sku_cache[sku_id] = existing

            if name:
                self.name_cache[
                    self.normalize_name(name)
                ] = existing

            return existing

        entry = DecorationEntry(
            asset=asset,
            sku_id=sku_id,
            name=name,
            discovered_at=time.time(),
        )

        self.asset_cache[asset] = entry

        if sku_id is not None:
            self.sku_cache[sku_id] = entry

        if name:
            self.name_cache[
                self.normalize_name(name)
            ] = entry

        return entry

    # ========================================================
    # USER DECORATION
    # ========================================================

    async def get_user_decoration(
        self,
        user: discord.abc.User,
    ) -> Optional[DecorationEntry]:

        decoration = getattr(
            user,
            "avatar_decoration",
            None,
        )

        sku_id = getattr(
            user,
            "avatar_decoration_sku_id",
            None,
        )

        # discord.py >= 2.4 normally gives us the Asset directly.
        if decoration is not None:
            asset = getattr(
                decoration,
                "key",
                None,
            )

            if asset:
                return self.remember(
                    asset=str(asset),
                    sku_id=sku_id,
                )

        # Fallback for situations where the library exposes the
        # raw decoration data differently.
        raw_user = getattr(
            user,
            "_user",
            None,
        )

        raw_data = getattr(
            raw_user,
            "avatar_decoration_data",
            None,
        )

        if isinstance(raw_data, dict):
            asset = raw_data.get("asset")
            raw_sku = raw_data.get("sku_id")

            if asset:
                try:
                    parsed_sku = (
                        int(raw_sku)
                        if raw_sku is not None
                        else sku_id
                    )
                except (TypeError, ValueError):
                    parsed_sku = sku_id

                return self.remember(
                    asset=str(asset),
                    sku_id=parsed_sku,
                )

        return None

    # ========================================================
    # CDN
    # ========================================================

    def build_asset_url(
        self,
        asset: str,
    ) -> str:

        asset = asset.strip()

        return (
            "https://cdn.discordapp.com/"
            f"avatar-decoration-presets/{asset}.png"
        )

    async def download_asset(
        self,
        asset: str,
    ) -> tuple[bytes, str, str]:

        asset = asset.strip()

        if not self.valid_asset(asset):
            raise ValueError(
                "That does not look like a valid Discord "
                "avatar decoration asset hash."
            )

        now = time.time()

        cached = self.file_cache.get(asset)

        if cached:
            timestamp, data, extension, content_type = cached

            if now - timestamp < CACHE_TTL:
                return data, extension, content_type

            self.file_cache.pop(asset, None)

        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=HTTP_TIMEOUT,
                    connect=5,
                    sock_read=HTTP_TIMEOUT,
                ),
                headers={
                    "User-Agent": (
                        "DiscordBot/1.0 "
                        "(Avatar Decoration Retriever)"
                    )
                },
            )

        lock = self.download_locks.setdefault(
            asset,
            asyncio.Lock(),
        )

        async with lock:

            # Another coroutine may have downloaded it while
            # we were waiting for the lock.
            cached = self.file_cache.get(asset)

            if cached:
                timestamp, data, extension, content_type = cached

                if time.time() - timestamp < CACHE_TTL:
                    return data, extension, content_type

            url = self.build_asset_url(asset)

            last_error: Optional[Exception] = None

            for attempt in range(3):

                try:
                    async with self.session.get(
                        url,
                        allow_redirects=True,
                    ) as response:

                        if response.status == 404:
                            raise FileNotFoundError(
                                "Discord could not find that "
                                "decoration asset."
                            )

                        if response.status == 429:
                            retry_after = response.headers.get(
                                "Retry-After",
                                "1",
                            )

                            try:
                                delay = min(
                                    float(retry_after),
                                    10,
                                )
                            except ValueError:
                                delay = 1

                            await asyncio.sleep(delay)
                            continue

                        if response.status >= 500:
                            raise aiohttp.ClientResponseError(
                                response.request_info,
                                response.history,
                                status=response.status,
                                message=(
                                    "Discord CDN returned a "
                                    "server error."
                                ),
                            )

                        if response.status != 200:
                            raise RuntimeError(
                                f"Discord CDN returned HTTP "
                                f"{response.status}."
                            )

                        content_length = response.headers.get(
                            "Content-Length"
                        )

                        if content_length:
                            try:
                                if (
                                    int(content_length)
                                    > MAX_DOWNLOAD_SIZE
                                ):
                                    raise ValueError(
                                        "The decoration asset is "
                                        "larger than the configured "
                                        "download limit."
                                    )
                            except ValueError as exc:
                                if str(exc).startswith(
                                    "The decoration"
                                ):
                                    raise

                        data = await response.read()

                        if len(data) > MAX_DOWNLOAD_SIZE:
                            raise ValueError(
                                "The decoration asset is too large."
                            )

                        if not data:
                            raise RuntimeError(
                                "Discord returned an empty asset."
                            )

                        content_type = response.headers.get(
                            "Content-Type",
                            "image/png",
                        )

                        extension = (
                            self.extension_from_content_type(
                                content_type,
                                asset,
                            )
                        )

                        self.file_cache[asset] = (
                            time.time(),
                            data,
                            extension,
                            content_type,
                        )

                        return (
                            data,
                            extension,
                            content_type,
                        )

                except FileNotFoundError:
                    raise

                except (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    RuntimeError,
                ) as exc:

                    last_error = exc

                    if attempt < 2:
                        await asyncio.sleep(
                            0.75 * (attempt + 1)
                        )

            raise RuntimeError(
                "The Discord CDN could not be reached after "
                "multiple attempts."
            ) from last_error

    # ========================================================
    # RESOLUTION
    # ========================================================

    def resolve_by_asset(
        self,
        asset: str,
    ) -> Optional[DecorationEntry]:

        return self.asset_cache.get(
            asset.strip()
        )

    def resolve_by_sku(
        self,
        sku: str,
    ) -> Optional[DecorationEntry]:

        try:
            sku_id = int(sku.strip())
        except (TypeError, ValueError):
            return None

        return self.sku_cache.get(sku_id)

    def resolve_by_name(
        self,
        name: str,
    ) -> Optional[DecorationEntry]:

        normalized = self.normalize_name(name)

        # Exact match first.
        exact = self.name_cache.get(normalized)

        if exact:
            return exact

        # Partial match.
        for key, entry in self.name_cache.items():
            if normalized in key:
                return entry

        return None

    # ========================================================
    # ERROR EMBEDS
    # ========================================================

    @staticmethod
    def error_embed(
        title: str,
        description: str,
    ) -> discord.Embed:

        embed = discord.Embed(
            title=f"Unable to retrieve decoration",
            description=description,
            colour=discord.Colour.red(),
        )

        return embed

    @staticmethod
    def success_embed(
        entry: DecorationEntry,
        user: Optional[discord.abc.User] = None,
    ) -> discord.Embed:

        embed = discord.Embed(
            title="Avatar Decoration",
            colour=discord.Colour.blurple(),
        )

        if user:
            embed.description = (
                f"Decoration currently equipped by "
                f"**{discord.utils.escape_markdown(user.display_name)}**."
            )

        if entry.name:
            embed.add_field(
                name="Name",
                value=entry.name,
                inline=True,
            )

        embed.add_field(
            name="Asset",
            value=f"`{entry.asset}`",
            inline=False,
        )

        if entry.sku_id:
            embed.add_field(
                name="SKU",
                value=f"`{entry.sku_id}`",
                inline=True,
            )

        embed.set_footer(
            text="Discord Avatar Decoration"
        )

        return embed

    # ========================================================
    # COMMAND
    # ========================================================

    @app_commands.command(
        name="decor",
        description=(
            "Retrieve a Discord avatar decoration as an image file."
        ),
    )
    @app_commands.describe(
        user=(
            "Get the currently equipped decoration "
            "from a Discord user."
        ),
        asset=(
            "Discord avatar decoration asset hash."
        ),
        sku=(
            "Discord avatar decoration SKU ID "
            "already discovered by the bot."
        ),
        name=(
            "Search the bot's discovered decoration names."
        ),
    )
    async def decor(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        asset: Optional[str] = None,
        sku: Optional[str] = None,
        name: Optional[str] = None,
    ):

        # ----------------------------------------------------
        # Exactly one source
        # ----------------------------------------------------

        supplied = [
            user is not None,
            asset is not None,
            sku is not None,
            name is not None,
        ]

        if sum(supplied) == 0:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "No decoration specified",
                    (
                        "Choose one option:\n"
                        "• `user` — retrieve their equipped decoration\n"
                        "• `asset` — retrieve by asset hash\n"
                        "• `sku` — retrieve a discovered SKU\n"
                        "• `name` — search discovered decorations"
                    ),
                ),
                ephemeral=True,
            )
            return

        if sum(supplied) > 1:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Too many options",
                    (
                        "Use only **one** of `user`, `asset`, "
                        "`sku`, or `name`."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        # ----------------------------------------------------
        # Resolve source
        # ----------------------------------------------------

        entry: Optional[DecorationEntry] = None
        source_user: Optional[discord.abc.User] = None

        try:

            # ----------------------------------------------
            # USER
            # ----------------------------------------------

            if user is not None:

                source_user = user

                # Fetch fresh user information rather than
                # relying only on the local cache.
                try:
                    fresh_user = await self.bot.fetch_user(
                        user.id
                    )
                    source_user = fresh_user
                except discord.HTTPException:
                    # If fetching fails, continue with the
                    # user object supplied by Discord.
                    pass

                entry = await self.get_user_decoration(
                    source_user
                )

                if entry is None:
                    await interaction.followup.send(
                        embed=self.error_embed(
                            "No decoration found",
                            (
                                f"{source_user.mention} does not "
                                "currently have an accessible "
                                "avatar decoration."
                            ),
                        )
                    )
                    return

            # ----------------------------------------------
            # ASSET
            # ----------------------------------------------

            elif asset is not None:

                asset = asset.strip()

                if not self.valid_asset(asset):
                    await interaction.followup.send(
                        embed=self.error_embed(
                            "Invalid asset",
                            (
                                "The supplied value does not look "
                                "like a Discord avatar decoration "
                                "asset hash."
                            ),
                        )
                    )
                    return

                entry = self.remember(
                    asset=asset
                )

            # ----------------------------------------------
            # SKU
            # ----------------------------------------------

            elif sku is not None:

                sku = sku.strip()

                if not self.valid_sku(sku):
                    await interaction.followup.send(
                        embed=self.error_embed(
                            "Invalid SKU",
                            "The SKU must be a numeric Discord ID.",
                        )
                    )
                    return

                entry = self.resolve_by_sku(sku)

                if entry is None:
                    await interaction.followup.send(
                        embed=self.error_embed(
                            "SKU not discovered",
                            (
                                f"`{sku}` is not currently in the "
                                "bot's decoration cache.\n\n"
                                "A Discord decoration's SKU ID "
                                "does not by itself provide the "
                                "asset hash through the normal "
                                "bot user object. Use `asset`, or "
                                "first retrieve the decoration "
                                "from a user who has it equipped."
                            ),
                        )
                    )
                    return

            # ----------------------------------------------
            # NAME
            # ----------------------------------------------

            elif name is not None:

                name = name.strip()

                if len(name) < 2:
                    await interaction.followup.send(
                        embed=self.error_embed(
                            "Name too short",
                            (
                                "Enter at least two characters "
                                "when searching by name."
                            ),
                        )
                    )
                    return

                entry = self.resolve_by_name(name)

                if entry is None:
                    await interaction.followup.send(
                        embed=self.error_embed(
                            "Decoration not found",
                            (
                                f"No discovered decoration "
                                f"matches `{discord.utils.escape_markdown(name)}`.\n\n"
                                "The bot only knows names that "
                                "have been discovered and cached; "
                                "Discord's normal bot API does not "
                                "provide the entire Avatar "
                                "Decoration Shop catalog."
                            ),
                        )
                    )
                    return

            # ------------------------------------------------
            # Download
            # ------------------------------------------------

            assert entry is not None

            data, extension, content_type = (
                await self.download_asset(
                    entry.asset
                )
            )

            filename = self.filename_for(
                entry.asset,
                extension,
            )

            file = discord.File(
                io.BytesIO(data),
                filename=filename,
            )

            embed = self.success_embed(
                entry,
                source_user,
            )

            # Display the actual uploaded Discord attachment
            # inside the embed.
            embed.set_image(
                url=f"attachment://{filename}"
            )

            await interaction.followup.send(
                embed=embed,
                file=file,
            )

        # ----------------------------------------------------
        # Expected failures
        # ----------------------------------------------------

        except FileNotFoundError:

            await interaction.followup.send(
                embed=self.error_embed(
                    "Asset not found",
                    (
                        "Discord's CDN returned `404` for this "
                        "decoration. The asset may have been "
                        "removed or the hash may be incorrect."
                    ),
                )
            )

        except ValueError as exc:

            await interaction.followup.send(
                embed=self.error_embed(
                    "Invalid decoration",
                    str(exc),
                )
            )

        except asyncio.TimeoutError:

            await interaction.followup.send(
                embed=self.error_embed(
                    "Discord CDN timeout",
                    (
                        "The decoration took too long to download. "
                        "Try the command again."
                    ),
                )
            )

        except aiohttp.ClientError:

            await interaction.followup.send(
                embed=self.error_embed(
                    "Network error",
                    (
                        "The bot could not reach Discord's CDN. "
                        "Try again in a moment."
                    ),
                )
            )

        except discord.Forbidden:

            await interaction.followup.send(
                embed=self.error_embed(
                    "Discord denied the request",
                    (
                        "Discord did not allow the requested "
                        "operation."
                    ),
                )
            )

        except discord.HTTPException as exc:

            await interaction.followup.send(
                embed=self.error_embed(
                    "Discord API error",
                    (
                        f"Discord returned HTTP `{exc.status}`."
                    ),
                )
            )

        except Exception:

            # Do not leak internal exceptions to users.
            await interaction.followup.send(
                embed=self.error_embed(
                    "Unexpected error",
                    (
                        "Something unexpected happened while "
                        "retrieving the decoration."
                    ),
                )
            )

    # ========================================================
    # AUTOCOMPLETE
    # ========================================================

    @decor.autocomplete("name")
    async def decor_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:

        current_normalized = (
            self.normalize_name(current)
        )

        results: list[
            app_commands.Choice[str]
        ] = []

        for entry in self.name_cache.values():

            if not entry.name:
                continue

            normalized = self.normalize_name(
                entry.name
            )

            if (
                not current_normalized
                or current_normalized in normalized
            ):
                results.append(
                    app_commands.Choice(
                        name=entry.name[:100],
                        value=entry.name[:100],
                    )
                )

            if len(results) >= 25:
                break

        return results

    @decor.autocomplete("asset")
    async def decor_asset_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:

        results: list[
            app_commands.Choice[str]
        ] = []

        current = current.lower().strip()

        for entry in self.asset_cache.values():

            if (
                not current
                or current in entry.asset.lower()
            ):

                label = entry.asset

                if entry.name:
                    label = (
                        f"{entry.name} • "
                        f"{entry.asset}"
                    )

                results.append(
                    app_commands.Choice(
                        name=label[:100],
                        value=entry.asset[:100],
                    )
                )

            if len(results) >= 25:
                break

        return results

    @decor.autocomplete("sku")
    async def decor_sku_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:

        results: list[
            app_commands.Choice[str]
        ] = []

        current = current.strip()

        for sku_id, entry in self.sku_cache.items():

            sku_string = str(sku_id)

            if (
                not current
                or current in sku_string
            ):

                label = sku_string

                if entry.name:
                    label = (
                        f"{entry.name} • "
                        f"{sku_string}"
                    )

                results.append(
                    app_commands.Choice(
                        name=label[:100],
                        value=sku_string,
                    )
                )

            if len(results) >= 25:
                break

        return results


# ============================================================
# SETUP
# ============================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(Decor(bot))