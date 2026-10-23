from helpers.color_palette import PALETTE
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
import asyncio
import aiohttp
from typing import Optional
import logging
import config

from database import (
    set_guild_bot_update_channel,
    get_guild_bot_update_channel,
    get_all_guild_bot_update_channels,
    is_user_bot_moderator,
    get_bot_config,
    set_bot_config,
)
from cogs_test.general_commands.dashboard import command_meta
from helpers.embed_helper import build_error_embed, build_success_embed, build_info_embed, build_warning_embed

# Setup logger
logger = logging.getLogger("github_tracker")

GITHUB_API_URL = "https://api.github.com"
LAST_SHA_KEY = "github_last_sha"
LAST_SHA_SCOPE = "global"
# How far back to look for the last posted commit before treating history as rewritten
MAX_LOOKBACK = 100
EMBED_DESCRIPTION_LIMIT = 4000


class GitHubAPIError(Exception):
    """Raised when the GitHub API returns an unusable response."""


def admin_only():
    """App command check that allows bot moderators, falling back to users with administrative/manage permissions."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False

        try:
            if await is_user_bot_moderator(interaction.user):
                return True

            member = interaction.user if isinstance(interaction.user, discord.Member) else await interaction.guild.fetch_member(interaction.user.id)
            perms = getattr(member, "guild_permissions", None)
            if perms:
                return perms.manage_roles or perms.manage_guild or perms.administrator
        except Exception:
            return False
        return False

    return app_commands.check(predicate)


def bot_moderator_only():
    """App command check that allows only bot moderators.
    Used for bot-wide actions like publishing commit updates to all servers.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            return await is_user_bot_moderator(interaction.user)
        except Exception:
            return False

    return app_commands.check(predicate)


