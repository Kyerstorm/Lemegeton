"""Detailed, implementation-aware privacy notice for Lemegeton."""

from discord import app_commands
import discord
from discord.ext import commands

from helpers.color_palette import PALETTE
from cogs_test.general_commands.dashboard import command_meta


def build_privacy_embeds() -> list[discord.Embed]:
    """Build the current privacy notice without making unsupported security claims."""
    overview = discord.Embed(
        title="🔒 Lemegeton Privacy & Data Notice",
        description=(
            "Privacy is a design goal, but Lemegeton is not a zero-knowledge service. "
            "This notice describes the current code and optional features. Data needed by a feature "
            "may be processed by the bot and by the service operator."
        ),
        color=PALETTE.PRIMARY,
    )
    overview.add_field(
        name="◇ Information we may process",
        value=(
            "Depending on the commands and server features used, this can include Discord user IDs, "
            "usernames/display names and avatars; guild, channel, message and interaction IDs; member, "
            "role, join and invite metadata; command options, search terms, links and lookup identifiers; "
            "AniList usernames/account IDs and Steam vanity names/SteamIDs; server settings; moderation "
            "and audit events; community submissions, sources, tags, votes and discussions; feedback text "
            "and optional screenshots; and AI prompts/responses when an AI feature is used."
        ),
        inline=False,
    )
    overview.add_field(
        name="◇ Message and member access",
        value=(
            "The current bot configuration enables Discord's privileged Message Content and Members "
            "intents. The bot can therefore receive message-content fields and member events/data that Discord "
            "makes available. Loaded listeners inspect messages for supported AniList, Steam and social links; "
            "DM link conversion reads links only after a session is started; feedback features handle DM exchanges; "
            "and the GPT responder only processes a guild message when the bot is explicitly mentioned. Member "
            "events support configured invite tracking, welcome DMs and Custom Role maintenance. This does not mean "
            "every message is permanently archived, but we cannot claim the bot is unable to read messages it receives."
        ),
        inline=False,
    )
    overview.add_field(
        name="◇ What application logs may contain",
        value=(
            "Usage logs may contain user IDs, display names, command names, guild IDs/names and timestamps. "
            "Some feature-specific logs also include supplied identifiers: for example, the AniList/Steam account "
            "value entered during linking and the Steam profile lookup value. Error diagnostics can include command, "
            "user/guild/channel/interaction IDs, exception text and a traceback. Feedback logs include the submitter's "
            "display name/ID, feedback type and Discord message/thread IDs. Invite tracking stores invite codes and "
            "inviter/joiner IDs and names in configured servers. /say audit records store user/guild/channel IDs, "
            "embed state, reply-to message ID and time—not the submitted message text."
        ),
        inline=False,
    )
    overview.add_field(
        name="◇ Where information is stored",
        value=(
            "The main bot stores feature records in PostgreSQL, including linked-account records, guild settings, "
            "moderation/audit data and community content. The optional GPT responder stores per-user/per-guild "
            "user and assistant conversation text in a separate local SQLite database. Feedback text and uploaded "
            "images are posted to the configured Discord feedback channel; a moderator can open a public thread "
            "inside that server. Panel and Custom Role image originals use a private S3-compatible bucket when "
            "configured; generated grids/collages may use a separately configured public bucket. Dashboard sessions "
            "keep the Discord profile and OAuth tokens server-side in memory until expiry or logout."
        ),
        inline=False,
    )
    overview.set_footer(text="Current implementation notice · See the second notice panel for providers, encryption and requests")

    disclosures = discord.Embed(
        title="🔎 Providers, Encryption & Your Choices",
        description="The details below distinguish what the application does from what its hosting and external services may do.",
        color=PALETTE.SECONDARY,
    )
    disclosures.add_field(
        name="◇ External services and recipients",
        value=(
            "Discord processes the platform interactions and messages sent to the bot. Depending on the command, "
            "search terms, URLs, account names or provider IDs may be sent to AniList, Steam, IGDB, TMDB, Google Books, "
            "Novel Updates, Novel Phoenix, NovelFire, Novelist and other sources used by that feature. If you mention "
            "the GPT responder, the message and relevant saved conversation history are sent to its configured chat "
            "provider: the current cog uses a g4f free fallback and can use OpenAI when configured. Hosting, database "
            "and object-storage vendors may also process data to provide infrastructure. Each external provider has "
            "its own terms and privacy practices."
        ),
        inline=False,
    )
    disclosures.add_field(
        name="◇ Encryption: an important distinction",
        value=(
            "Lemegeton is not end-to-end encrypted (E2EE). The bot must receive readable command and message "
            "content to perform the requested feature; the application and authorized operators can access data "
            "available to the running service. Remote PostgreSQL connections are configured to use TLS with "
            "certificate and hostname verification, and external HTTPS/TLS protects supported network connections. "
            "That is encryption in transit, not E2EE. The repository cannot verify that every deployment encrypts "
            "all database backups or object storage at rest. A private S3 bucket restricts access; it does not create "
            "user-held, end-to-end encryption."
        ),
        inline=False,
    )
    disclosures.add_field(
        name="◇ MIT licence and legal requests",
        value=(
            "The MIT licence governs how people may use, copy and distribute the software code. It does not make "
            "a hosted database public, decide who owns personal data, or exempt an operator from applicable law. "
            "It also does not give outside companies automatic access to user records. Our policy is not to sell "
            "personal data or provide companies with blanket database access. If a valid, binding legal request applies, "
            "the operator or an infrastructure provider may be required to disclose data it controls. Requests should "
            "be reviewed and disclosures limited to what applicable law requires; users are notified only where legally permitted."
        ),
        inline=False,
    )
    disclosures.add_field(
        name="◇ Retention and requests",
        value=(
            "There is no single automatic retention period covering every log, database record, conversation or file. "
            "The main bot clears .log files in its logs directory at startup, but that does not delete PostgreSQL "
            "records, GPT conversation history, Discord feedback messages/threads, provider-side copies or stored files. "
            "Some records can remain until a feature-specific cleanup or operator deletion. /login can unlink AniList "
            "or Steam information for the current server, but it is not a complete account-wide erasure. There is not "
            "currently one self-service export/delete command for every data store. For a privacy request, contact the "
            "operator privately through the Support Server linked in /help. Do not use /feedback for private requests: "
            "submissions are posted to the configured feedback channel and may receive a public server thread."
        ),
        inline=False,
    )
    disclosures.add_field(
        name="◇ Our commitments",
        value=(
            "We aim to minimise collection, use information only for the feature or security purpose that needs it, "
            "keep guild-owned records separated, restrict access to operational systems, and avoid advertising profiles "
            "or selling personal data. Do not submit passwords, API keys, authentication tokens or information you do "
            "not want processed by Discord, the bot operator or the provider needed for that feature."
        ),
        inline=False,
    )
    disclosures.set_footer(text="MIT is a software licence, not a privacy or legal-process exemption · Provider behaviour is governed by each provider's terms")
    return [overview, disclosures]


class PrivacyCog(commands.Cog):
    """Publish Lemegeton's detailed privacy and data-use notice."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="privacy",
        description="Read Lemegeton's detailed privacy, data-use, logging and encryption notice",
    )
    @command_meta(section="Utilities", name="Privacy")
    async def privacy(self, interaction: discord.Interaction):
        embeds = build_privacy_embeds()
        await interaction.response.send_message(embed=embeds[0], ephemeral=True)
        await interaction.followup.send(embed=embeds[1], ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PrivacyCog(bot))
