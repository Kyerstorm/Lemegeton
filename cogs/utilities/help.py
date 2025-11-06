import discord
from discord import app_commands
from discord.ext import commands
import logging
from pathlib import Path
from config import BOT_ID
from cogs_test.general_commands.dashboard import command_meta
from helpers.embed_helper import build_error_embed, build_warning_embed

# ------------------------------------------------------
# Logging Setup - Safe handling
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "help.log"

# Setup logger
logger = logging.getLogger("help")
logger.setLevel(logging.INFO)

# Only add a file handler if not already present; fall back to a console stream handler on failure
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(LOG_FILE)
           for h in logger.handlers):
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(stream_handler)

logger.info("Help cog logging initialized")

class HelpCog(commands.Cog):
    """A comprehensive help system for the Lemegeton bot."""

    def __init__(self, bot):
        self.bot = bot
        logger.info("Help cog initialized")
        
        # Command categories and details
        self.command_categories = {
            "🔐 Account Management": {
                "login": {
                    "desc": "🔐 Manage your account - register with AniList and/or Steam",
                    "usage": "/login",
                    "note": "Start here to connect your AniList account! Supports both AniList and Steam account linking.",
                    "examples": ["/login"]
                },
                "profile": {
                    "desc": "View your AniList profile with comprehensive stats, achievements, and bio gallery",
                    "usage": "/profile [user]",
                    "note": "Features: 🖼️ Gallery (view all bio images), 🏅 Achievements, ⭐ Favorites, 📝 Bio with auto-cleanup, 👥 Social stats, 📅 Account age. Data cached for 12 hours for faster loading.",
                    "examples": ["/profile", "/profile @username"]
                },
                "admin-login": {
                    "desc": "🔐 Link a Discord user with an AniList username (Admin only)",
                    "usage": "/admin-login <discord_user> <anilist_user>",
                    "note": "Manually link users' Discord accounts to AniList profiles. Requires admin permissions.",
                    "examples": ["/admin-login @user theiranilistname"]
                }
            },
            "📺 Anime & Manga": {
                "browse": {
                    "desc": "Search Anime, Manga, Light Novels and General Novels",
                    "usage": "/browse",
                    "note": "Interactive browsing with advanced filtering and sorting options. Filter by genre, year, format, and more.",
                    "examples": ["/browse"]
                },
                "trending": {
                    "desc": "🔥 View the currently trending anime, manga, or light novels on AniList",
                    "usage": "/trending [media_type]",
                    "note": "See what's popular right now on AniList. Supports Anime, Manga, Light Novels, or All.",
                    "examples": ["/trending", "/trending anime", "/trending manga"]
                },
                "recommendations": {
                    "desc": "Get personalized manga recommendations based on your highly-rated library",
                    "usage": "/recommendations [username]",
                    "note": "AI-powered recommendations with interactive browsing by category. Based on titles rated ≥8.0/10.",
                    "examples": ["/recommendations", "/recommendations @friend"]
                },
                "random": {
                    "desc": "🎲 Get a completely random Anime, Manga, Light Novel, or All suggestion from AniList",
                    "usage": "/random <media_type>",
                    "note": "For when you can't decide what to watch/read - supports Anime, Manga, Light Novel, or All",
                    "examples": ["/random anime", "/random manga", "/random light_novel", "/random all"]
                },
                "trailer": {
                    "desc": "🎬 Get the trailer for an anime/manga from AniList",
                    "usage": "/trailer <type> <title>",
                    "note": "Fetches official trailers with autocomplete support. Supports both anime and manga.",
                    "examples": ["/trailer anime Demon Slayer", "/trailer manga Chainsaw Man"]
                },
                "3x3": {
                    "desc": "🎨 Create a 3x3 grid of your favorite anime, manga, or characters",
                    "usage": "/3x3 <media_type>",
                    "note": "Generate shareable 3x3 grids with custom selections. Supports anime, manga, characters, and games. Fetches covers/images from AniList automatically.",
                    "examples": ["/3x3 anime", "/3x3 manga", "/3x3 character", "/3x3 games"]
                },
                "news": {
                    "desc": "Manage Twitter/X news monitoring for anime/manga updates",
                    "usage": "/news",
                    "note": "Monitor Twitter accounts for anime/manga news. Bot Moderator only.",
                    "examples": ["/news"]
                },
                "test-twitter-scrape": {
                    "desc": "Test Twitter scraping for debugging",
                    "usage": "/test-twitter-scrape <username>",
                    "note": "Debug command to test Twitter/X scraping functionality. Bot Moderator only.",
                    "examples": ["/test-twitter-scrape username"]
                },
                "set_animanga_completion_channel": {
                    "desc": "Set channel to receive anime/manga completion updates (Mod only)",
                    "usage": "/set_animanga_completion_channel <channel>",
                    "note": "Monitor when users complete series. Requires moderator permissions.",
                    "examples": ["/set_animanga_completion_channel #completions"]
                },
                "show_manga_channel": {
                    "desc": "Show currently configured manga update channel (Mod only)",
                    "usage": "/show_manga_channel",
                    "note": "View the channel currently set for anime/manga completion notifications.",
                    "examples": ["/show_manga_channel"]
                }
            },
            "🎮 Gaming": {
                "steam-profile": {
                    "desc": "Show detailed Steam profile with library stats and analytics",
                    "usage": "/steam-profile [user]",
                    "note": "View Steam user profiles and stats. Supports vanity URLs or SteamID64. Leave blank for your own profile.",
                    "examples": ["/steam-profile gaben", "/steam-profile 76561197960287930", "/steam-profile"]
                },
                "steam-recommendation": {
                    "desc": "Get personalized game recommendations based on your Steam library",
                    "usage": "/steam-recommendation [genre] [max_price]",
                    "note": "Discover new games similar to ones you enjoy. Filter by genre and price.",
                    "examples": ["/steam-recommendation", "/steam-recommendation genre:action max_price:30"]
                },
                "steam-game": {
                    "desc": "Search for a Steam game and view detailed information",
                    "usage": "/steam-game <query>",
                    "note": "Search Steam store with fuzzy matching. View game details, prices, and reviews.",
                    "examples": ["/steam-game Elden Ring", "/steam-game god of war"]
                },
                "free-games": {
                    "desc": "Manage free games notifications and check current deals",
                    "usage": "/free-games",
                    "note": "Check current free games and setup automatic notifications (Epic, GOG, Steam). Checks every 6 hours.",
                    "examples": ["/free-games"]
                },
                "check-free-games": {
                    "desc": "🎮 Test command: Check current free games from all platforms",
                    "usage": "/check-free-games",
                    "note": "Immediately check for free games from Epic, GOG, and Steam. Useful for testing.",
                    "examples": ["/check-free-games"]
                }
            },
            "🎨 Customization": {
                "theme": {
                    "desc": "Complete theme customization system - Browse, preview, and apply themes",
                    "usage": "/theme",
                    "note": "Customize your bot experience with themes",
                    "examples": ["/theme"]
                },
                "nitro-role-set": {
                    "desc": "Create and apply a custom role with your chosen color (Server Boosters only)",
                    "usage": "/nitro-role-set <role_name> <hex_color>",
                    "note": "Server boosters can create custom roles with any name and hex color. Multiple roles allowed.",
                    "examples": ["/nitro-role-set \"My Cool Role\" #FF6B6B", "/nitro-role-set \"Gamer\" #00FF00"]
                },
                "admin-guild-theme": {
                    "desc": "Manage guild-wide theme settings (Bot Moderator only)",
                    "usage": "/admin-guild-theme",
                    "note": "Set server-wide default themes",
                    "examples": ["/admin-guild-theme"]
                }
            },
            "⚙️ Server Management": {
                "serverinfo": {
                    "desc": "View detailed server information",
                    "usage": "/serverinfo",
                    "note": "Display comprehensive server stats, member counts, channels, roles, and more. Works in any guild.",
                    "examples": ["/serverinfo"]
                },
                "server-config": {
                    "desc": "⚙️ Configure server settings - roles, channels, and notifications",
                    "usage": "/server-config",
                    "note": "Unified server configuration interface. Manage roles, channels, and notification settings. Requires 'Manage Server' permission.",
                    "examples": ["/server-config"]
                },
                "invite-stats": {
                    "desc": "View recruitment statistics for the server or a specific user",
                    "usage": "/invite-stats [user]",
                    "note": "Track invite statistics and recruitment data. Requires 'Manage Server' permission.",
                    "examples": ["/invite-stats", "/invite-stats @user"]
                },
                "invite-leaderboard": {
                    "desc": "View the top recruiters in the server",
                    "usage": "/invite-leaderboard",
                    "note": "See who's leading in server recruitment. Requires 'Manage Server' permission.",
                    "examples": ["/invite-leaderboard"]
                },
                "invite-theme": {
                    "desc": "Customize invite leaderboard theme",
                    "usage": "/invite-theme",
                    "note": "Set the visual theme for invite leaderboards. Requires 'Manage Server' permission.",
                    "examples": ["/invite-theme"]
                },
                "set-welcome-dm": {
                    "desc": "Set the welcome DM message by uploading a text file (Admin only)",
                    "usage": "/set-welcome-dm <text_file>",
                    "note": "Configure automated welcome messages sent to new server boosters. Requires admin permissions.",
                    "examples": ["/set-welcome-dm"]
                },
                "welcome-dm-status": {
                    "desc": "Check the current welcome DM configuration (Admin only)",
                    "usage": "/welcome-dm-status",
                    "note": "View current welcome DM settings and status. Requires admin permissions.",
                    "examples": ["/welcome-dm-status"]
                }
            },
            "👑 Admin": {
                "admin-moderator-manage": {
                    "desc": "👑 Manage bot moderators (bot-wide permissions)",
                    "usage": "/admin-moderator-manage",
                    "note": "Add/remove bot moderators with elevated permissions. Bot Moderator only.",
                    "examples": ["/admin-moderator-manage"]
                },
                "changelog": {
                    "desc": "Create and publish a changelog from text or file (Bot Moderator only)",
                    "usage": "/changelog [text] [file]",
                    "note": "Publish formatted changelogs with customizable appearance and notifications. Use text OR upload a file.",
                    "examples": ["/changelog", "/changelog text:New features added"]
                },
                "set_bot_updates_channel": {
                    "desc": "Set channel to receive bot updates and announcements (Admin only)",
                    "usage": "/set_bot_updates_channel <channel>",
                    "note": "Configure where bot update notifications appear. Requires admin permissions.",
                    "examples": ["/set_bot_updates_channel #bot-updates"]
                }
            },
            "👥 Social": {
                "anilist-leaderboard": {
                    "desc": "🏆 Show leaderboard ranked by manga, anime, or combined activity",
                    "usage": "/anilist-leaderboard <medium>",
                    "note": "View rankings by chapters read, episodes watched, or completed series. Server-specific leaderboards.",
                    "examples": ["/anilist-leaderboard chapters", "/anilist-leaderboard anime_completed"]
                },
                "affinity": {
                    "desc": "Compare your affinity with all users or a specific user in this server",
                    "usage": "/affinity [user]",
                    "note": "See how similar your anime/manga tastes are with others. Calculates compatibility scores.",
                    "examples": ["/affinity", "/affinity @friend"]
                },
                "feedback": {
                    "desc": "Submit ideas or report bugs",
                    "usage": "/feedback",
                    "note": "Help improve the bot with your suggestions. Submit feature ideas or bug reports.",
                    "examples": ["/feedback"]
                }
            },
            "🛠️ Utilities": {
                "help": {
                    "desc": "Get comprehensive help for bot commands and features",
                    "usage": "/help [category]",
                    "note": "Display this help information. Use the dropdown to explore categories.",
                    "examples": ["/help", "/help anime", "/help gaming"]
                },
                "notifications": {
                    "desc": "Manage your bot update notification preferences",
                    "usage": "/notifications",
                    "note": "Control what notifications you receive from the bot.",
                    "examples": ["/notifications"]
                },
                "say": {
                    "desc": "Make the bot say something (Moderators only). Supports markdown, embeds, and channel targeting.",
                    "usage": "/say <message> [options]",
                    "note": "Send messages as the bot. Supports embeds, markdown, and replying to messages. All usage is logged for moderation accountability.",
                    "examples": ["/say Hello world!", "/say message:Test embed:true"]
                },
                "userinfo": {
                    "desc": "View detailed user information",
                    "usage": "/userinfo [user]",
                    "note": "Display comprehensive user stats, badges, security info, and account details. Defaults to your own info.",
                    "examples": ["/userinfo", "/userinfo @user"]
                },
                "timestamp": {
                    "desc": "Convert a date and time to Discord's universal timestamp format",
                    "usage": "/timestamp <time> [date]",
                    "note": "Create Discord timestamps that display in each user's local timezone. Time in HH:MM format (24-hour).",
                    "examples": ["/timestamp 18:00", "/timestamp 12:30 2025-12-25"]
                },
                "invite": {
                    "desc": "Get an invite link to add this bot to your server",
                    "usage": "/invite",
                    "note": "Share the bot with other servers. Generates invite link with proper permissions.",
                    "examples": ["/invite"]
                },
                "planned-features": {
                    "desc": "View planned bot features",
                    "usage": "/planned-features",
                    "note": "See what's coming in future updates. Vote on features you'd like to see.",
                    "examples": ["/planned-features"]
                }
            },
        }

        # Note: keep the curated metadata above, but filter at runtime to only show
        # commands that are actually registered with the bot. This provides a stable
        # descriptions source while ensuring /help reflects current functionality.

    def _get_registered_command_names(self) -> set:
        """Return a set of registered command names from app commands (bot.tree)
        and legacy text commands (bot.commands)."""
        names = set()

        # App commands (slash commands, groups, etc.)
        try:
            tree = getattr(self.bot, "tree", None)
            if tree is not None:
                # walk_commands yields AppCommand or AppCommandGroup objects
                walker = getattr(tree, "walk_commands", None)
                if walker:
                    for cmd in tree.walk_commands():
                        # cmd may be an AppCommand or Group; use cmd.name
                        try:
                            names.add(cmd.name)
                        except Exception:
                            continue
                else:
                    # Fallback: iterate tree._commands if available
                    for cmd in getattr(tree, "_commands", []):
                        try:
                            names.add(cmd.name)
                        except Exception:
                            continue
        except Exception:
            logger.debug("Failed to enumerate app commands from bot.tree", exc_info=True)

        # Also include legacy commands (prefix commands)
        try:
            for cmd in getattr(self.bot, "commands", []):
                try:
                    names.add(cmd.name)
                except Exception:
                    continue
        except Exception:
            logger.debug("Failed to enumerate legacy commands", exc_info=True)

        return names

    def _get_filtered_command_categories(self) -> dict:
        """Return a copy of self.command_categories filtered to only include
        commands that are currently registered on the bot.
        
        AUTO-UPDATE FEATURE: This method auto-fills missing metadata from runtime
        command info (description, usage, examples).
        """
        registered = self._get_registered_command_names()
        filtered = {}

        # Collect runtime info to optionally fill missing metadata (description/usage/examples)
        runtime_info = self._get_runtime_command_info()

        for category, cmds in self.command_categories.items():
            kept = {}
            for cmd_name, meta in cmds.items():
                # the keys in our metadata map are command names
                if cmd_name in registered:
                    # copy metadata so we don't mutate original
                    entry = dict(meta)

                    # AUTO-UPDATE: Fill missing fields from runtime info
                    rt = runtime_info.get(cmd_name)
                    if rt:
                        if (not entry.get('desc')) and rt.get('desc'):
                            entry['desc'] = rt.get('desc')
                            logger.debug(f"Auto-filled description for {cmd_name} from runtime")
                        if (not entry.get('usage')) and rt.get('usage'):
                            entry['usage'] = rt.get('usage')
                            logger.debug(f"Auto-filled usage for {cmd_name} from runtime")
                        # Generate basic example if missing
                        if (not entry.get('examples')) and rt.get('usage'):
                            entry['examples'] = [rt.get('usage')]
                            logger.debug(f"Auto-generated example for {cmd_name} from usage")

                    kept[cmd_name] = entry

            if kept:
                filtered[category] = kept

        return filtered

    def _get_runtime_command_info(self) -> dict:
        """Return runtime info for commands: {name: {'desc':..., 'usage':...}}.

        This inspects app commands (bot.tree) and legacy commands (bot.commands).
        It is conservative and will not raise on unexpected structures.
        """
        info = {}

        # App commands
        try:
            tree = getattr(self.bot, 'tree', None)
            if tree is not None:
                walker = getattr(tree, 'walk_commands', None)
                if walker:
                    for cmd in tree.walk_commands():
                        try:
                            name = getattr(cmd, 'name', None)
                            desc = getattr(cmd, 'description', None) or getattr(cmd, 'brief', None) or ''
                            # Build a simple usage string from parameters if available
                            usage = f"/{name}"
                            params = []
                            try:
                                for p in getattr(cmd, 'parameters', []):
                                    # parameters may be inspect.Parameter objects or AppCommandParameter
                                    pname = getattr(p, 'name', None) or getattr(p, 'display_name', None)
                                    if pname:
                                        params.append(pname)
                            except Exception:
                                params = []

                            if params:
                                usage += ' ' + ' '.join([f'<{p}>' for p in params])

                            if name:
                                info[name] = {'desc': desc, 'usage': usage}
                        except Exception:
                            continue
        except Exception:
            logger.debug('Error enumerating app command runtime info', exc_info=True)

        # Legacy commands (prefix commands)
        try:
            for cmd in getattr(self.bot, 'commands', []):
                try:
                    name = getattr(cmd, 'name', None)
                    desc = getattr(cmd, 'help', None) or getattr(cmd, 'short_doc', None) or ''
                    sig = ''
                    try:
                        sig = getattr(cmd, 'signature', '')
                    except Exception:
                        sig = ''

                    usage = f"/{name} {sig}".strip()
                    if name:
                        # Do not override app command info if present
                        if name not in info:
                            info[name] = {'desc': desc, 'usage': usage}
                except Exception:
                    continue
        except Exception:
            logger.debug('Error enumerating legacy command runtime info', exc_info=True)

        return info

    async def cog_load(self):
        """Called when the cog is loaded."""
        logger.info("Help cog loaded successfully")

    @app_commands.command(name="help", description="Get comprehensive help for bot commands and features")
    @command_meta(section="Utilities", name="Help")
    @app_commands.describe(
        category="Choose a specific category to view detailed information"
    )
    @app_commands.choices(category=[
        app_commands.Choice(name="🔐 Account Management", value="account"),
        app_commands.Choice(name="📺 Anime & Manga", value="anime"),
        app_commands.Choice(name="🎮 Gaming", value="gaming"),
        app_commands.Choice(name="🎨 Customization", value="customization"),
        app_commands.Choice(name="⚙️ Server Management", value="server"),
        app_commands.Choice(name="👑 Admin", value="admin"),
        app_commands.Choice(name="👥 Social", value="social"),
        app_commands.Choice(name="🛠️ Utilities", value="utilities"),
    ])
    async def help(self, interaction: discord.Interaction, category: app_commands.Choice[str] = None):
        """Display comprehensive help information for bot commands."""
        
        try:
            logger.info(f"Help command requested by {interaction.user.display_name} (ID: {interaction.user.id}) - Category: {category.value if category else 'overview'}")
            
            # Filter categories/commands at runtime to only show registered commands
            self._filtered_command_categories = self._get_filtered_command_categories()

            if category is None:
                # Show overview of all categories
                embed = await self._create_overview_embed(interaction)
            else:
                # Show detailed category information
                embed = await self._create_category_embed(category.value, interaction)
            
            # Create navigation view
            view = HelpNavigationView(self, interaction.user)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.info(f"Help information sent successfully to {interaction.user.display_name}")
            
        except Exception as e:
            logger.error(f"Error displaying help information: {e}", exc_info=True)
            
            error_embed = build_error_embed(
                title="Error",
                description="Failed to load help information. Please try again later."
            )
            
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

    async def _create_overview_embed(self, interaction: discord.Interaction) -> discord.Embed:
        """Create the main overview embed showing all categories."""
        
        embed = discord.Embed(
            title="🤖 Lemegeton Bot - Command Help",
            description=(
                "**Welcome to Lemegeton!** Your ultimate anime/manga tracking companion with AI-powered features.\n\n"
                "**🚀 Quick Start:**\n"
                "1. Use `/login` to connect your AniList account\n"
                "2. Explore commands by category below\n"
                "3. Join our [Support Server](https://discord.gg/xUGD7krzws) for help\n"
                "4. Use `/feedback` to suggest improvements\n\n"
                "**📋 Command Categories:**"
            ),
            color=discord.Color.blue()
        )
        
        # Add category overview
        category_overview = []
        for category_name, commands in getattr(self, "_filtered_command_categories", self.command_categories).items():
            command_count = len(commands)
            category_overview.append(f"{category_name} • **{command_count} commands**")
        
        embed.add_field(
            name="Available Categories",
            value="\n".join(category_overview),
            inline=False
        )
        
        embed.add_field(
            name="💡 Pro Tips",
            value=(
                "• Most commands work better after using `/login`\n"
                "• Use the dropdown menu below to explore categories\n"
                "• Commands marked with 🔒 require registration\n"
                "• Some commands have optional parameters for flexibility"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔗 Useful Links",
            value=(
                "• [AniList Website](https://anilist.co) - Create your account\n"
                "• [Bot Invite Link](https://discord.com/api/oauth2/authorize?client_id={}&permissions=0&scope=bot%20applications.commands) - Share with friends\n"
                "• [Support Server](https://discord.gg/xUGD7krzws) - Get help and report issues\n"
                "• Use `/feedback` to report issues or suggest features"
            ).format(BOT_ID),
            inline=False
        )
        
        embed.set_footer(
            text=f"Total Commands: {sum(len(cmds) for cmds in self.command_categories.values())} | Use the dropdown to explore categories",
            icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None
        )
        
        return embed

    async def _create_category_embed(self, category_key: str, interaction: discord.Interaction) -> discord.Embed:
        """Create a detailed embed for a specific category."""
        
        category_mapping = {
            "account": "🔐 Account Management",
            "anime": "📺 Anime & Manga",
            "gaming": "🎮 Gaming",
            "customization": "🎨 Customization",
            "server": "⚙️ Server Management",
            "admin": "👑 Admin",
            "social": "👥 Social",
            "utilities": "🛠️ Utilities"
        }
        
        category_name = category_mapping.get(category_key, "Unknown Category")
        commands = self.command_categories.get(category_name, {})
        
        embed = discord.Embed(
            title=f"{category_name}",
            description=f"Detailed information for **{len(commands)} commands** in this category:",
            color=discord.Color.green()
        )
        
        # Add each command in the category
        # Use the filtered mapping if available
        commands = getattr(self, "_filtered_command_categories", self.command_categories).get(category_name, {})

        for cmd_name, cmd_info in commands.items():
            # Build the field value with optional examples
            field_value = (
                f"**Description:** {cmd_info['desc']}\n"
                f"**Usage:** `{cmd_info['usage']}`\n"
            )
            
            # Add examples if available
            if 'examples' in cmd_info and cmd_info['examples']:
                examples_text = '\n'.join([f"  • `{ex}`" for ex in cmd_info['examples']])
                field_value += f"**Examples:**\n{examples_text}\n"
            
            field_value += f"💡 *{cmd_info['note']}*"
            
            embed.add_field(
                name=f"/{cmd_name}",
                value=field_value,
                inline=False
            )
        
        # Add category-specific tips
        tips = self._get_category_tips(category_key)
        if tips:
            embed.add_field(
                name="💡 Category Tips",
                value=tips,
                inline=False
            )
        
        embed.set_footer(
            text="Use the dropdown menu to explore other categories",
            icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None
        )
        
        return embed

    def _get_category_tips(self, category_key: str) -> str:
        """Get category-specific tips and information."""
        
        tips = {
            "account": (
                "• Start with `/login` - it's required for most features\n"
                "• Your AniList username must be exact (case-sensitive)\n"
                "• Use the **Check AniList** button in the `/login` interface to verify usernames before registration\n"
                "• You can update or change your linked account anytime\n"
                "• View profiles with `/profile` to see stats, achievements, and more"
            ),
            "anime": (
                "• Most commands work with both anime and manga\n"
                "• Recommendations use advanced AI filtering for quality results\n"
                "• Rate titles 8.0+ for best recommendation accuracy\n"
                "• Browse supports advanced filtering by genre, year, format\n"
                "• News monitoring tracks Twitter/X accounts for updates (Bot Moderator only)\n"
                "• Use `/trailer` to watch official trailers before starting a series\n"
                "• Try `/random all` to discover completely random suggestions\n"
                "• Create shareable 3x3 grids with `/3x3`"
            ),
            "gaming": (
                "• Steam integration provides game recommendations\n"
                "• Based on your gaming preferences and activity\n"
                "• Discover new games similar to ones you enjoy\n"
                "• Use `/steam-game` to search for specific games\n"
                "• Free games checker monitors Epic, GOG, and Steam automatically\n"
                "• Set up notifications for free game alerts"
            ),
            "customization": (
                "• Themes personalize your bot experience\n"
                "• Preview themes before applying them\n"
                "• Server boosters can create custom roles with `/nitro-role-set`\n"
                "• Bot moderators can set guild-wide themes\n"
                "• Individual user preferences override guild themes"
            ),
            "server": (
                "• Server-config provides centralized server management\n"
                "• Configure roles, channels, and notification settings\n"
                "• Track invite statistics and recruitment data\n"
                "• Set up welcome DMs for new server boosters\n"
                "• Requires 'Manage Server' permission for most commands"
            ),
            "admin": (
                "• Bot moderators have bot-wide permissions\n"
                "• Manage bot moderators with `/admin-moderator-manage`\n"
                "• Publish changelogs with `/changelog`\n"
                "• Configure bot update channels\n"
                "• All admin commands require Bot Moderator or Admin permissions"
            ),
            "social": (
                "• Compare your anime/manga tastes with others using `/affinity`\n"
                "• View server leaderboards for activity rankings\n"
                "• Submit feedback to help improve the bot\n"
                "• Leaderboards are server-specific and update automatically"
            ),
            "utilities": (
                "• Manage your notification preferences\n"
                "• View planned features and vote on upcoming updates\n"
                "• Use `/say` to send messages as the bot (Moderators only)\n"
                "• Generate Discord timestamps with `/timestamp`\n"
                "• View detailed user information with `/userinfo`\n"
                "• All `/say` command usage is logged for accountability"
            )
        }
        
        return tips.get(category_key, "")


class HelpNavigationView(discord.ui.View):
    """Navigation view for help command with dropdown menu."""
    
    def __init__(self, help_cog: HelpCog, user: discord.User):
        super().__init__(timeout=300)  # 5 minute timeout
        self.help_cog = help_cog
        self.user = user
        
        # Add the dropdown select menu
        self.add_item(CategorySelect(help_cog))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the original user to interact with the view."""
        if interaction.user != self.user:
            await interaction.response.send_message(
                embed=build_warning_embed(
                    description="You can't use this menu. Use `/help` to get your own help interface!"
                ),
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        """Disable all items when the view times out."""
        for item in self.children:
            item.disabled = True


class CategorySelect(discord.ui.Select):
    """Dropdown select menu for choosing help categories."""
    
    def __init__(self, help_cog: HelpCog):
        self.help_cog = help_cog
        
        options = [
            discord.SelectOption(
                label="📋 Overview",
                value="overview",
                description="Show all categories and getting started info",
                emoji="📋"
            ),
            discord.SelectOption(
                label="Account Management",
                value="account",
                description="Registration and account settings",
                emoji="🔐"
            ),
            discord.SelectOption(
                label="Anime & Manga",
                value="anime", 
                description="Browse, track, and discover titles",
                emoji="📺"
            ),
            discord.SelectOption(
                label="Gaming",
                value="gaming",
                description="Steam integration and game recommendations",
                emoji="🎮"
            ),
            discord.SelectOption(
                label="Customization",
                value="customization",
                description="Themes and personalization",
                emoji="🎨"
            ),
            discord.SelectOption(
                label="Server Management",
                value="server",
                description="Server configuration and moderation",
                emoji="⚙️"
            ),
            discord.SelectOption(
                label="Admin",
                value="admin",
                description="Bot moderation and admin commands",
                emoji="👑"
            ),
            discord.SelectOption(
                label="Social",
                value="social",
                description="Leaderboards, affinity, and feedback",
                emoji="👥"
            ),
            discord.SelectOption(
                label="Utilities",
                value="utilities",
                description="Help, notifications, and utility commands",
                emoji="🛠️"
            )
        ]
        
        super().__init__(
            placeholder="📖 Choose a category to explore...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle selection from the dropdown menu."""
        
        selected_value = self.values[0]
        
        try:
            if selected_value == "overview":
                embed = await self.help_cog._create_overview_embed(interaction)
            else:
                embed = await self.help_cog._create_category_embed(selected_value, interaction)
            
            await interaction.response.edit_message(embed=embed, view=self.view)
            
            logger.info(f"Help category '{selected_value}' displayed for {interaction.user.display_name}")
            
        except Exception as e:
            logger.error(f"Error in category selection: {e}", exc_info=True)
            
            await interaction.response.send_message(
                embed=build_error_embed(
                    description="An error occurred while loading that category. Please try again."
                ),
                ephemeral=True
            )


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(HelpCog(bot))
    logger.info("Help cog successfully loaded")