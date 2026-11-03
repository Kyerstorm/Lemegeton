"""First-use agreement gate for Lemegeton's Discord commands."""
from __future__ import annotations

import logging

import discord
from discord import app_commands

import database

log = logging.getLogger("Lemegeton.TermsConsent")

# Bump these values whenever the corresponding published policy materially changes.
TERMS_VERSION = "2026-11-03"
PRIVACY_VERSION = "2026-11-03"
GUIDELINES_VERSION = "2026-11-03"

POLICY_LINKS = {
    "Terms of Service": "https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/docs/TERMS_OF_SERVICE.md",
    "Privacy Policy": "https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/docs/PRIVACY_POLICY.md",
    "Community Guidelines": "https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/docs/COMMUNITY_GUIDELINES.md",
}


def build_consent_embed() -> discord.Embed:
    """Build the first-use agreement prompt with direct links to each policy."""
    embed = discord.Embed(
        title="Before using Lemegeton",
        description=(
            "Please review the documents below before continuing. Agreement is required once per "
            "account for the current policy versions. You can open each document on GitHub and "
            "return here to choose **Agree & Continue**.\n\n"
            "The privacy notice explains what the running bot can process, where records may be "
            "stored, and which external providers may receive requests. Lemegeton is not end-to-end encrypted."
        ),
        color=discord.Color(0x62676D),
    )
    for label, url in POLICY_LINKS.items():
        embed.add_field(name=label, value=f"[Read the {label}]({url})", inline=False)
    embed.set_footer(text=f"Policy versions: {TERMS_VERSION} · {PRIVACY_VERSION} · {GUIDELINES_VERSION}")
    return embed


async def init_user_consent_schema() -> None:
    """Create the user-level policy acceptance record without changing guild data."""
    await database.execute_db_operation(
        "initialize first-use policy consent",
        """
        CREATE TABLE IF NOT EXISTS bot_user_consents (
            user_id BIGINT PRIMARY KEY,
            terms_version VARCHAR(32) NOT NULL,
            privacy_version VARCHAR(32) NOT NULL,
            guidelines_version VARCHAR(32) NOT NULL,
            accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    )


async def user_has_current_consent(user_id: int) -> bool:
    """Return whether this Discord account accepted all currently published policies."""
    row = await database.execute_db_operation(
        "check first-use policy consent",
        """SELECT user_id FROM bot_user_consents
           WHERE user_id = ? AND terms_version = ? AND privacy_version = ?
             AND guidelines_version = ?""",
        (user_id, TERMS_VERSION, PRIVACY_VERSION, GUIDELINES_VERSION),
        fetch_type="one",
    )
    return row is not None


class TermsConsentView(discord.ui.View):
    """User-bound agreement controls shared by slash and prefix command prompts."""

    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "This agreement prompt belongs to another Discord account. Run a command to open your own.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Agree & Continue", style=discord.ButtonStyle.primary, emoji="✓")
    async def agree(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            await database.execute_db_operation(
                "save first-use policy consent",
                """
                INSERT INTO bot_user_consents(
                    user_id, terms_version, privacy_version, guidelines_version, accepted_at
                )
                VALUES (?, ?, ?, ?, NOW())
                ON CONFLICT(user_id) DO UPDATE SET
                    terms_version = EXCLUDED.terms_version,
                    privacy_version = EXCLUDED.privacy_version,
                    guidelines_version = EXCLUDED.guidelines_version,
                    accepted_at = NOW()
                """,
                (interaction.user.id, TERMS_VERSION, PRIVACY_VERSION, GUIDELINES_VERSION),
            )
        except Exception:
            log.exception("Could not save policy agreement for user %s", interaction.user.id)
            await interaction.response.send_message(
                "Your agreement could not be saved. Please try again shortly; commands remain locked until it is recorded.",
                ephemeral=True,
            )
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Agreement saved. You can now run Lemegeton's commands. Please rerun the command you originally tried.",
            embed=None,
            view=self,
        )

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Agreement declined. Lemegeton commands remain unavailable until you accept the current policies.",
            embed=None,
            view=self,
        )


class TermsCommandTree(app_commands.CommandTree):
    """Require current policy acceptance before any application command executes."""

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.bot:
            return True
        try:
            if await user_has_current_consent(interaction.user.id):
                return True
        except Exception:
            log.exception("Could not verify policy agreement for user %s", interaction.user.id)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Lemegeton cannot verify your policy agreement right now. Please try again shortly.",
                    ephemeral=True,
                )
            return False

        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=build_consent_embed(),
                view=TermsConsentView(interaction.user.id),
                ephemeral=True,
            )
        return False