class GitHubTracker(commands.Cog):
    """Posts new commits from the configured GitHub repository to bot-update channels."""

    github = app_commands.Group(name="github", description="GitHub commit tracker (Bot Moderator only)")
    command_meta(section="Admin", name="GitHub")(github)

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.repo = config.GITHUB_REPO
        self.branch = config.GITHUB_BRANCH
        self.session: Optional[aiohttp.ClientSession] = None
        # Serialises the background loop and /github check so a commit is never posted twice
        self._poll_lock = asyncio.Lock()
        self.last_poll_at: Optional[datetime] = None
        self.last_poll_error: Optional[str] = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        self.poll_commits.start()
        logger.info(f"GitHub tracker watching {self.repo}@{self.branch} every {config.GITHUB_POLL_MINUTES} min")

    async def cog_unload(self):
        self.poll_commits.cancel()
        if self.session and not self.session.closed:
            await self.session.close()

    # ------------------------------------------------------------------
    # GitHub API
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Lemegeton-Discord-Bot",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if config.GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
        return headers

    async def _fetch_commits(self, limit: int = 10) -> list[dict]:
        """Fetch the newest commits on the tracked branch, newest first."""
        url = f"{GITHUB_API_URL}/repos/{self.repo}/commits"
        params = {"sha": self.branch, "per_page": str(min(max(limit, 1), 100))}

        async with self.session.get(url, params=params, headers=self._headers()) as response:
            if response.status == 200:
                return await response.json()
            if response.status in (403, 429) and response.headers.get("X-RateLimit-Remaining") == "0":
                reset = response.headers.get("X-RateLimit-Reset")
                reset_at = f" (resets <t:{reset}:R>)" if reset else ""
                raise GitHubAPIError(f"GitHub rate limit reached{reset_at}")
            if response.status == 404:
                raise GitHubAPIError(f"Repository or branch not found: {self.repo}@{self.branch}")
            if response.status == 401:
                raise GitHubAPIError("GITHUB_TOKEN was rejected by GitHub")
            raise GitHubAPIError(f"GitHub API returned HTTP {response.status}")

    async def _fetch_new_commits(self, since_sha: str) -> Optional[list[dict]]:
        """Return commits newer than since_sha, oldest first.
        Returns None if since_sha is not in recent history (e.g. after a force-push).
        """
        commits = await self._fetch_commits(MAX_LOOKBACK)
        for index, commit in enumerate(commits):
            if commit["sha"] == since_sha:
                return list(reversed(commits[:index]))
        return None

    # ------------------------------------------------------------------
    # Embed building
    # ------------------------------------------------------------------

    @staticmethod
    def _commit_author(commit: dict) -> str:
        if commit.get("author") and commit["author"].get("login"):
            return commit["author"]["login"]
        return commit["commit"]["author"].get("name", "unknown")

    @staticmethod
    def _commit_date(commit: dict) -> Optional[datetime]:
        raw = commit["commit"].get("committer", {}).get("date") or commit["commit"]["author"].get("date")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _format_commit_line(self, commit: dict) -> str:
        summary = commit["commit"]["message"].split("\n", 1)[0].strip()
        if len(summary) > 100:
            summary = summary[:97] + "..."
        summary = discord.utils.escape_markdown(summary)
        return f"[`{commit['sha'][:7]}`]({commit['html_url']}) {summary} — *{self._commit_author(commit)}*"

    def _build_commits_embed(self, commits: list[dict], title: Optional[str] = None) -> discord.Embed:
        """Build one embed listing commits in the order given."""
        lines = []
        length = 0
        for index, commit in enumerate(commits):
            line = self._format_commit_line(commit)
            remaining = len(commits) - index
            # Leave room for the "...and N more" trailer
            if length + len(line) + 1 > EMBED_DESCRIPTION_LIMIT - 40:
                lines.append(f"*…and {remaining} more*")
                break
            lines.append(line)
            length += len(line) + 1

        count = len(commits)
        embed = discord.Embed(
            title=title or f"🛠️ {count} new commit{'s' if count != 1 else ''} to {self.repo}",
            url=f"https://github.com/{self.repo}/commits/{self.branch}",
            description="\n".join(lines),
            color=PALETTE.PRIMARY,
        )
        embed.set_author(
            name=f"{self.repo} • {self.branch}",
            url=f"https://github.com/{self.repo}",
            icon_url="https://github.githubassets.com/favicons/favicon.png",
        )
        newest = max((d for d in (self._commit_date(c) for c in commits) if d), default=None)
        if newest:
            embed.timestamp = newest
        embed.set_footer(text="GitHub Commit Tracker")
        return embed

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def _publish_to_all(self, embed: discord.Embed) -> tuple[int, int, list[str]]:
        """Send embed to every configured bot-update channel. Returns (success, total, failures)."""
        update_channels = await get_all_guild_bot_update_channels()
        success_count = 0
        failed_guilds = []

        for guild_id, channel_id in update_channels.items():
            try:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    failed_guilds.append(f"Guild {guild_id} (Channel {channel_id} not found)")
                    continue
                await channel.send(embed=embed)
                success_count += 1
            except Exception as e:
                failed_guilds.append(f"Guild {guild_id}: {str(e)}")
                logger.error(f"Error publishing commits to guild {guild_id}: {e}")

        return success_count, len(update_channels), failed_guilds

    def _publish_summary_embed(self, success: int, total: int, failures: list[str]) -> discord.Embed:
        if total == 0:
            return build_error_embed(
                "No Update Channels Configured",
                "No servers have configured bot update channels."
            )
        if failures:
            failed_list = "\n".join(f"• {failure}" for failure in failures[:5])
            if len(failures) > 5:
                failed_list += f"\n• ... and {len(failures) - 5} more"
            return build_warning_embed(
                "Commits Published",
                f"Published to {success}/{total} configured servers.\n\n"
                f"⚠️ **Failed to send to:**\n{failed_list}"
            )
        return build_success_embed(
            "Commits Published",
            f"Successfully published to {success}/{total} configured servers."
        )

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _run_poll(self) -> tuple[str, Optional[tuple[int, int, list[str]]]]:
        """Check for new commits and post them everywhere.
        Returns (status message, publish result or None if nothing was posted).
        """
        async with self._poll_lock:
            self.last_poll_at = discord.utils.utcnow()
            try:
                last_sha = await get_bot_config(LAST_SHA_KEY, LAST_SHA_SCOPE)

                if not last_sha:
                    # First run: remember where we are instead of posting the whole history
                    head = await self._fetch_commits(1)
                    if head:
                        await set_bot_config(LAST_SHA_KEY, LAST_SHA_SCOPE, head[0]["sha"])
                        logger.info(f"GitHub tracker initialised at {head[0]['sha'][:7]}")
                    self.last_poll_error = None
                    return "Tracker initialised at the current head; future commits will be posted.", None

                new_commits = await self._fetch_new_commits(last_sha)
                if new_commits is None:
                    head = await self._fetch_commits(1)
                    if head:
                        await set_bot_config(LAST_SHA_KEY, LAST_SHA_SCOPE, head[0]["sha"])
                    logger.warning(
                        f"Last posted commit {last_sha[:7]} not found in the last {MAX_LOOKBACK} commits "
                        f"of {self.repo}@{self.branch}; resetting to head"
                    )
                    self.last_poll_error = None
                    return "Last posted commit is no longer in history; reset to the current head.", None

                self.last_poll_error = None
                if not new_commits:
                    return "No new commits.", None

                embed = self._build_commits_embed(new_commits)
                result = await self._publish_to_all(embed)
                # Advance even if some guilds failed, so working guilds don't get duplicates next cycle
                await set_bot_config(LAST_SHA_KEY, LAST_SHA_SCOPE, new_commits[-1]["sha"])
                logger.info(f"Posted {len(new_commits)} new commit(s) to {result[0]}/{result[1]} servers")
                return f"Posted {len(new_commits)} new commit(s).", result

            except GitHubAPIError as e:
                self.last_poll_error = str(e)
                logger.warning(f"GitHub poll skipped: {e}")
                return f"GitHub poll failed: {e}", None
            except aiohttp.ClientError as e:
                self.last_poll_error = f"Network error: {e}"
                logger.warning(f"GitHub poll network error: {e}")
                return f"GitHub poll failed: network error ({e})", None

    @tasks.loop(minutes=config.GITHUB_POLL_MINUTES)
    async def poll_commits(self):
        try:
            await self._run_poll()
        except Exception as e:
            # Never let an unexpected error kill the loop
            self.last_poll_error = str(e)
            logger.error(f"Unexpected error in GitHub poll: {e}", exc_info=True)

    @poll_commits.before_loop
    async def before_poll_commits(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @github.command(name="recent", description="Show or publish the most recent commits (Bot Moderator only)")
    @bot_moderator_only()
    @app_commands.describe(
        count="How many commits to include (1-20)",
        publish_to="Preview privately, or publish to this server / all servers",
    )
    @app_commands.choices(
        publish_to=[
            app_commands.Choice(name="👀 Preview (only you)", value="preview"),
            app_commands.Choice(name="🏠 Current Server Only", value="current_server"),
            app_commands.Choice(name="📡 All Servers (Bot Update)", value="all_servers"),
        ]
    )
    async def github_recent(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, 20] = 5,
        publish_to: str = "preview",
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            commits = await self._fetch_commits(count)
        except (GitHubAPIError, aiohttp.ClientError) as e:
            await interaction.followup.send(embed=build_error_embed("GitHub Request Failed", str(e)), ephemeral=True)
            return

        if not commits:
            await interaction.followup.send(
                embed=build_info_embed("No Commits", f"No commits found on {self.repo}@{self.branch}."),
                ephemeral=True
            )
            return

        embed = self._build_commits_embed(
            list(reversed(commits)),
            title=f"🛠️ Latest {len(commits)} commit{'s' if len(commits) != 1 else ''} to {self.repo}",
        )

        if publish_to == "preview":
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if publish_to == "all_servers":
            result = await self._publish_to_all(embed)
            await interaction.followup.send(embed=self._publish_summary_embed(*result), ephemeral=True)
            return

        if not interaction.guild:
            await interaction.followup.send(
                embed=build_error_embed("Server Required", "This command must be used in a server for current server publishing."),
                ephemeral=True
            )
            return

        channel_id = await get_guild_bot_update_channel(interaction.guild.id)
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not channel:
            await interaction.followup.send(
                embed=build_error_embed(
                    "No Update Channel Configured",
                    "No bot updates channel configured for this server. Use `/set_bot_updates_channel` to configure one."
                ),
                ephemeral=True
            )
            return

        await channel.send(embed=embed)
        await interaction.followup.send(
            embed=build_success_embed("Commits Published", f"Published {len(commits)} commit(s) to {channel.mention}."),
            ephemeral=True
        )

    @github.command(name="status", description="Show GitHub commit tracker status (Bot Moderator only)")
    @bot_moderator_only()
    async def github_status(self, interaction: discord.Interaction):
        last_sha = await get_bot_config(LAST_SHA_KEY, LAST_SHA_SCOPE)
        channels = await get_all_guild_bot_update_channels()

        embed = discord.Embed(title="🛠️ GitHub Commit Tracker", color=PALETTE.PRIMARY)
        embed.add_field(name="Repository", value=f"[{self.repo}](https://github.com/{self.repo})", inline=True)
        embed.add_field(name="Branch", value=f"`{self.branch}`", inline=True)
        embed.add_field(name="Poll Interval", value=f"{config.GITHUB_POLL_MINUTES} min", inline=True)
        embed.add_field(
            name="Background Loop",
            value="🟢 Running" if self.poll_commits.is_running() else "🔴 Stopped",
            inline=True
        )
        embed.add_field(name="Token", value="✅ Configured" if config.GITHUB_TOKEN else "➖ None (60 req/h)", inline=True)
        embed.add_field(name="Servers Receiving Updates", value=str(len(channels)), inline=True)
        embed.add_field(
            name="Last Posted Commit",
            value=f"[`{last_sha[:7]}`](https://github.com/{self.repo}/commit/{last_sha})" if last_sha else "Not initialised yet",
            inline=True
        )
        embed.add_field(
            name="Last Check",
            value=discord.utils.format_dt(self.last_poll_at, "R") if self.last_poll_at else "Not yet",
            inline=True
        )
        if self.last_poll_error:
            embed.add_field(name="⚠️ Last Error", value=self.last_poll_error[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @github.command(name="check", description="Check GitHub for new commits now and post them (Bot Moderator only)")
    @bot_moderator_only()
    async def github_check(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        message, result = await self._run_poll()
        if result:
            embed = self._publish_summary_embed(*result)
            embed.description = f"{message}\n\n{embed.description}"
        elif message.startswith("GitHub poll failed"):
            embed = build_error_embed("GitHub Check Failed", message)
        else:
            embed = build_info_embed("GitHub Check", message)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="set_bot_updates_channel", description="Set channel to receive bot updates and announcements (Admin only)")
    @command_meta(section="Admin", name="Set Bot Updates Channel")
    async def set_bot_updates_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel where bot updates and commit announcements will be published."""
        if interaction.guild is None:
            embed = build_error_embed(
                "Server Required",
                "This command must be used in a server."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            # Check bot can send messages in channel
            bot_member = interaction.guild.me
            perms = channel.permissions_for(bot_member) if bot_member else None
            if perms and not perms.send_messages:
                embed = build_error_embed(
                    "Missing Permissions",
                    "I don't have permission to send messages in that channel."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            await set_guild_bot_update_channel(interaction.guild.id, channel.id)
            embed = build_success_embed(
                "Bot Updates Channel Configured",
                f"Bot updates will be sent to {channel.mention}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting bot updates channel: {e}", exc_info=True)
            embed = build_error_embed(
                "Configuration Error",
                "Failed to set bot updates channel."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            raise e


async def setup(bot: commands.Bot):
    await bot.add_cog(GitHubTracker(bot))
