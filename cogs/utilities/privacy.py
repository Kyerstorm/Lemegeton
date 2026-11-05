"""Detailed, implementation-aware privacy notice for Lemegeton."""

from discord import app_commands
import discord
from discord.ext import commands

from cogs.admin.dashboard import command_meta
from helpers.color_palette import PALETTE
from helpers.command_error_handler import FeedbackAwareView


PRIVACY_SECTIONS = (
    ("Introduction", "A quick overview of the privacy notice.", "👋"),
    ("Information processed", "Information features may need to operate.", "🗂️"),
    ("Message and member access", "What the bot can receive and inspect.", "💬"),
    ("Application logs", "Identifiers and activity that may be logged.", "📋"),
    ("Where information is stored", "The databases, channels and storage used.", "🗄️"),
    ("External services", "Providers and infrastructure that may receive data.", "🌐"),
    ("Encryption and E2EE", "What is protected in transit—and what is not.", "🔐"),
    ("Open-source project", "Review the code and how the bot works.", "📖"),
    ("MIT licence and legal requests", "What the licence means and how requests are handled.", "⚖️"),
    ("Retention and privacy requests", "How long information may remain and how to contact us.", "🕒"),
    ("Our commitments", "The principles guiding how information is handled.", "◇"),
)


def build_privacy_embeds() -> list[discord.Embed]:
    """Build the complete privacy notice as navigable, self-contained pages."""
    pages = [
        discord.Embed(
            title="🔒 Lemegeton Privacy",
            description=(
                "Welcome to Lemegeton's privacy notice.\n\n"
                "This is one private, interactive guide. Use the dropdown below to explore what the bot "
                "may process, what can appear in logs, where information is stored, which outside services "
                "may receive it, and what choices are available.\n\n"
                "**An important distinction:** Lemegeton is not end-to-end encrypted (E2EE). "
                "The bot must be able to read the information required to provide its features. "
                "Encryption in transit is not the same as end-to-end encryption.\n\n"
                "Choose a section from the menu below to read the full details."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="Information we may process",
            description=(
                "Depending on the commands and server features used, this can include Discord user IDs, "
                "usernames/display names and avatars; guild, channel, message and interaction IDs; member, "
                "role, join and invite metadata; command options, search terms, links and lookup identifiers; "
                "AniList usernames/account IDs and Steam vanity names/SteamIDs; server settings; moderation "
                "and audit events; community submissions, sources, tags, votes and discussions; feedback text "
                "and optional screenshots; and AI prompts/responses when an AI feature is used."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="Message and member access",
            description=(
                "The current bot configuration enables Discord's privileged Message Content and Members "
                "intents. The bot can therefore receive message-content fields and member events/data that Discord "
                "makes available. Loaded listeners inspect messages for supported AniList, Steam and social links; "
                "DM link conversion reads links only after a session is started; feedback features handle DM exchanges; "
                "and the GPT responder only processes a guild message when the bot is explicitly mentioned. Member "
                "events support configured invite tracking, welcome DMs and Custom Role maintenance. This does not mean "
                "every message is permanently archived, but we cannot claim the bot is unable to read messages it receives."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="What application logs may contain",
            description=(
                "Usage logs may contain user IDs, display names, command names, guild IDs/names and timestamps. "
                "Some feature-specific logs also include supplied identifiers: for example, the AniList/Steam account "
                "value entered during linking and the Steam profile lookup value. Error diagnostics can include command, "
                "user/guild/channel/interaction IDs, exception text and a traceback. Feedback logs include the submitter's "
                "display name/ID, feedback type and Discord message/thread IDs. Invite tracking stores invite codes and "
                "inviter/joiner IDs and names in configured servers. /say audit records store user/guild/channel IDs, "
                "embed state, reply-to message ID and time—not the submitted message text."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="Where information is stored",
            description=(
                "The main bot stores feature records in PostgreSQL, including linked-account records, guild settings, "
                "moderation/audit data and community content. The optional GPT responder stores per-user/per-guild "
                "user and assistant conversation text in a separate local SQLite database. Feedback text and uploaded "
                "images are posted to the configured Discord feedback channel; a moderator can open a public thread "
                "inside that server. Panel and Custom Role image originals use a private S3-compatible bucket when "
                "configured; generated grids/collages may use a separately configured public bucket. Dashboard sessions "
                "keep the Discord profile and OAuth tokens server-side in memory until expiry or logout."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="External services and recipients",
            description=(
                "Discord processes the platform interactions and messages sent to the bot. Depending on the command, "
                "search terms, URLs, account names or provider IDs may be sent to AniList, Steam, IGDB, TMDB, Google Books, "
                "Novel Updates, Novel Phoenix, NovelFire, Novelist and other sources used by that feature. If you mention "
                "the GPT responder, the message and relevant saved conversation history are sent to its configured chat "
                "provider: the current cog uses a g4f free fallback and can use OpenAI when configured. Hosting, database "
                "and object-storage vendors may also process data to provide infrastructure. Each external provider has "
                "its own terms and privacy practices; provider behaviour is governed by those terms."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="Encryption: an important distinction",
            description=(
                "Lemegeton is not end-to-end encrypted (E2EE). The bot must receive readable command and message "
                "content to perform the requested feature; the application and authorized operators can access data "
                "available to the running service. Remote PostgreSQL connections are configured to use TLS with "
                "certificate and hostname verification, and external HTTPS/TLS protects supported network connections. "
                "That is encryption in transit, not E2EE. The repository cannot verify that every deployment encrypts "
                "all database backups or object storage at rest. A private S3 bucket restricts access; it does not create "
                "user-held, end-to-end encryption."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="Lemegeton is open source",
            description=(
                "Lemegeton is an open-source project. You can inspect the source code, review how the bot works, "
                "and contribute through the public GitHub repository: "
                "[Kyerstorm/Lemegeton](https://github.com/Kyerstorm/Lemegeton)."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="MIT licence and legal requests",
            description=(
                "The MIT licence governs how people may use, copy and distribute the software code. It does not make "
                "a hosted database public, decide who owns personal data, or exempt an operator from applicable law. "
                "It also does not give outside companies automatic access to user records. Our policy is not to sell "
                "personal data or provide companies with blanket database access. If a valid, binding legal request applies, "
                "the operator or an infrastructure provider may be required to disclose data it controls. Requests should "
                "be reviewed and disclosures limited to what applicable law requires; users are notified only where legally permitted."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="Retention and privacy requests",
            description=(
                "There is no single automatic retention period covering every log, database record, conversation or file. "
                "The main bot clears .log files in its logs directory at startup, but that does not delete PostgreSQL "
                "records, GPT conversation history, Discord feedback messages/threads, provider-side copies or stored files. "
                "Some records can remain until a feature-specific cleanup or operator deletion. /login can unlink AniList "
                "or Steam information for the current server, but it is not a complete account-wide erasure. There is not "
                "currently one self-service export/delete command for every data store. For a privacy request, contact the "
                "operator privately through the Support Server linked in /help. Do not use /feedback for private requests: "
                "submissions are posted to the configured feedback channel and may receive a public server thread."
            ),
            color=PALETTE.PRIMARY,
        ),
        discord.Embed(
            title="Our commitments",
            description=(
                "We aim to minimise collection, use information only for the feature or security purpose that needs it, "
                "keep guild-owned records separated, restrict access to operational systems, and avoid advertising profiles "
                "or selling personal data. Do not submit passwords, API keys, authentication tokens or information you do "
                "not want processed by Discord, the bot operator or the provider needed for that feature."
            ),
            color=PALETTE.PRIMARY,
        ),
    ]

    for index, embed in enumerate(pages, start=1):
        embed.set_footer(
            text=f"Section {index} of {len(pages)} · Current implementation notice"
        )

    return pages


class PrivacyNavigationView(FeedbackAwareView):
    """Single-message, user-bound navigation for the privacy notice."""

    def __init__(self, user: discord.abc.User, pages: list[discord.Embed]):
        super().__init__(timeout=300)
        self.user = user
        self.pages = pages
        self.message: discord.Message | None = None
        self.add_item(PrivacySectionSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Keep this private menu scoped to the person who opened it."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "This privacy menu belongs to another user. Run /privacy to open your own copy.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        """Disable the dropdown when the private navigation session expires."""
        for item in self.children:
            item.disabled = True

        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class PrivacySectionSelect(discord.ui.Select):
    """Dropdown for switching sections in the existing privacy message."""

    def __init__(self, privacy_view: PrivacyNavigationView):
        self.privacy_view = privacy_view
        options = [
            discord.SelectOption(
                label=label,
                value=str(index),
                description=description,
                emoji=emoji,
                default=index == 0,
            )
            for index, (label, description, emoji) in enumerate(PRIVACY_SECTIONS)
        ]
        super().__init__(
            placeholder="Choose a privacy section…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Edit the current ephemeral message rather than sending another one."""
        selected_value = self.values[0]
        for option in self.options:
            option.default = option.value == selected_value

        await interaction.response.edit_message(
            embed=self.privacy_view.pages[int(selected_value)],
            view=self.privacy_view,
        )


class PrivacyCog(commands.Cog):
    """Publish Lemegeton's detailed privacy and data-use notice."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="privacy",
        description="Read Lemegeton's privacy, data-use, logging and encryption notice",
    )
    @command_meta(section="Utilities", name="Privacy")
    async def privacy(self, interaction: discord.Interaction):
        pages = build_privacy_embeds()
        view = PrivacyNavigationView(interaction.user, pages)
        await interaction.response.send_message(
            embed=pages[0],
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(PrivacyCog(bot))
