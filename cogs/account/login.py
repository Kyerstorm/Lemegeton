import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
import re
import aiohttp
import aiosqlite
from pathlib import Path
from typing import Optional

from database import (
    # Guild-aware functions (multi-guild support)
    add_user_guild_aware, get_user_guild_aware, register_user_guild_aware, 
    is_user_registered_in_guild, update_username, remove_user
)
from config import STEAM_API_KEY, DB_PATH

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "login.log"
MAX_USERNAME_LENGTH = 50
USERNAME_REGEX = r"^[\w-]+$"
ANILIST_ENDPOINT = "https://graphql.anilist.co"
STEAM_VANITY_REGEX = r"^[a-zA-Z0-9_-]+$"
VIEW_TIMEOUT = 60

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging with auto-clearing
logger = logging.getLogger("Login")
logger.setLevel(logging.DEBUG)

# Ensure we don't duplicate handlers on reload; try to use a file handler but
# fall back to a console StreamHandler if the file is locked (Windows).
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(LOG_FILE)
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

logger.info("Login cog logging system initialized")

class LoginView(discord.ui.View):
    """Interactive view for login/registration/unregistration actions."""
    
    def __init__(self, user_id: int, username: str, is_registered: bool, anilist_username: str = None, 
                 steam_data: dict = None):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.user_id = user_id
        self.username = username
        self.is_registered = is_registered
        self.anilist_username = anilist_username
        self.steam_data = steam_data  # {'steam_id': str, 'vanity_name': str} or None
        
        logger.debug(f"Created LoginView for {username} (ID: {user_id}), registered: {is_registered}, steam: {bool(steam_data)}")

    @discord.ui.button(label="📝 AniList", style=discord.ButtonStyle.primary, emoji="📝")
    async def anilist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show modal for AniList registration or updating."""
        logger.info(f"AniList button clicked by {interaction.user.display_name} (ID: {self.user_id})")
        
        modal = RegistrationModal(self.is_registered, registration_type="anilist")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🎮 Steam", style=discord.ButtonStyle.secondary, emoji="🎮")
    async def steam_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show modal for Steam registration or updating."""
        logger.info(f"Steam button clicked by {interaction.user.display_name} (ID: {self.user_id})")
        
        modal = RegistrationModal(bool(self.steam_data), registration_type="steam")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🗑️ Unregister", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def unregister_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show confirmation for unregistration."""
        has_data = self.is_registered or bool(self.steam_data)

        if not has_data:
            await interaction.response.send_message(
                "⚠️ You don't have any registered accounts, so there's nothing to unregister.",
                ephemeral=True,
            )
            logger.debug(
                f"Unregister attempted by user with no registrations: {interaction.user.display_name}"
            )
            return

        logger.info(
            f"Unregister button clicked by {interaction.user.display_name} (ID: {self.user_id})"
        )

        # Build unregister message based on what's registered
        services = []
        if self.is_registered:
            services.append("• Your AniList connection and all anime/manga data")
        if self.steam_data:
            services.append("• Your Steam connection and game data")

        # Show confirmation (include guild_id so unregistration can be scoped)
        guild_ctx_id = getattr(interaction.guild, "id", None) if interaction.guild else None
        view = UnregisterConfirmView(
            self.user_id, self.is_registered, bool(self.steam_data), guild_id=guild_ctx_id
        )

        message_text = (
            "❗ **Are you sure you want to unregister?**\n\n"
            "This action cannot be undone and will remove:\n"
            + "\n".join(services)
            + "\n• All your challenge progress\n"
            "• All your statistics and data\n\n"
            "⚠️ **This is permanent and cannot be recovered!**"
        )

        await interaction.response.send_message(message_text, view=view, ephemeral=True)

    @discord.ui.button(label="ℹ️ Status", style=discord.ButtonStyle.secondary, emoji="ℹ️")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show user's current registration status with unified gaming profile."""
        logger.debug(f"Status button clicked by {interaction.user.display_name} (ID: {self.user_id})")

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(title="📊 Your Account Status", color=discord.Color.blue())

        status_lines = []

        # AniList status
        if self.is_registered:
            status_lines.append(f"📚 **AniList**: ✅ Connected ({self.anilist_username or 'Unknown'})")
        else:
            status_lines.append("📚 **AniList**: ❌ Not connected")

        # Steam status with detailed stats
        if self.steam_data:
            vanity = self.steam_data.get('vanity_name', 'Unknown')
            steamid = self.steam_data.get('steam_id')

            status_lines.append(f"🎮 **Steam**: ✅ Connected ({vanity})")

            # Fetch detailed Steam stats
            if steamid and STEAM_API_KEY:
                try:
                    # Import gaming helpers
                    import sys
                    from pathlib import Path
                    repo_root = Path(__file__).resolve().parents[2]
                    if str(repo_root) not in sys.path:
                        sys.path.insert(0, str(repo_root))

                    from helpers.steam_helper import get_library_stats

                    # Get library statistics
                    library_stats = await get_library_stats(STEAM_API_KEY, steamid)

                    if library_stats and library_stats.get('total_games', 0) > 0:
                        total_games = library_stats.get('total_games', 0)
                        total_hours = library_stats.get('total_playtime_hours', 0)
                        never_played = library_stats.get('never_played', 0)

                        embed.add_field(
                            name="🎮 Steam Library Stats",
                            value=(
                                f"**Games Owned**: {total_games:,}\n"
                                f"**Total Playtime**: {total_hours:,.0f} hours\n"
                                f"**Unplayed Games**: {never_played} ({library_stats.get('never_played_percentage', 0):.1f}%)"
                            ),
                            inline=False
                        )
                        logger.debug(f"Fetched Steam stats for {vanity}: {total_games} games, {total_hours:.0f} hours")
                except Exception as e:
                    logger.warning(f"Could not fetch Steam stats: {e}")
                    # Don't show error to user, just skip the stats
        else:
            status_lines.append("🎮 **Steam**: ❌ Not connected")

        embed.description = "\n".join(status_lines)

        if not self.is_registered and not self.steam_data:
            embed.description += "\n\n💡 Connect your accounts to use the bot's features!"
            embed.color = discord.Color.orange()
        elif self.is_registered and self.steam_data:
            embed.description += "\n\n🎉 All services connected! You have access to all features."
            embed.color = discord.Color.green()
        else:
            embed.description += "\n\n⚡ Consider connecting both services for the full experience!"
            embed.color = discord.Color.gold()

        embed.set_footer(text="Use /steam-profile for detailed gaming stats • Use buttons above to manage connections")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_timeout(self):
        """Handle view timeout by disabling buttons."""
        try:
            self.clear_items()
            logger.debug(f"LoginView timed out for user ID: {self.user_id}")
        except Exception as e:
            logger.error(f"Error handling LoginView timeout: {e}", exc_info=True)


