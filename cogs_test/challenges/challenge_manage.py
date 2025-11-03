import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import logging
from pathlib import Path
from typing import Optional, List, Tuple

from database import execute_db_operation

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "challenge_change.log"
ANILIST_API_URL = "https://graphql.anilist.co"
VIEW_TIMEOUT = 120
MAX_TITLE_LENGTH = 100
MAX_MANGA_ID = 999999

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging with auto-clearing
logger = logging.getLogger("ChallengeChange")
logger.setLevel(logging.DEBUG)

if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == str(LOG_FILE)
           for h in logger.handlers):
    try:
        file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
                                                      datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(stream_handler)

logger.info("Challenge Change cog logging system initialized (file or stream fallback)")

class ChallengeManagementView(discord.ui.View):
    """Interactive view for challenge management actions."""
    
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.user_id = user_id
        self.guild_id = guild_id
        logger.debug(f"Created ChallengeManagementView for user ID: {user_id} in guild {guild_id}")

    @discord.ui.button(label="➕ Add Manga", style=discord.ButtonStyle.success, emoji="➕")
    async def add_manga_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show modal for adding manga to challenge."""
        logger.info(f"Add manga button clicked by {interaction.user.display_name} (ID: {self.user_id}) in guild {self.guild_id}")
        
        modal = AddMangaModal(self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🗑️ Remove Manga", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_manga_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show modal for removing manga from challenge."""
        logger.info(f"Remove manga button clicked by {interaction.user.display_name} (ID: {self.user_id}) in guild {self.guild_id}")
        
        modal = RemoveMangaModal(self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📋 List Challenges", style=discord.ButtonStyle.secondary, emoji="📋", row=1)
    async def list_challenges_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show all active challenges for this guild."""
        logger.info(f"List challenges button clicked by {interaction.user.display_name} (ID: {self.user_id}) in guild {self.guild_id}")
        
        await interaction.response.defer(ephemeral=True)
        try:
            challenge_cog = interaction.client.get_cog("ChallengeManage")
            if not challenge_cog:
                await interaction.followup.send("❌ System error: Challenge management not available.", ephemeral=True)
                return

            # Get all challenges for this guild and their manga lists
            challenges_info = await challenge_cog.get_all_guild_challenges(self.guild_id)
            if not challenges_info:
                embed = discord.Embed(
                    title="📋 Guild Challenge List",
                    description="No active challenges found for this server.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Build a list of (challenge_id, title, manga_list)
            challenges_with_manga = []
            for challenge_id, title, _mcount in challenges_info:
                manga_rows = await challenge_cog.get_guild_challenge_manga(self.guild_id, challenge_id)
                # manga_rows is list of tuples (manga_id, title, total_chapters)
                challenges_with_manga.append((challenge_id, title, manga_rows))

            # Paginated view: one page per challenge
            class ChallengeListView(discord.ui.View):
                PER_PAGE = 8

                def __init__(self, challenges, guild_id):
                    super().__init__(timeout=VIEW_TIMEOUT)
                    self.challenges = challenges
                    self.guild_id = guild_id
                    self.index = 0
                    # per-challenge manga page (resets when switching challenges)
                    self.manga_page = 0

                def make_embed(self):
                    cid, ctitle, manga_list = self.challenges[self.index]
                    total = len(manga_list)
                    start = self.manga_page * self.PER_PAGE
                    end = start + self.PER_PAGE
                    page_items = manga_list[start:end]

                    embed = discord.Embed(
                        title=f"📋 {ctitle}",
                        description=f"Guild Challenge ID: `{cid}` • {total} manga • Guild: {interaction.guild.name}",
                        color=discord.Color.blue()
                    )

                    if page_items:
                        description_lines = []
                        for m_id, m_title, m_chapters in page_items:
                            m_title_short = (m_title[:80] + '...') if m_title and len(m_title) > 80 else (m_title or 'Unknown')
                            description_lines.append(f"• **{m_title_short}** (ID: `{m_id}`) • {m_chapters or 'Unknown'} chapters")

                        embed.add_field(name="📚 Manga in this challenge", value="\n".join(description_lines), inline=False)
                    else:
                        embed.add_field(name="📚 Manga in this challenge", value="No manga in this challenge.", inline=False)

                    # Footer shows challenge page and manga subpage
                    total_pages = (len(self.challenges))
                    manga_pages = (total - 1) // self.PER_PAGE + 1 if total > 0 else 1
                    embed.set_footer(text=f"Challenge {self.index + 1}/{total_pages} • Showing {start + 1 if total>0 else 0}-{min(end, total)} of {total} • Manga page {self.manga_page + 1}/{manga_pages}")
                    return embed

                @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
                async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if self.index > 0:
                        self.index -= 1
                        self.manga_page = 0
                        await interaction.response.edit_message(embed=self.make_embed(), view=self)
                    else:
                        await interaction.response.defer()

                @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary)
                async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if self.index < len(self.challenges) - 1:
                        self.index += 1
                        self.manga_page = 0
                        await interaction.response.edit_message(embed=self.make_embed(), view=self)
                    else:
                        await interaction.response.defer()

                @discord.ui.button(label="More", style=discord.ButtonStyle.primary)
                async def more(self, interaction: discord.Interaction, button: discord.ui.Button):
                    # Advance manga subpage within current challenge
                    cid, _ctitle, manga_list = self.challenges[self.index]
                    total = len(manga_list)
                    manga_pages = (total - 1) // self.PER_PAGE + 1 if total > 0 else 1
                    if self.manga_page < manga_pages - 1:
                        self.manga_page += 1
                        await interaction.response.edit_message(embed=self.make_embed(), view=self)
                    else:
                        # No more pages; wrap or just defer
                        await interaction.response.defer()

                @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
                async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
                    for item in self.children:
                        item.disabled = True
                    await interaction.response.edit_message(embed=self.make_embed(), view=self)

                async def on_timeout(self):
                    for item in self.children:
                        item.disabled = True

            view = ChallengeListView(challenges_with_manga, self.guild_id)
            await interaction.followup.send(embed=view.make_embed(), view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing challenges for guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send("❌ Error retrieving challenge list.", ephemeral=True)

    @discord.ui.button(label="🎭 Manage Roles", style=discord.ButtonStyle.primary, emoji="🎭", row=1)
    async def manage_roles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show challenge role management submenu."""
        logger.info(f"Manage roles button clicked by {interaction.user.display_name} (ID: {self.user_id}) in guild {self.guild_id}")
        
        # Show role management submenu
        embed = discord.Embed(
            title="🎭 Challenge Role Management",
            description=f"Manage automatic role rewards for **{interaction.guild.name}** challenges.\n\n"
                       "When users reach specific point thresholds in challenges, they can automatically receive roles!",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="⚙️ Available Actions",
            value=(
                "**➕ Setup Role** - Configure a role for a challenge threshold\n"
                "**📋 View Roles** - See all configured challenge roles\n"
                "**🗑️ Remove Role** - Remove a role configuration"
            ),
            inline=False
        )
        
        embed.set_footer(text="Configure roles to automatically reward challenge participants")
        
        view = ChallengeRoleManagementView(self.user_id, self.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🔍 Search Manga", style=discord.ButtonStyle.primary, emoji="🔍")
    async def search_manga_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show information about a specific manga."""
        logger.info(f"Search manga button clicked by {interaction.user.display_name} (ID: {self.user_id}) in guild {self.guild_id}")
        
        modal = SearchMangaModal(self.guild_id)
        await interaction.response.send_modal(modal)

    async def on_timeout(self):
        """Handle view timeout by disabling buttons."""
        try:
            self.clear_items()
            logger.debug(f"ChallengeManagementView timed out for user ID: {self.user_id} in guild {self.guild_id}")
        except Exception as e:
            logger.error(f"Error handling ChallengeManagementView timeout: {e}", exc_info=True)

    @discord.ui.button(label="🗑️ Delete Challenge", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def delete_challenge_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show modal to delete a challenge by ID."""
        logger.info(f"Delete challenge button clicked by {interaction.user.display_name} (ID: {self.user_id}) in guild {self.guild_id}")
        modal = DeleteChallengeModal(self.guild_id)
        await interaction.response.send_modal(modal)


class ChallengeRoleManagementView(discord.ui.View):
    """View for managing challenge roles - submenu of main challenge management."""
    
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.user_id = user_id
        self.guild_id = guild_id
        logger.debug(f"Created ChallengeRoleManagementView for user ID: {user_id} in guild {guild_id}")
    
    @discord.ui.button(label="➕ Setup Role", style=discord.ButtonStyle.success, emoji="➕")
    async def setup_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show modal for setting up a challenge role."""
        logger.info(f"Setup role button clicked by {interaction.user.display_name} (ID: {self.user_id}) in guild {self.guild_id}")
        modal = SetupChallengeRoleModal(self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 View Roles", style=discord.ButtonStyle.primary, emoji="📋")
    async def view_roles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show all configured challenge roles."""
        logger.info(f"View roles button clicked by {interaction.user.display_name} (ID: {self.user_id}) in guild {self.guild_id}")
        
        await interaction.response.defer(ephemeral=True)
        try:
            from database import get_guild_challenge_roles
            
            roles_config = await get_guild_challenge_roles(self.guild_id)
            
            if not roles_config:
                embed = discord.Embed(
                    title="📋 Challenge Roles Configuration",
                    description="No challenge roles are currently configured.\n\nUse the **Setup Role** button to configure challenge roles for this server.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🎯 Challenge Roles Configuration",
                description=f"Challenge roles configured for **{interaction.guild.name}**",
                color=discord.Color.purple()
            )
            
            for challenge_id in sorted(roles_config.keys()):
                thresholds = roles_config[challenge_id]
                role_info = []
                
                for threshold in sorted(thresholds.keys()):
                    role_id = thresholds[threshold]
                    role = interaction.guild.get_role(role_id)
                    role_mention = role.mention if role else f"<@&{role_id}> (deleted)"
                    role_info.append(f"**{threshold} points** → {role_mention}")
                
                embed.add_field(
                    name=f"Challenge {challenge_id}",
                    value="\n".join(role_info),
                    inline=True
                )
            
            embed.set_footer(text="Users automatically receive roles when reaching these thresholds")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Listed {len(roles_config)} challenge role configurations for guild {self.guild_id}")
        
        except Exception as e:
            logger.error(f"Error viewing challenge roles for guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send("❌ Error retrieving challenge roles.", ephemeral=True)
    
    @discord.ui.button(label="🗑️ Remove Role", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show modal for removing a challenge role configuration."""
        logger.info(f"Remove role button clicked by {interaction.user.display_name} (ID: {self.user_id}) in guild {self.guild_id}")
        modal = RemoveChallengeRoleModal(self.guild_id)
        await interaction.response.send_modal(modal)
    
    async def on_timeout(self):
        """Handle view timeout by disabling buttons."""
        try:
            self.clear_items()
            logger.debug(f"ChallengeRoleManagementView timed out for user ID: {self.user_id} in guild {self.guild_id}")
        except Exception as e:
            logger.error(f"Error handling ChallengeRoleManagementView timeout: {e}", exc_info=True)


class SetupChallengeRoleModal(discord.ui.Modal):
    """Modal for setting up a challenge role."""
    
    def __init__(self, guild_id: int):
        super().__init__(title="➕ Setup Challenge Role")
        self.guild_id = guild_id
    
    challenge_id = discord.ui.TextInput(
        label="Challenge ID (1-13)",
        placeholder="Enter challenge ID",
        required=True,
        max_length=2
    )
    
    role_id = discord.ui.TextInput(
        label="Role ID or Mention",
        placeholder="Enter role ID or @role mention",
        required=True,
        max_length=100
    )
    
    threshold = discord.ui.TextInput(
        label="Points Threshold",
        placeholder="Enter points threshold (e.g., 1.0, 5.0, 10.0)",
        required=True,
        default="1.0",
        max_length=10
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            from database import set_guild_challenge_role
            
            # Validate and parse challenge ID
            challenge_id_value = int(self.challenge_id.value.strip())
            if challenge_id_value < 1 or challenge_id_value > 13:
                await interaction.followup.send("❌ Challenge ID must be between 1 and 13.", ephemeral=True)
                return
            
            # Parse role ID
            role_id_str = self.role_id.value.strip()
            role_id_str = role_id_str.replace("<@&", "").replace(">", "")
            role_id_value = int(role_id_str)
            
            # Get the role
            role = interaction.guild.get_role(role_id_value)
            if not role:
                await interaction.followup.send("❌ Role not found. Please check the role ID.", ephemeral=True)
                return
            
            # Validate threshold
            threshold_value = float(self.threshold.value.strip())
            if threshold_value <= 0:
                await interaction.followup.send("❌ Threshold must be greater than 0.", ephemeral=True)
                return
            
            # Check bot permissions
            if not interaction.guild.me.guild_permissions.manage_roles:
                await interaction.followup.send("❌ I don't have permission to manage roles in this server.", ephemeral=True)
                return
            
            if role >= interaction.guild.me.top_role:
                await interaction.followup.send("❌ I cannot manage that role because it's higher than or equal to my highest role.", ephemeral=True)
                return
            
            # Set the challenge role
            await set_guild_challenge_role(self.guild_id, challenge_id_value, threshold_value, role.id)
            
            embed = discord.Embed(
                title="✅ Challenge Role Configured",
                description=(
                    f"**Challenge:** {challenge_id_value}\n"
                    f"**Role:** {role.mention}\n"
                    f"**Threshold:** {threshold_value} points\n\n"
                    f"Users who reach this threshold will automatically receive the role!"
                ),
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Challenge role configured for guild {self.guild_id}: Challenge {challenge_id_value} -> {role.name} ({role.id}) at {threshold_value} points")
        
        except ValueError as e:
            await interaction.followup.send(f"❌ Invalid input format: {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting up challenge role: {e}", exc_info=True)
            await interaction.followup.send("❌ Error setting up challenge role.", ephemeral=True)


class RemoveChallengeRoleModal(discord.ui.Modal):
    """Modal for removing a challenge role configuration."""
    
    def __init__(self, guild_id: int):
        super().__init__(title="🗑️ Remove Challenge Role")
        self.guild_id = guild_id
    
    challenge_id = discord.ui.TextInput(
        label="Challenge ID (1-13)",
        placeholder="Enter challenge ID",
        required=True,
        max_length=2
    )
    
    threshold = discord.ui.TextInput(
        label="Threshold (optional)",
        placeholder="Leave empty to remove all thresholds for this challenge",
        required=False,
        max_length=10
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            from database import remove_guild_challenge_role
            
            # Validate and parse challenge ID
            challenge_id_value = int(self.challenge_id.value.strip())
            if challenge_id_value < 1 or challenge_id_value > 13:
                await interaction.followup.send("❌ Challenge ID must be between 1 and 13.", ephemeral=True)
                return
            
            # Parse threshold if provided
            threshold_value = None
            if self.threshold.value.strip():
                threshold_value = float(self.threshold.value.strip())
            
            # Remove the challenge role
            await remove_guild_challenge_role(self.guild_id, challenge_id_value, threshold_value)
            
            if threshold_value is not None:
                embed = discord.Embed(
                    title="✅ Challenge Role Removed",
                    description=(
                        f"**Challenge:** {challenge_id_value}\n"
                        f"**Threshold:** {threshold_value} points\n\n"
                        f"Role configuration has been removed."
                    ),
                    color=discord.Color.green()
                )
                logger.info(f"Removed challenge role for guild {self.guild_id}: Challenge {challenge_id_value} at {threshold_value} points")
            else:
                embed = discord.Embed(
                    title="✅ Challenge Roles Removed",
                    description=(
                        f"**Challenge:** {challenge_id_value}\n\n"
                        f"All role configurations for this challenge have been removed."
                    ),
                    color=discord.Color.green()
                )
                logger.info(f"Removed all challenge roles for guild {self.guild_id}: Challenge {challenge_id_value}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        except ValueError as e:
            await interaction.followup.send(f"❌ Invalid input format: {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error removing challenge role: {e}", exc_info=True)
            await interaction.followup.send("❌ Error removing challenge role.", ephemeral=True)


class AddMangaModal(discord.ui.Modal):
    """Modal for adding manga to challenges."""
    
    def __init__(self, guild_id: int):
        super().__init__(title="➕ Add Manga to Challenge")
        self.guild_id = guild_id
        
        self.challenge_title = discord.ui.TextInput(
            label="Challenge Title",
            placeholder="Enter challenge title (will be created if it doesn't exist)",
            required=True,
            max_length=MAX_TITLE_LENGTH
        )
        self.add_item(self.challenge_title)
        
        self.manga_id = discord.ui.TextInput(
            label="AniList Manga ID",
            placeholder="Enter the AniList manga ID number",
            required=True,
            max_length=10
        )
        self.add_item(self.manga_id)
        
        self.total_chapters = discord.ui.TextInput(
            label="Total Chapters (Optional)",
            placeholder="Override chapter count (leave blank to use AniList data)",
            required=False,
            max_length=10
        )
        self.add_item(self.total_chapters)
        
        logger.debug(f"Created AddMangaModal for guild {guild_id}")

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission for adding manga."""
        logger.info(f"Add manga modal submitted by {interaction.user.display_name} (ID: {interaction.user.id}) in guild {self.guild_id}")
        logger.debug(f"Parameters: title='{self.challenge_title.value}', manga_id='{self.manga_id.value}', chapters='{self.total_chapters.value}'")
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validate manga ID
            try:
                manga_id_int = int(self.manga_id.value.strip())
                if manga_id_int <= 0 or manga_id_int > MAX_MANGA_ID:
                    await interaction.followup.send("❌ Invalid manga ID. Must be a positive number.", ephemeral=True)
                    return
            except ValueError:
                await interaction.followup.send("❌ Invalid manga ID. Must be a number.", ephemeral=True)
                return
            
            # Validate chapters if provided
            chapters_override = None
            if self.total_chapters.value.strip():
                try:
                    chapters_override = int(self.total_chapters.value.strip())
                    if chapters_override <= 0:
                        await interaction.followup.send("❌ Total chapters must be a positive number.", ephemeral=True)
                        return
                except ValueError:
                    await interaction.followup.send("❌ Invalid chapter count. Must be a number.", ephemeral=True)
                    return
            
            # Process the request
            challenge_cog = interaction.client.get_cog("ChallengeManage")
            if challenge_cog:
                result = await challenge_cog.handle_add_manga(
                    self.guild_id,
                    self.challenge_title.value.strip(),
                    manga_id_int,
                    chapters_override
                )
                await interaction.followup.send(result, ephemeral=True)
            else:
                await interaction.followup.send("❌ System error: Challenge management not available.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in add manga modal for guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while adding manga.", ephemeral=True)


class RemoveMangaModal(discord.ui.Modal):
    """Modal for removing manga from challenges."""
    
    def __init__(self, guild_id: int):
        super().__init__(title="🗑️ Remove Manga from Challenge")
        self.guild_id = guild_id
        
        self.manga_id = discord.ui.TextInput(
            label="AniList Manga ID",
            placeholder="Enter the AniList manga ID to remove",
            required=True,
            max_length=10
        )
        self.add_item(self.manga_id)
        
        logger.debug(f"Created RemoveMangaModal for guild {guild_id}")

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission for removing manga."""
        logger.info(f"Remove manga modal submitted by {interaction.user.display_name} (ID: {interaction.user.id}) in guild {self.guild_id}")
        logger.debug(f"Parameters: manga_id='{self.manga_id.value}'")
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validate manga ID
            try:
                manga_id_int = int(self.manga_id.value.strip())
                if manga_id_int <= 0 or manga_id_int > MAX_MANGA_ID:
                    await interaction.followup.send("❌ Invalid manga ID. Must be a positive number.", ephemeral=True)
                    return
            except ValueError:
                await interaction.followup.send("❌ Invalid manga ID. Must be a number.", ephemeral=True)
                return
            
            # Process the request
            challenge_cog = interaction.client.get_cog("ChallengeManage")
            if challenge_cog:
                result = await challenge_cog.handle_remove_manga(self.guild_id, manga_id_int)
                await interaction.followup.send(result, ephemeral=True)
            else:
                await interaction.followup.send("❌ System error: Challenge management not available.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in remove manga modal for guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while removing manga.", ephemeral=True)


class DeleteChallengeModal(discord.ui.Modal):
    """Modal for deleting a challenge by ID."""

    def __init__(self, guild_id: int):
        super().__init__(title="🗑️ Delete Challenge")
        self.guild_id = guild_id

        self.challenge_id = discord.ui.TextInput(
            label="Challenge ID",
            placeholder="Enter the numeric challenge ID to delete",
            required=True,
            max_length=20
        )
        self.add_item(self.challenge_id)

        logger.debug(f"Created DeleteChallengeModal for guild {guild_id}")

    async def on_submit(self, interaction: discord.Interaction):
        logger.info(f"Delete challenge modal submitted by {interaction.user.display_name} (ID: {interaction.user.id}) in guild {self.guild_id}")
        await interaction.response.defer(ephemeral=True)

        try:
            try:
                cid = int(self.challenge_id.value.strip())
            except ValueError:
                await interaction.followup.send("❌ Invalid Challenge ID. Must be a number.", ephemeral=True)
                return

            challenge_cog = interaction.client.get_cog("ChallengeManage")
            if challenge_cog:
                result = await challenge_cog.handle_delete_challenge(self.guild_id, cid)
                await interaction.followup.send(result, ephemeral=True)
            else:
                await interaction.followup.send("❌ System error: Challenge management not available.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in delete challenge modal for guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while deleting the challenge.", ephemeral=True)


class SearchMangaModal(discord.ui.Modal):
    """Modal for searching manga information."""
    
    def __init__(self, guild_id: int):
        super().__init__(title="🔍 Search Manga Information")
        self.guild_id = guild_id
        
        self.manga_id = discord.ui.TextInput(
            label="AniList Manga ID",
            placeholder="Enter the AniList manga ID to search for",
            required=True,
            max_length=10
        )
        self.add_item(self.manga_id)
        
        logger.debug(f"Created SearchMangaModal for guild {guild_id}")

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission for searching manga."""
        logger.info(f"Search manga modal submitted by {interaction.user.display_name} (ID: {interaction.user.id}) in guild {self.guild_id}")
        logger.debug(f"Parameters: manga_id='{self.manga_id.value}'")
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validate manga ID
            try:
                manga_id_int = int(self.manga_id.value.strip())
                if manga_id_int <= 0 or manga_id_int > MAX_MANGA_ID:
                    await interaction.followup.send("❌ Invalid manga ID. Must be a positive number.", ephemeral=True)
                    return
            except ValueError:
                await interaction.followup.send("❌ Invalid manga ID. Must be a number.", ephemeral=True)
                return
            
            # Process the request
            challenge_cog = interaction.client.get_cog("ChallengeManage")
            if challenge_cog:
                result = await challenge_cog.handle_search_manga(self.guild_id, manga_id_int)
                await interaction.followup.send(embed=result, ephemeral=True)
            else:
                await interaction.followup.send("❌ System error: Challenge management not available.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in search manga modal for guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while searching for manga.", ephemeral=True)

class ChallengeManage(commands.Cog):
    """Discord cog for interactive challenge management with guild-specific support."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Challenge Management cog initialized with guild-specific support")

    async def get_all_guild_challenges(self, guild_id: int) -> List[Tuple[int, str, int]]:
        """Get all challenges for a specific guild with manga counts. Returns list of (challenge_id, title, manga_count)."""
        try:
            logger.debug(f"Retrieving all challenges for guild {guild_id}")
            
            challenges = await execute_db_operation(
                f"get all challenges for guild {guild_id}",
                """
                SELECT gc.challenge_id, gc.title, COUNT(cm.manga_id) as manga_count
                FROM guild_challenges gc
                LEFT JOIN guild_challenge_manga cm ON gc.challenge_id = cm.challenge_id AND gc.guild_id = cm.guild_id
                WHERE gc.guild_id = ?
                GROUP BY gc.challenge_id, gc.title
                ORDER BY gc.title
                """,
                (guild_id,),
                fetch_type='all'
            )
            
            logger.info(f"Retrieved {len(challenges) if challenges else 0} challenges for guild {guild_id}")
            return challenges or []
                
        except Exception as e:
            logger.error(f"Error retrieving challenges for guild {guild_id}: {e}", exc_info=True)
            return []

    async def get_guild_challenge_manga(self, guild_id: int, challenge_id: int) -> List[Tuple[int, str, int]]:
        """Return list of manga for a given guild challenge as (manga_id, title, total_chapters)."""
        try:
            logger.debug(f"Retrieving manga for challenge {challenge_id} in guild {guild_id}")
            
            manga_list = await execute_db_operation(
                f"get manga for challenge {challenge_id} in guild {guild_id}",
                """
                SELECT manga_id, title, total_chapters 
                FROM guild_challenge_manga 
                WHERE guild_id = ? AND challenge_id = ? 
                ORDER BY title
                """,
                (guild_id, challenge_id),
                fetch_type='all'
            )
            
            logger.debug(f"Retrieved {len(manga_list) if manga_list else 0} manga entries for challenge {challenge_id} in guild {guild_id}")
            return manga_list or []
            
        except Exception as e:
            logger.error(f"Error fetching manga for challenge {challenge_id} in guild {guild_id}: {e}", exc_info=True)
            return []

    async def handle_add_manga(self, guild_id: int, title: str, manga_id: int, total_chapters: Optional[int] = None) -> str:
        """Handle adding manga to guild-specific challenge with validation and logging."""
        logger.info(f"Processing add manga request for guild {guild_id}: title='{title}', manga_id={manga_id}, chapters={total_chapters}")
        
        try:
            # Check if manga already exists in any challenge for this guild
            existing_info = await self._check_guild_manga_exists(guild_id, manga_id)
            if existing_info:
                existing_challenge_id, existing_manga_title = existing_info
                existing_challenge_title = await self._get_guild_challenge_info(guild_id, existing_challenge_id)
                return (f"⚠️ Manga **{existing_manga_title}** (ID: `{manga_id}`) already exists in challenge "
                       f"**{existing_challenge_title or 'Unknown'}** (ID: {existing_challenge_id}) for this server.")

            # Get or create guild-specific challenge
            challenge_id = await self._get_or_create_guild_challenge(guild_id, title)

            # Get manga information
            if total_chapters is not None:
                manga_title = f"Manga {manga_id}"
                logger.debug(f"Using provided chapter count: {total_chapters}")
            else:
                anilist_info = await self._fetch_anilist_manga_info(manga_id)
                if not anilist_info:
                    return (f"⚠️ Manga ID `{manga_id}` not found on AniList or API error occurred. "
                           f"Please try again or specify total chapters manually.")
                
                manga_title, total_chapters = anilist_info

            # Add manga to guild challenge
            await self._add_manga_to_guild_challenge(guild_id, challenge_id, manga_id, manga_title, total_chapters)

            logger.info(f"Successfully added manga '{manga_title}' (ID: {manga_id}) to challenge '{title}' (ID: {challenge_id}) in guild {guild_id}")
            return f"✅ Manga **{manga_title}** ({total_chapters} chapters) added to challenge **{title}** for this server!"
                
        except Exception as e:
            logger.error(f"Error in handle_add_manga for guild {guild_id}: {e}", exc_info=True)
            return "❌ An error occurred while adding manga to the challenge. Please try again later."

    async def handle_remove_manga(self, guild_id: int, manga_id: int) -> str:
        """Handle removing manga from guild-specific challenge with validation and logging."""
        logger.info(f"Processing remove manga request for guild {guild_id}: manga_id={manga_id}")
        
        try:
            # Check if manga exists in any challenge for this guild
            existing_info = await self._check_guild_manga_exists(guild_id, manga_id)
            if not existing_info:
                return f"⚠️ Manga ID `{manga_id}` is not currently in any challenge for this server."

            existing_challenge_id, existing_manga_title = existing_info
            existing_challenge_title = await self._get_guild_challenge_info(guild_id, existing_challenge_id)

            # Remove manga from guild challenge
            removal_success = await self._remove_manga_from_guild_challenge(guild_id, manga_id)
            
            if removal_success:
                logger.info(f"Successfully removed manga '{existing_manga_title}' (ID: {manga_id}) from challenge '{existing_challenge_title}' (ID: {existing_challenge_id}) in guild {guild_id}")
                return (f"✅ Manga **{existing_manga_title}** (ID: `{manga_id}`) "
                       f"removed from challenge **{existing_challenge_title or 'Unknown'}** for this server!")
            else:
                return f"⚠️ Failed to remove manga ID `{manga_id}` from challenge. It may have been removed already."
                    
        except Exception as e:
            logger.error(f"Error in handle_remove_manga for guild {guild_id}: {e}", exc_info=True)
            return "❌ An error occurred while removing manga from the challenge. Please try again later."

    async def handle_delete_challenge(self, guild_id: int, challenge_id: int) -> str:
        """Delete a guild-specific challenge and all its manga entries. Returns a user-facing status string."""
        logger.info(f"Processing delete challenge request for guild {guild_id}: challenge_id={challenge_id}")
        
        try:
            # Check if challenge exists for this guild
            challenge_title = await self._get_guild_challenge_info(guild_id, challenge_id)
            if not challenge_title:
                return f"⚠️ Challenge ID `{challenge_id}` does not exist for this server."

            # Delete related manga entries for this guild challenge
            await execute_db_operation(
                f"delete manga entries for challenge {challenge_id} in guild {guild_id}",
                "DELETE FROM guild_challenge_manga WHERE guild_id = ? AND challenge_id = ?",
                (guild_id, challenge_id)
            )
            
            # Delete guild challenge
            await execute_db_operation(
                f"delete challenge {challenge_id} in guild {guild_id}",
                "DELETE FROM guild_challenges WHERE guild_id = ? AND challenge_id = ?",
                (guild_id, challenge_id)
            )

            logger.info(f"Successfully deleted challenge '{challenge_title}' (ID: {challenge_id}) and its manga entries from guild {guild_id}")
            return f"✅ Challenge **{challenge_title}** (ID: {challenge_id}) and its manga entries have been deleted from this server."

        except Exception as e:
            logger.error(f"Error deleting challenge {challenge_id} from guild {guild_id}: {e}", exc_info=True)
            return "❌ An error occurred while deleting the challenge. Please try again later."

    async def handle_search_manga(self, guild_id: int, manga_id: int) -> discord.Embed:
        """Handle searching for manga information and return a guild-specific embed."""
        logger.info(f"Processing search manga request for guild {guild_id}: manga_id={manga_id}")
        
        try:
            # Get AniList information
            anilist_info = await self._fetch_anilist_manga_info(manga_id)
            
            # Check if manga is in any challenge for this guild
            challenge_info = await self._check_guild_manga_exists(guild_id, manga_id)
            
            if not anilist_info:
                embed = discord.Embed(
                    title="🔍 Manga Search Results",
                    description=f"❌ Manga ID `{manga_id}` not found on AniList.",
                    color=discord.Color.red()
                )
                return embed
            
            manga_title, total_chapters = anilist_info
            
            embed = discord.Embed(
                title="🔍 Manga Information",
                description=f"**{manga_title}**",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="📊 Details",
                value=f"**ID:** `{manga_id}`\n**Chapters:** {total_chapters or 'Unknown'}",
                inline=True
            )
            
            if challenge_info:
                challenge_id, _ = challenge_info
                challenge_title = await self._get_guild_challenge_info(guild_id, challenge_id)
                embed.add_field(
                    name="🎯 Challenge Status (This Server)",
                    value=f"✅ In challenge: **{challenge_title or 'Unknown'}**\n(ID: {challenge_id})",
                    inline=True
                )
            else:
                embed.add_field(
                    name="🎯 Challenge Status (This Server)",
                    value="❌ Not in any challenge",
                    inline=True
                )
            
            embed.set_footer(text=f"AniList ID: {manga_id} • Guild-specific results")
            
            logger.info(f"Successfully retrieved information for manga '{manga_title}' (ID: {manga_id}) in guild {guild_id}")
            return embed
                
        except Exception as e:
            logger.error(f"Error in handle_search_manga for guild {guild_id}: {e}", exc_info=True)
            embed = discord.Embed(
                title="🔍 Manga Search Results",
                description="❌ An error occurred while searching for manga information.",
                color=discord.Color.red()
            )
            return embed

    async def _check_guild_manga_exists(self, guild_id: int, manga_id: int) -> tuple[int, str] | None:
        """Check if manga already exists in any challenge for a specific guild. Returns (challenge_id, manga_title) if exists."""
        try:
            logger.debug(f"Checking if manga ID {manga_id} exists in any challenge for guild {guild_id}")
            
            result = await execute_db_operation(
                f"check manga {manga_id} exists in guild {guild_id}",
                "SELECT challenge_id, title FROM guild_challenge_manga WHERE guild_id = ? AND manga_id = ?",
                (guild_id, manga_id),
                fetch_type='one'
            )
            
            if result:
                logger.debug(f"Manga ID {manga_id} found in challenge ID {result[0]}: '{result[1]}' for guild {guild_id}")
                return (result[0], result[1])
            else:
                logger.debug(f"Manga ID {manga_id} not found in any challenge for guild {guild_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error checking manga existence for guild {guild_id}: {e}", exc_info=True)
            raise

    async def _get_or_create_guild_challenge(self, guild_id: int, title: str) -> int:
        """Get existing guild challenge or create new one. Returns challenge_id."""
        try:
            logger.debug(f"Checking if challenge '{title}' exists for guild {guild_id}")
            
            result = await execute_db_operation(
                f"get challenge '{title}' for guild {guild_id}",
                "SELECT challenge_id FROM guild_challenges WHERE guild_id = ? AND title = ?",
                (guild_id, title),
                fetch_type='one'
            )
            
            if result:
                challenge_id = result[0]
                logger.info(f"Challenge '{title}' exists (ID: {challenge_id}) for guild {guild_id}")
                return challenge_id
            else:
                logger.debug(f"Creating new challenge '{title}' for guild {guild_id}")
                
                result = await execute_db_operation(
                    f"create challenge '{title}' for guild {guild_id}",
                    "INSERT INTO guild_challenges (guild_id, title) VALUES (?, ?)",
                    (guild_id, title),
                    fetch_type='lastrowid'
                )
                
                challenge_id = result
                logger.info(f"Created new challenge '{title}' (ID: {challenge_id}) for guild {guild_id}")
                return challenge_id
                
        except Exception as e:
            logger.error(f"Error managing guild challenge for guild {guild_id}: {e}", exc_info=True)
            raise

    async def _get_guild_challenge_info(self, guild_id: int, challenge_id: int) -> str | None:
        """Get guild challenge title by ID. Returns title or None if not found."""
        try:
            logger.debug(f"Getting challenge info for ID {challenge_id} in guild {guild_id}")
            
            result = await execute_db_operation(
                f"get challenge info for ID {challenge_id} in guild {guild_id}",
                "SELECT title FROM guild_challenges WHERE guild_id = ? AND challenge_id = ?",
                (guild_id, challenge_id),
                fetch_type='one'
            )
            
            if result:
                logger.debug(f"Challenge ID {challenge_id} found: '{result[0]}' for guild {guild_id}")
                return result[0]
            else:
                logger.warning(f"Challenge ID {challenge_id} not found for guild {guild_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting guild challenge info for guild {guild_id}: {e}", exc_info=True)
            raise

    async def _fetch_anilist_manga_info(self, manga_id: int) -> tuple[str, int] | None:
        """Fetch manga information from AniList API. Returns (title, chapters) or None."""
        query = """
        query ($id: Int) {
          Media(id: $id, type: MANGA) {
            id
            title {
              romaji
              english
            }
            chapters
          }
        }
        """
        
        try:
            logger.debug(f"Fetching manga info from AniList for ID {manga_id}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    ANILIST_API_URL,
                    json={"query": query, "variables": {"id": manga_id}},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"AniList API returned status {resp.status} for manga {manga_id}")
                        return None
                        
                    data = await resp.json()
                    
            media = data.get("data", {}).get("Media")
            if not media:
                logger.warning(f"Manga ID {manga_id} not found on AniList")
                return None
                
            manga_title = media["title"].get("romaji") or media["title"].get("english") or "Unknown Title"
            total_chapters = media.get("chapters") or 0
            
            logger.info(f"Successfully fetched AniList data for '{manga_title}' ({total_chapters} chapters)")
            return (manga_title, total_chapters)
            
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching AniList data for manga {manga_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching AniList data: {e}", exc_info=True)
            return None

    async def _add_manga_to_guild_challenge(
        self, guild_id: int, challenge_id: int, manga_id: int, 
        manga_title: str, total_chapters: int
    ):
        """Add manga to guild challenge in database."""
        try:
            logger.debug(f"Adding manga '{manga_title}' (ID: {manga_id}) to challenge {challenge_id} in guild {guild_id}")
            
            await execute_db_operation(
                f"add manga {manga_id} to challenge {challenge_id} in guild {guild_id}",
                """
                INSERT INTO guild_challenge_manga (guild_id, challenge_id, manga_id, title, total_chapters)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, challenge_id, manga_id, manga_title, total_chapters)
            )
            
            logger.info(f"Successfully added manga '{manga_title}' (ID: {manga_id}) to challenge {challenge_id} in guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error adding manga to guild challenge for guild {guild_id}: {e}", exc_info=True)
            raise

    async def _remove_manga_from_guild_challenge(self, guild_id: int, manga_id: int) -> bool:
        """Remove manga from guild challenge in database. Returns True if removed, False if not found."""
        try:
            logger.debug(f"Removing manga ID {manga_id} from challenge in guild {guild_id}")
            
            result = await execute_db_operation(
                f"remove manga {manga_id} from challenge in guild {guild_id}",
                "DELETE FROM guild_challenge_manga WHERE guild_id = ? AND manga_id = ?",
                (guild_id, manga_id),
                fetch_type='rowcount'
            )
            
            if result > 0:
                logger.info(f"Successfully removed manga ID {manga_id} from challenge in guild {guild_id}")
                return True
            else:
                logger.warning(f"Manga ID {manga_id} not found in any challenge for removal in guild {guild_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing manga from guild challenge for guild {guild_id}: {e}", exc_info=True)
            raise

    @app_commands.command(
        name="challenge-manage",
        description="🎯 Interactive challenge management - add, remove manga, and manage challenge roles"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def challenge_manage(self, interaction: discord.Interaction):
        """Interactive guild-specific challenge management interface."""
        try:
            guild_id = interaction.guild.id
            logger.info(f"Challenge-manage command invoked by {interaction.user.display_name} "
                       f"({interaction.user.id}) in guild {guild_id} ({interaction.guild.name})")
            
            embed = discord.Embed(
                title="🎯 Guild Challenge Management",
                description=f"Welcome **{interaction.user.display_name}**!\n\n"
                           f"Use the buttons below to manage challenges for **{interaction.guild.name}**:\n\n"
                           f"➕ **Add Manga** - Add manga to a challenge\n"
                           f"🗑️ **Remove Manga** - Remove manga from challenges\n"
                           f"📋 **List Challenges** - View all active challenges\n"
                           f"🎭 **Manage Roles** - Configure automatic role rewards\n"
                           f"🔍 **Search Manga** - Get information about specific manga",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📝 Notes",
                value="• Challenges are specific to this server\n"
                      "• Challenges are created automatically when adding manga\n"
                      "• AniList manga information is fetched automatically\n"
                      "• Role rewards can be configured for challenge thresholds\n"
                      "• All operations are logged for tracking",
                inline=False
            )
            
            embed.set_footer(text="Server Moderator only • Buttons expire after 2 minutes of inactivity")
            
            # Create interactive view with guild ID
            view = ChallengeManagementView(interaction.user.id, guild_id)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            logger.info(f"Guild challenge management interface sent to {interaction.user.display_name} for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Unexpected error in challenge_manage command for {interaction.user.display_name} "
                        f"(ID: {interaction.user.id}) in guild {interaction.guild.id}: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An unexpected error occurred. Please try again later.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An unexpected error occurred. Please try again later.",
                        ephemeral=True
                    )
            except Exception as follow_e:
                logger.error(f"Failed to send error message: {follow_e}", exc_info=True)


async def setup(bot: commands.Bot):
    """Set up the ChallengeManage cog."""
    try:
        await bot.add_cog(ChallengeManage(bot))
        logger.info("Guild-specific Challenge Management cog successfully loaded")
    except Exception as e:
        logger.error(f"Failed to load Challenge Management cog: {e}", exc_info=True)
        raise