class RegistrationModal(discord.ui.Modal):
    """Modal for collecting registration information for AniList or Steam."""
    
    def __init__(self, is_update: bool = False, registration_type: str = "anilist"):
        self.is_update = is_update
        self.registration_type = registration_type
        
        if registration_type == "steam":
            title = "Update Steam Profile" if is_update else "Register Steam Profile"
            label = "Steam Vanity Name"
            placeholder = "Enter your Steam vanity URL (the part after /id/)"
        else:  # anilist
            title = "Update AniList Username" if is_update else "Register with AniList"
            label = "AniList Username"
            placeholder = "Enter your exact AniList username (case-sensitive)"
        
        super().__init__(title=title)
        
        self.username_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=True,
            max_length=MAX_USERNAME_LENGTH
        )
        self.add_item(self.username_input)
        
        logger.debug(f"Created RegistrationModal (type: {registration_type}, update: {is_update})")


    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission and process registration."""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server!", 
                ephemeral=True
            )
            return
            
        guild_id = interaction.guild.id
        username_input = self.username_input.value.strip()
        
        logger.info(f"Registration modal submitted by {interaction.user.display_name} "
                   f"(ID: {interaction.user.id}) in guild {guild_id} - Type: {self.registration_type}, Input: {username_input}")
        
        # Show progress indicator immediately
        progress_msg = "🔄 Verifying your username..." if self.registration_type == "anilist" else "🔄 Connecting to Steam..."
        await interaction.response.send_message(progress_msg, ephemeral=True)
        
        login_cog = interaction.client.get_cog("Login")
        if not login_cog:
            logger.error("Login cog not found when processing registration modal")
            await interaction.edit_original_response(
                content="❌ System error: Login cog not available. Please try again later."
            )
            return
        
        # Process registration
        if self.registration_type == "steam":
            result = await login_cog.handle_steam_register(
                interaction.user.id,
                str(interaction.user),
                username_input,
                guild_id
            )
        else:  # anilist
            result = await login_cog.handle_register(
                interaction.user.id,
                guild_id,
                str(interaction.user),
                username_input
            )
        
        # Update the progress message with the result
        if isinstance(result, discord.Embed):
            await interaction.edit_original_response(content=None, embed=result)
        else:
            await interaction.edit_original_response(content=result)


class UnregisterConfirmView(discord.ui.View):
    """View for confirming unregistration from services.

    Accepts guild_id so the actual unregistration call can be scoped to the guild
    where the user triggered the action.
    """

    def __init__(self, user_id: int, is_registered: bool, has_steam: bool, guild_id: int = None):
        super().__init__(timeout=300)
        # Keep a small dict for compatibility with existing usage in the view
        self.user_data = {
            'user_id': user_id,
            'is_registered': is_registered,
            'has_steam': has_steam
        }
        self.guild_id = guild_id
        
    @discord.ui.button(
        label="✅ Yes, Unregister AniList", 
        style=discord.ButtonStyle.danger, 
        custom_id="unregister_confirm_anilist"
    )
    async def unregister_confirm_anilist(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle confirmed AniList unregistration."""
        if interaction.user.id != self.user_data['user_id']:
            await interaction.response.send_message(
                "❌ You can only unregister yourself!", ephemeral=True
            )
            return
            
        await interaction.response.defer(ephemeral=True)
        
        login_cog = interaction.client.get_cog("Login")
        if not login_cog:
            await interaction.followup.send(
                "❌ System error: Login cog not available.", ephemeral=True
            )
            return

        success = await login_cog.unregister_user(interaction.user.id, "anilist", guild_id=self.guild_id)

        if success:
            logger.info(f"User {interaction.user.id} successfully unregistered from AniList")
            await interaction.followup.send(
                "✅ You have been successfully unregistered from AniList. "
                "All your AniList data has been removed from the system.",
                ephemeral=True
            )
        else:
            logger.error(f"Failed to unregister user {interaction.user.id} from AniList")
            await interaction.followup.send(
                "❌ An error occurred while unregistering from AniList. Please try again.",
                ephemeral=True
            )
        
        # Disable all buttons after action
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        try:
            await interaction.edit_original_response(view=self)
        except discord.NotFound:
            pass
            
    @discord.ui.button(
        label="✅ Yes, Unregister Steam", 
        style=discord.ButtonStyle.danger, 
        custom_id="unregister_confirm_steam"
    )
    async def unregister_confirm_steam(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle confirmed Steam unregistration."""
        if interaction.user.id != self.user_data['user_id']:
            await interaction.response.send_message(
                "❌ You can only unregister yourself!", ephemeral=True
            )
            return
            
        await interaction.response.defer(ephemeral=True)
        
        login_cog = interaction.client.get_cog("Login")
        if not login_cog:
            await interaction.followup.send(
                "❌ System error: Login cog not available.", ephemeral=True
            )
            return

        success = await login_cog.unregister_user(interaction.user.id, "steam", guild_id=self.guild_id)

        if success:
            logger.info(f"User {interaction.user.id} successfully unregistered from Steam")
            await interaction.followup.send(
                "✅ You have been successfully unregistered from Steam. "
                "All your Steam data has been removed from the system.",
                ephemeral=True
            )
        else:
            logger.error(f"Failed to unregister user {interaction.user.id} from Steam")
            await interaction.followup.send(
                "❌ An error occurred while unregistering from Steam. Please try again.",
                ephemeral=True
            )
        
        # Disable all buttons after action
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        try:
            await interaction.edit_original_response(view=self)
        except discord.NotFound:
            pass
    
    @discord.ui.button(
        label="❌ Cancel", 
        style=discord.ButtonStyle.secondary, 
        custom_id="unregister_cancel"
    )
    async def unregister_cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle cancellation of unregistration."""
        await interaction.response.send_message(
            "✅ Unregistration cancelled. Your accounts remain connected.", 
            ephemeral=True
        )
        
        # Disable all buttons after cancellation
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        try:
            await interaction.edit_original_response(view=self)
        except discord.NotFound:
            pass
    
    async def on_timeout(self):
        """Handle view timeout."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class Login(commands.Cog):
    """Discord cog for user login/registration management."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Login cog initialized")

    def _is_valid_username(self, username: str) -> bool:
        """Validate username format and length."""
        if not username or not isinstance(username, str):
            return False
        return bool(re.match(USERNAME_REGEX, username)) and 0 < len(username) <= MAX_USERNAME_LENGTH

    async def _fetch_anilist_id(self, anilist_username: str) -> Optional[dict]:
        """Fetch AniList user ID and avatar from username via GraphQL API.
        
        Returns:
            dict with 'id', 'name', and 'avatar' keys, or None if user not found
        """
        query = """
        query ($name: String) {
          User(name: $name) { 
            id 
            name
            avatar {
              large
              medium
            }
          }
        }
        """
        
        logger.debug(f"Fetching AniList ID for username: {anilist_username}")
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(
                    ANILIST_ENDPOINT,
                    json={"query": query, "variables": {"name": anilist_username}}
                ) as resp:
                    if resp.status == 404:
                        logger.warning(f"AniList user not found: {anilist_username}")
                        return {"error": "not_found", "message": "User does not exist on AniList"}
                    elif resp.status == 429:
                        logger.warning(f"AniList API rate limit hit for: {anilist_username}")
                        return {"error": "rate_limit", "message": "Too many requests. Please try again in a moment."}
                    elif resp.status != 200:
                        logger.warning(f"AniList API returned status {resp.status} for username: {anilist_username}")
                        return {"error": "api_error", "message": f"AniList API error (status {resp.status})"}
                    
                    data = await resp.json()
                    logger.debug(f"AniList API response received for username: {anilist_username}")
                    
                    user_data = data.get("data", {}).get("User")
                    if user_data and "id" in user_data:
                        result = {
                            "id": user_data["id"],
                            "name": user_data.get("name", anilist_username),
                            "avatar": user_data.get("avatar", {}).get("large") or user_data.get("avatar", {}).get("medium")
                        }
                        logger.info(f"Successfully found AniList user: {result['name']} (ID: {result['id']})")
                        return result
                    
                    logger.warning(f"AniList user not found: {anilist_username}")
                    return {"error": "not_found", "message": "User does not exist on AniList"}
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error while fetching AniList ID for {anilist_username}: {e}")
            return {"error": "network", "message": "Network connection error. Please check your internet connection."}
        except Exception as e:
            logger.error(f"Unexpected error while fetching AniList ID for {anilist_username}: {e}", exc_info=True)
            return {"error": "unexpected", "message": "An unexpected error occurred. Please try again later."}

    async def handle_register(self, user_id: int, guild_id: int, discord_user: str, anilist_username: str) -> str:
        """Handle user registration with comprehensive validation and logging."""
        logger.info(f"Registration attempt by {discord_user} (ID: {user_id}) in guild {guild_id} with AniList username: {anilist_username}")
        
        # Input validation
        anilist_username = anilist_username.strip()
        if not anilist_username:
            logger.warning(f"Empty username provided by {discord_user} (ID: {user_id}) in guild {guild_id}")
            return "❌ AniList username cannot be empty."
            
        if len(anilist_username) > MAX_USERNAME_LENGTH:
            logger.warning(f"Username too long ({len(anilist_username)} chars) by {discord_user} (ID: {user_id}) in guild {guild_id}")
            return f"❌ Username too long. Maximum {MAX_USERNAME_LENGTH} characters allowed."
            
        if not self._is_valid_username(anilist_username):
            logger.warning(f"Invalid username format '{anilist_username}' by {discord_user} (ID: {user_id}) in guild {guild_id}")
            return "❌ Invalid username. Only letters, numbers, underscores, and hyphens are allowed."

        # Fetch and validate AniList ID with enhanced error messages
        anilist_data = await self._fetch_anilist_id(anilist_username)
        if not anilist_data or "error" in anilist_data:
            error_type = anilist_data.get("error", "unknown") if anilist_data else "unknown"
            error_msg = anilist_data.get("message", "Unknown error") if anilist_data else "Unknown error"
            
            logger.warning(f"AniList user '{anilist_username}' fetch failed for {discord_user} (ID: {user_id}) in guild {guild_id}: {error_type}")
            
            # Provide specific error messages with helpful suggestions
            if error_type == "not_found":
                return (f"❌ Could not find AniList user **{anilist_username}**. "
                       f"\n\n💡 **Suggestions:**\n"
                       f"• Double-check the spelling (usernames are case-sensitive)\n"
                       f"• Visit https://anilist.co/@{anilist_username} to verify\n"
                       f"• Make sure the profile exists and is public")
            elif error_type == "rate_limit":
                return f"❌ {error_msg}\n\n⏰ Please wait a moment and try again."
            elif error_type == "network":
                return f"❌ {error_msg}\n\n🔌 Please check your connection and try again."
            else:
                return f"❌ Could not connect to AniList: {error_msg}\n\n🔄 Please try again later."
        
        anilist_id = anilist_data["id"]
        actual_name = anilist_data["name"]
        avatar_url = anilist_data.get("avatar")

        # Database operations
        try:
            existing_user = await get_user_guild_aware(user_id, guild_id)
            
            if existing_user:
                # Update existing user
                await self._update_existing_user_guild_aware(user_id, guild_id, discord_user, actual_name, anilist_id)
                logger.info(f"Updated registration for {discord_user} (ID: {user_id}) in guild {guild_id} -> AniList: {actual_name} (ID: {anilist_id})")
                
                # Create rich embed with avatar
                embed = discord.Embed(
                    title="✅ AniList Updated",
                    description=f"Your AniList username has been updated to **{actual_name}** in this server!",
                    color=discord.Color.green()
                )
                if avatar_url:
                    embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="Profile", value=f"https://anilist.co/user/{actual_name}", inline=False)
                return embed
            else:
                # Register new user
                await self._register_new_user_guild_aware(user_id, guild_id, discord_user, actual_name, anilist_id)
                logger.info(f"Successfully registered new user {discord_user} (ID: {user_id}) in guild {guild_id} -> AniList: {actual_name} (ID: {anilist_id})")
                
                # Create rich embed with avatar
                embed = discord.Embed(
                    title="🎉 Registration Successful",
                    description=f"Successfully registered with AniList username **{actual_name}** in this server!",
                    color=discord.Color.blue()
                )
                if avatar_url:
                    embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="Profile", value=f"https://anilist.co/user/{actual_name}", inline=False)
                embed.set_footer(text="You can now use all AniList features!")
                return embed
                
        except Exception as e:
            logger.error(f"Database error during registration for {discord_user} (ID: {user_id}) in guild {guild_id}: {e}", exc_info=True)
            return "❌ An error occurred while registering you. Please try again later."

    # Deprecated method removed - use _update_existing_user_guild_aware instead

    async def _update_existing_user_guild_aware(self, user_id: int, guild_id: int, discord_user: str, anilist_username: str, anilist_id: int):
        """Update existing user's AniList information for a specific guild."""
        try:
            # Use the guild-aware registration function which handles updates via INSERT OR REPLACE
            await register_user_guild_aware(user_id, guild_id, discord_user, anilist_username, anilist_id)
            logger.info(f"Updated AniList info for existing user {discord_user} (ID: {user_id}) in guild {guild_id}")
        except Exception as e:
            logger.error(f"Failed to update existing user {discord_user} (ID: {user_id}) in guild {guild_id}: {e}")
            raise

    # Deprecated method removed - use _register_new_user_guild_aware instead

    async def _register_new_user_guild_aware(self, user_id: int, guild_id: int, discord_user: str, anilist_username: str, anilist_id: int):
        """Register a completely new user in a specific guild."""
        await register_user_guild_aware(user_id, guild_id, discord_user, anilist_username, anilist_id)
        logger.info(f"Added new user to database: {discord_user} (ID: {user_id}) in guild {guild_id}")

    async def _resolve_steam_vanity(self, vanity_name: str) -> Optional[dict]:
        """Resolve Steam vanity name to Steam ID and fetch avatar using Steam API.
        
        Returns:
            dict with 'steam_id', 'vanity_name', and 'avatar' keys, or dict with 'error' key
        """
        if not STEAM_API_KEY:
            logger.error("Steam API key not configured")
            return {"error": "no_api_key", "message": "Steam API is not configured. Please contact the bot administrator."}
            
        # Remove any URL parts if user provided full URL
        vanity_name = vanity_name.strip().split('/')[-1]
        
        # Check if it's already a Steam ID
        if vanity_name.isdigit() and len(vanity_name) >= 17:
            steam_id = vanity_name
        else:
            # Resolve vanity URL to Steam ID
            url = f"http://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key={STEAM_API_KEY}&vanityurl={vanity_name}"
            
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.warning(f"Steam API returned status {resp.status} for vanity: {vanity_name}")
                            return {"error": "api_error", "message": f"Steam API error (status {resp.status})"}
                        
                        data = await resp.json()
                        response_data = data.get("response", {})
                        
                        if response_data.get("success") == 1:
                            steam_id = response_data.get("steamid")
                            logger.info(f"Successfully resolved Steam vanity '{vanity_name}' to ID: {steam_id}")
                        else:
                            logger.warning(f"Steam vanity name not found: {vanity_name}")
                            return {"error": "not_found", "message": f"Steam user **{vanity_name}** not found. Please check the vanity name and try again.\n\n💡 **Tip:** Your vanity URL is the part after `/id/` in your Steam profile URL."}
            except Exception as e:
                logger.error(f"Error resolving Steam vanity name '{vanity_name}': {e}")
                return {"error": "network", "message": "Network error while connecting to Steam. Please try again."}
        
        # Fetch player summary for avatar
        try:
            summary_url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(summary_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        players = data.get("response", {}).get("players", [])
                        if players:
                            player = players[0]
                            return {
                                "steam_id": steam_id,
                                "vanity_name": vanity_name,
                                "avatar": player.get("avatarfull") or player.get("avatarmedium"),
                                "profile_url": player.get("profileurl")
                            }
        except Exception as e:
            logger.warning(f"Could not fetch Steam avatar for {steam_id}: {e}")
        
        # Return without avatar if fetch failed
        return {
            "steam_id": steam_id,
            "vanity_name": vanity_name,
            "avatar": None,
            "profile_url": f"https://steamcommunity.com/profiles/{steam_id}"
        }

    async def handle_steam_register(self, user_id: int, discord_user: str, vanity_name: str, guild_id: Optional[int] = None) -> str:
        """Handle Steam user registration with guild-aware support.
        
        Args:
            user_id: Discord user ID
            discord_user: Discord username
            vanity_name: Steam vanity URL name
            guild_id: Guild ID for guild-aware storage (optional)
        """
        logger.info(f"Steam registration attempt by {discord_user} (ID: {user_id}) with vanity: {vanity_name}")
        
        # Input validation
        vanity_name = vanity_name.strip()
        if not vanity_name:
            return "❌ Steam vanity name cannot be empty."
            
        if not re.match(STEAM_VANITY_REGEX, vanity_name):
            return "❌ Invalid Steam vanity name. Only letters, numbers, underscores, and hyphens are allowed.\n\n💡 **Tip:** Your vanity URL should only contain letters, numbers, - and _"

        # Resolve vanity name to Steam ID with enhanced error handling
        steam_data = await self._resolve_steam_vanity(vanity_name)
        if not steam_data or "error" in steam_data:
            error_msg = steam_data.get("message", "Unknown error") if steam_data else "Unknown error"
            logger.warning(f"Steam resolution failed for {discord_user} (ID: {user_id}): {error_msg}")
            return f"❌ {error_msg}"
        
        steam_id = steam_data["steam_id"]
        avatar_url = steam_data.get("avatar")
        profile_url = steam_data.get("profile_url")

        # Database operations with guild-aware support
        try:
            import aiosqlite
            
            async with aiosqlite.connect(DB_PATH) as db:
                # Check if user already exists (guild-aware if guild_id provided)
                existing_user = None
                if guild_id is not None:
                    cursor = await db.execute(
                        "SELECT * FROM steam_users WHERE discord_id = ? AND guild_id = ?",
                        (user_id, guild_id)
                    )
                    existing_user = await cursor.fetchone()
                    await cursor.close()
                
                if not existing_user:
                    # Fallback to global check
                    cursor = await db.execute(
                        "SELECT * FROM steam_users WHERE discord_id = ?",
                        (user_id,)
                    )
                    existing_user = await cursor.fetchone()
                    await cursor.close()

                if existing_user:
                    # Update existing user
                    if guild_id is not None:
                        await db.execute(
                            "UPDATE steam_users SET steam_id = ?, vanity_name = ? WHERE discord_id = ? AND guild_id = ?",
                            (steam_id, vanity_name, user_id, guild_id)
                        )
                    else:
                        await db.execute(
                            "UPDATE steam_users SET steam_id = ?, vanity_name = ? WHERE discord_id = ?",
                            (steam_id, vanity_name, user_id)
                        )
                    await db.commit()
                    logger.info(f"Updated Steam registration for {discord_user} (ID: {user_id}) -> Steam: {vanity_name}")
                    
                    # Create rich embed with avatar
                    embed = discord.Embed(
                        title="✅ Steam Updated",
                        description=f"Your Steam profile has been updated to **{vanity_name}**!",
                        color=discord.Color.green()
                    )
                    if avatar_url:
                        embed.set_thumbnail(url=avatar_url)
                    if profile_url:
                        embed.add_field(name="Profile", value=profile_url, inline=False)
                    return embed
                else:
                    # Register new user
                    if guild_id is not None:
                        await db.execute(
                            "INSERT INTO steam_users (discord_id, steam_id, vanity_name, guild_id) VALUES (?, ?, ?, ?)",
                            (user_id, steam_id, vanity_name, guild_id)
                        )
                    else:
                        await db.execute(
                            "INSERT INTO steam_users (discord_id, steam_id, vanity_name) VALUES (?, ?, ?)",
                            (user_id, steam_id, vanity_name)
                        )
                    await db.commit()
                    logger.info(f"Successfully registered Steam user {discord_user} (ID: {user_id}) -> Steam: {vanity_name}")
                    
                    # Create rich embed with avatar
                    embed = discord.Embed(
                        title="🎉 Steam Registration Successful",
                        description=f"Successfully registered with Steam profile **{vanity_name}**!",
                        color=discord.Color.blue()
                    )
                    if avatar_url:
                        embed.set_thumbnail(url=avatar_url)
                    if profile_url:
                        embed.add_field(name="Profile", value=profile_url, inline=False)
                    embed.set_footer(text="You can now use all Steam features!")
                    return embed
                
        except Exception as e:
            logger.error(f"Database error during Steam registration for {discord_user} (ID: {user_id}): {e}", exc_info=True)
            return "❌ An error occurred while registering your Steam profile. Please try again later."

    async def get_user_data(self, user_id: int, guild_id: int) -> dict:
        """Get combined user data from both AniList and Steam systems."""
        user_data = {
            'user_id': user_id,
            'anilist_connected': False,
            'steam_connected': False,
            'anilist_username': None,
            'steam_vanity': None
        }
        
        # Check AniList connection
        try:
            anilist_user = await get_user_guild_aware(user_id, guild_id)
            if anilist_user:
                user_data['anilist_connected'] = True
                user_data['anilist_username'] = anilist_user[4]  # anilist_username is at index 4
        except Exception as e:
            logger.error(f"Error checking AniList user data for {user_id}: {e}")
        
        # Check Steam connection
        try:
            import aiosqlite
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute("SELECT vanity_name FROM steam_users WHERE discord_id = ?", (user_id,))
                steam_user = await cursor.fetchone()
                
                if steam_user:
                    user_data['steam_connected'] = True
                    user_data['steam_vanity'] = steam_user[0]
        except Exception as e:
            logger.error(f"Error checking Steam user data for {user_id}: {e}")
        
        return user_data

    async def unregister_user(self, user_id: int, service_type: str, guild_id: Optional[int] = None) -> bool:
        """
        Unregister user from specified service.
        
        Args:
            user_id: Discord user ID
            service_type: Either "anilist" or "steam"
            guild_id: Guild ID for guild-scoped deletion (None for global deletion)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if service_type == "anilist":
                # Perform guild-aware deletion
                await remove_user(user_id, guild_id)
                if guild_id:
                    logger.info(f"Successfully unregistered user {user_id} from AniList in guild {guild_id}")
                else:
                    logger.info(f"Successfully unregistered user {user_id} from AniList (global)")
                return True
                
            elif service_type == "steam":
                import aiosqlite
                async with aiosqlite.connect(DB_PATH) as db:
                    if guild_id is not None:
                        # Guild-scoped deletion
                        await db.execute(
                            "DELETE FROM steam_users WHERE discord_id = ? AND guild_id = ?",
                            (user_id, guild_id)
                        )
                        logger.info(f"Successfully unregistered user {user_id} from Steam in guild {guild_id}")
                    else:
                        # Global deletion
                        await db.execute(
                            "DELETE FROM steam_users WHERE discord_id = ?",
                            (user_id,)
                        )
                        logger.info(f"Successfully unregistered user {user_id} from Steam (global)")
                    await db.commit()
                return True
                
            else:
                logger.error(f"Unknown service type: {service_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error unregistering user {user_id} from {service_type}: {e}")
            return False

    @app_commands.command(
        name="login",
        description="🔐 Manage your account - register with AniList and/or Steam"
    )
    async def login(self, interaction: discord.Interaction):
        """Smart login command that manages both AniList and Steam connections."""
        try:
            # Ensure command is used in a guild
            if not interaction.guild:
                await interaction.response.send_message(
                    "❌ This command can only be used in a server!", 
                    ephemeral=True
                )
                return
            
            guild_id = interaction.guild.id
            logger.info(f"Login command invoked by {interaction.user.display_name} "
                       f"({interaction.user.id}) in {interaction.guild.name} (Guild ID: {guild_id})")
            
            # Get combined user data
            user_data = await self.get_user_data(interaction.user.id, guild_id)
            
            logger.debug(f"User {interaction.user.display_name} data: {user_data}")
            
            # Create embed based on connection status
            if user_data['anilist_connected'] or user_data['steam_connected']:
                # User has at least one connection
                embed = discord.Embed(
                    title="🔐 Account Management",
                    description=f"Welcome back, **{interaction.user.display_name}**!\n\n"
                               f"Here's your connection status in **{interaction.guild.name}**:",
                    color=discord.Color.green()
                )
                
                # Add connection status
                status_lines = []
                if user_data['anilist_connected']:
                    status_lines.append(f"� **AniList**: {user_data['anilist_username']}")
                else:
                    status_lines.append(f"📝 **AniList**: Not connected")
                    
                if user_data['steam_connected']:
                    status_lines.append(f"🎮 **Steam**: {user_data['steam_vanity']}")
                else:
                    status_lines.append(f"🎮 **Steam**: Not connected")
                
                embed.add_field(
                    name="Connection Status",
                    value="\n".join(status_lines),
                    inline=False
                )
                
                embed.add_field(
                    name="Available Actions",
                    value="📝 **AniList** - Register or update your AniList username\n"
                          "🎮 **Steam** - Register or update your Steam profile\n"
                          "🗑️ **Unregister** - Remove specific service connections\n"
                          "ℹ️ **Status** - View detailed account information",
                    inline=False
                )
            else:
                # User has no connections
                embed = discord.Embed(
                    title="🔐 Welcome to the Bot!",
                    description=f"Hello **{interaction.user.display_name}**!\n\n"
                               f"❌ **Status**: Not Connected in **{interaction.guild.name}**\n\n"
                               f"To use this bot's features, you can connect your accounts:\n"
                               f"• **AniList** - For anime/manga tracking features\n"
                               f"• **Steam** - For gaming features\n\n"
                               f"Use the buttons below to get started:",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="Available Actions",
                    value="📝 **AniList** - Connect your AniList account\n"
                          "🎮 **Steam** - Connect your Steam profile\n"
                          "ℹ️ **Status** - View account information",
                    inline=False
                )
            
            embed.set_footer(text="Your data is secure and can be removed anytime")
            
            # Create interactive view with user data
            # Format steam_data properly for LoginView
            steam_data_formatted = None
            if user_data['steam_connected']:
                steam_data_formatted = {
                    'vanity_name': user_data['steam_vanity']
                }
            
            view = LoginView(
                user_id=interaction.user.id,
                username=str(interaction.user),
                is_registered=user_data['anilist_connected'],  # Keep for backward compatibility
                anilist_username=user_data['anilist_username'],
                steam_data=steam_data_formatted
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            logger.info(f"Login interface sent to {interaction.user.display_name} "
                       f"(AniList: {user_data['anilist_connected']}, Steam: {user_data['steam_connected']})")
            
        except Exception as e:
            logger.error(f"Unexpected error in login command for {interaction.user.display_name} "
                        f"(ID: {interaction.user.id}): {e}", exc_info=True)
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

    async def check_connection_health(self, user_id: int, guild_id: int) -> dict:
        """Check if connected accounts are still valid and accessible.
        
        Returns:
            dict with health status for each service
        """
        health_status = {
            "anilist": {"connected": False, "healthy": False, "message": ""},
            "steam": {"connected": False, "healthy": False, "message": ""}
        }
        
        # Check AniList connection
        try:
            anilist_user = await get_user_guild_aware(user_id, guild_id)
            if anilist_user:
                health_status["anilist"]["connected"] = True
                anilist_username = anilist_user[4]  # anilist_username at index 4
                
                # Verify account still exists
                anilist_data = await self._fetch_anilist_id(anilist_username)
                if anilist_data and "error" not in anilist_data:
                    health_status["anilist"]["healthy"] = True
                    health_status["anilist"]["message"] = "Connection verified"
                else:
                    health_status["anilist"]["message"] = anilist_data.get("message", "Could not verify account") if anilist_data else "Could not verify account"
        except Exception as e:
            logger.error(f"Error checking AniList health for user {user_id}: {e}")
            health_status["anilist"]["message"] = "Health check failed"
        
        # Check Steam connection
        try:
            import aiosqlite
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT vanity_name FROM steam_users WHERE discord_id = ?",
                    (user_id,)
                )
                steam_user = await cursor.fetchone()
                await cursor.close()
                
                if steam_user:
                    health_status["steam"]["connected"] = True
                    vanity_name = steam_user[0]
                    
                    # Verify Steam account still exists
                    steam_data = await self._resolve_steam_vanity(vanity_name)
                    if steam_data and "error" not in steam_data:
                        health_status["steam"]["healthy"] = True
                        health_status["steam"]["message"] = "Connection verified"
                    else:
                        health_status["steam"]["message"] = steam_data.get("message", "Could not verify account") if steam_data else "Could not verify account"
        except Exception as e:
            logger.error(f"Error checking Steam health for user {user_id}: {e}")
            health_status["steam"]["message"] = "Health check failed"
        
        return health_status

    async def cog_load(self):
        """Called when the cog is loaded."""
        logger.info("Login cog loaded successfully with connection health monitoring")

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        logger.info("Login cog unloaded")


async def setup(bot: commands.Bot):
    """Set up the Login cog."""
    try:
        await bot.add_cog(Login(bot))
        logger.info("Login cog successfully loaded")
    except Exception as e:
        logger.error(f"Failed to load Login cog: {e}", exc_info=True)
        raise