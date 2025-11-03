import discord
from discord import app_commands
from discord.ext import commands
import logging
from pathlib import Path
from config import BOT_ID
from cogs_test.general_commands.dashboard import command_meta

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
                    "desc": "Manage your account - register, update, or unregister",
                    "usage": "/login",
                    "note": "Start here to connect your AniList account!",
                    "examples": ["/login"]
                }
            },
            "📊 Profile & Stats": {
                "profile": {
                    "desc": "View your AniList profile with comprehensive stats, achievements, and bio gallery",
                    "usage": "/profile [user]",
                    "note": "Features: 🖼️ Gallery (view all bio images), 🏅 Achievements, ⭐ Favorites, 📝 Bio with auto-cleanup, 👥 Social stats, 📅 Account age. Data cached for 12 hours for faster loading.",
                    "examples": ["/profile", "/profile @username"]
                }
            },
            "📺 Anime & Manga": {
                "browse": {
                    "desc": "Search and browse anime, manga, light novels, and general novels",
                    "usage": "/browse",
                    "note": "Interactive browsing with advanced filtering and sorting options",
                    "examples": ["/browse"]
                },
                "trending": {
                    "desc": "View trending anime and manga",
                    "usage": "/trending",
                    "note": "See what's popular right now",
                    "examples": ["/trending"]
                },
                "recommendations": {
                    "desc": "Get personalized recommendations based on your highly-rated manga (≥8.0/10)",
                    "usage": "/recommendations [member]",
                    "note": "AI-powered recommendations with interactive browsing by category",
                    "examples": ["/recommendations", "/recommendations @friend"]
                },
                "random": {
                    "desc": "Get random anime/manga/light novel suggestions from AniList",
                    "usage": "/random <media_type>",
                    "note": "For when you can't decide what to watch/read - supports Anime, Manga, Light Novel, or All",
                    "examples": ["/random anime", "/random manga", "/random light_novel", "/random all"]
                },
                "trailer": {
                    "desc": "Get the official trailer for an anime or manga from AniList",
                    "usage": "/trailer <type> <title>",
                    "note": "Fetches trailers with autocomplete support and debug options",
                    "examples": ["/trailer anime Demon Slayer", "/trailer manga Chainsaw Man"]
                },
                "3x3": {
                    "desc": "🎨 Create a 3x3 grid of your favorite anime, manga, or characters",
                    "usage": "/3x3 <media_type>",
                    "note": "Generate shareable 3x3 grids with custom selections. Supports anime, manga, characters, and games. Fetches covers/images from AniList automatically.",
                    "examples": ["/3x3 anime", "/3x3 manga", "/3x3 character", "/3x3 games"]
                },
                "admin-news-manage": {
                    "desc": "Manage Twitter/X news monitoring for anime/manga updates",
                    "usage": "/admin-news-manage",
                    "note": "Monitor Twitter accounts for anime/manga news",
                    "examples": ["/admin-news-manage"]
                }
            },
            "🏆 Challenges & Competition": {
                "challenge_progress": {
                    "desc": "View your reading challenge progress",
                    "usage": "/challenge_progress",
                    "note": "Track your annual reading goals",
                    "examples": ["/challenge_progress"]
                },
                "challenge_update": {
                    "desc": "Update your challenge progress",
                    "usage": "/challenge_update",
                    "note": "Manually update your reading challenge",
                    "examples": ["/challenge_update"]
                },
                "challenge_manage": {
                    "desc": "Manage reading challenges",
                    "usage": "/challenge_manage",
                    "note": "Create and manage reading challenges",
                    "examples": ["/challenge_manage"]
                },
                "challenge_leaderboard": {
                    "desc": "View challenge leaderboards",
                    "usage": "/challenge_leaderboard",
                    "note": "See who's leading in various challenges",
                    "examples": ["/challenge_leaderboard"]
                },
                "leaderboard": {
                    "desc": "View server leaderboards for various metrics",
                    "usage": "/leaderboard",
                    "note": "Server rankings and competitions",
                    "examples": ["/leaderboard"]
                },
                "affinity": {
                    "desc": "Compare your affinity with all users or a specific user in this server",
                    "usage": "/affinity [user]",
                    "note": "See how similar your anime/manga tastes are with others",
                    "examples": ["/affinity", "/affinity @friend"]
                },
                "anilist_leaderboard": {
                    "desc": "🏆 Show leaderboard ranked by manga, anime, or combined activity",
                    "usage": "/anilist_leaderboard <medium>",
                    "note": "View rankings by chapters read, episodes watched, or completed series",
                    "examples": ["/anilist_leaderboard chapters", "/anilist_leaderboard anime_completed"]
                }
            },
            "🎮 Gaming": {
                "steam-profile": {
                    "desc": "Show a Steam profile (vanity or SteamID)",
                    "usage": "/steam-profile <username>",
                    "note": "View Steam user profiles and stats",
                    "examples": ["/steam-profile gaben", "/steam-profile 76561197960287930"]
                },
                "steam-recommendation": {
                    "desc": "Get personalized game recommendations based on your Steam library",
                    "usage": "/steam-recommendation <username>",
                    "note": "Discover new games similar to ones you enjoy",
                    "examples": ["/steam-recommendation gaben"]
                },
                "steam": {
                    "desc": "Search for games on Steam with advanced filters",
                    "usage": "/steam game <game_name> [filters]",
                    "note": "Filter by genre, price, platform, tags, and sort options with fuzzy matching",
                    "examples": ["/steam game Elden Ring", "/steam game god war genre:action max_price:30"]
                },
                "free-games": {
                    "desc": "Manage free games notifications with interactive interface",
                    "usage": "/free-games",
                    "note": "Check current free games and setup automatic notifications (Epic, GOG, Steam). Checks every 6 hours.",
                    "examples": ["/free-games"]
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
                "server-config": {
                    "desc": "Configure server settings - roles, channels, and notifications",
                    "usage": "/server-config",
                    "note": "Manage server-wide bot configuration (Admin only)",
                    "examples": ["/server-config"]
                },
                "admin-moderator-manage": {
                    "desc": "Manage bot moderators (bot-wide permissions)",
                    "usage": "/admin-moderator-manage",
                    "note": "Add/remove bot moderators with elevated permissions",
                    "examples": ["/admin-moderator-manage"]
                },
                "set_bot_updates_channel": {
                    "desc": "Set channel to receive bot updates and announcements (Admin only)",
                    "usage": "/set_bot_updates_channel <channel>",
                    "note": "Configure where bot update notifications appear",
                    "examples": ["/set_bot_updates_channel #bot-updates"]
                },
                "set_animanga_completion_channel": {
                    "desc": "Set channel to receive anime/manga completion updates (Mod only)",
                    "usage": "/set_animanga_completion_channel <channel>",
                    "note": "Monitor when users complete series",
                    "examples": ["/set_animanga_completion_channel #completions"]
                },
                "changelog": {
                    "desc": "Create and publish a changelog from an uploaded text file (Bot Moderator only)",
                    "usage": "/changelog <file> [options]",
                    "note": "Publish formatted changelogs with customizable appearance and notifications",
                    "examples": ["/changelog"]
                },
                "set-welcome-dm": {
                    "desc": "Set the welcome DM message by uploading a text file (Admin only)",
                    "usage": "/set-welcome-dm <text_file>",
                    "note": "Configure automated welcome messages sent to new server boosters",
                    "examples": ["/set-welcome-dm"]
                },
                "welcome-dm-status": {
                    "desc": "Check the current welcome DM configuration (Admin only)",
                    "usage": "/welcome-dm-status",
                    "note": "View current welcome DM settings and status",
                    "examples": ["/welcome-dm-status"]
                },
                "admin-login": {
                    "desc": "Link a Discord user with an AniList username (Admin only)",
                    "usage": "/admin-login <discord_user> <anilist_user>",
                    "note": "Manually link users' Discord accounts to AniList profiles",
                    "examples": ["/admin-login @user theiranilistname"]
                }
            },
            "🛠️ Utilities": {
                "notifications": {
                    "desc": "Manage your bot update notification preferences",
                    "usage": "/notifications",
                    "note": "Control what notifications you receive",
                    "examples": ["/notifications"]
                },
                "planned": {
                    "desc": "View planned bot features",
                    "usage": "/planned",
                    "note": "See what's coming in future updates",
                    "examples": ["/planned"]
                }
            },
            "ℹ️ Bot Information": {
                "invite": {
                    "desc": "Get an invite link to add this bot to your server",
                    "usage": "/invite",
                    "note": "Share the bot with other servers",
                    "examples": ["/invite"]
                },
                "feedback": {
                    "desc": "Submit ideas or report bugs",
                    "usage": "/feedback",
                    "note": "Help improve the bot with your suggestions",
                    "examples": ["/feedback ideas Add more themes", "/feedback bugs Profile not loading"]
                },
                "help": {
                    "desc": "Display this help information",
                    "usage": "/help [category]",
                    "note": "Get detailed command information",
                    "examples": ["/help", "/help anime", "/help gaming"]
                }
            }
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
        app_commands.Choice(name="📊 Profile & Stats", value="profile"),
        app_commands.Choice(name="📺 Anime & Manga", value="anime"),
        app_commands.Choice(name="🏆 Challenges", value="challenges"),
        app_commands.Choice(name="🎮 Gaming", value="gaming"),
        app_commands.Choice(name="🎨 Customization", value="customization"),
        app_commands.Choice(name="⚙️ Server Management", value="server"),
        app_commands.Choice(name="🛠️ Utilities", value="utilities"),
        app_commands.Choice(name="ℹ️ Bot Info", value="info"),
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
            
            error_embed = discord.Embed(
                title="❌ Error",
                description="Failed to load help information. Please try again later.",
                color=discord.Color.red()
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
            "profile": "📊 Profile & Stats", 
            "anime": "📺 Anime & Manga",
            "challenges": "🏆 Challenges & Competition",
            "gaming": "🎮 Gaming",
            "customization": "🎨 Customization",
            "server": "⚙️ Server Management",
            "utilities": "🛠️ Utilities",
            "info": "ℹ️ Bot Information"
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
                "• You can update or change your linked account anytime"
            ),
            "profile": (
                "• Profiles show achievements, stats, and activity\n"
                "• Stats include detailed breakdowns of your watching history\n"
                "• You can view other users' profiles if they're registered"
            ),
            "anime": (
                "• Most commands work with both anime and manga\n"
                "• Recommendations use advanced AI filtering for quality results\n"
                "• Rate titles 8.0+ for best recommendation accuracy\n"
                "• Browse supports advanced filtering by genre, year, format\n"
                "• News monitoring tracks Twitter/X accounts for updates\n"
                "• Use `/trailer` to watch official trailers before starting a series\n"
                "• Try `/random all` to discover completely random suggestions"
            ),
            "challenges": (
                "• Join reading challenges to stay motivated\n"
                "• Progress updates automatically from your AniList\n"
                "• Compete with friends on the leaderboards"
            ),
            "gaming": (
                "• Steam integration provides game recommendations\n"
                "• Based on your gaming preferences and activity\n"
                "• Discover new games similar to ones you enjoy\n"
                "• Use `/steam game` with filters for precise searches"
            ),
            "customization": (
                "• Themes personalize your bot experience\n"
                "• Preview themes before applying them\n"
                "• Server moderators can set guild-wide themes\n"
                "• Individual user preferences override guild themes"
            ),
            "server": (
                "• Server-config provides centralized server management\n"
                "• Configure roles, channels, and notification settings\n"
                "• Bot moderators have bot-wide permissions\n"
                "• Requires Admin or Moderator permissions"
            ),
            "utilities": (
                "• Manage your notification preferences\n"
                "• View planned features and upcoming updates\n"
                "• These commands enhance your bot experience"
            ),
            "info": (
                "• Use `/feedback` to suggest improvements\n"
                "• Share the bot with `/invite` command\n"
                "• Join our [Support Server](https://discord.gg/xUGD7krzws) for help"
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
                "❌ You can't use this menu. Use `/help` to get your own help interface!",
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
                label="Profile & Stats", 
                value="profile",
                description="View profiles and statistics",
                emoji="📊"
            ),
            discord.SelectOption(
                label="Anime & Manga",
                value="anime", 
                description="Browse, track, and discover titles",
                emoji="📺"
            ),
            discord.SelectOption(
                label="Challenges",
                value="challenges",
                description="Reading challenges and leaderboards", 
                emoji="🏆"
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
                label="Utilities",
                value="utilities",
                description="Notifications and utility commands",
                emoji="🛠️"
            ),
            discord.SelectOption(
                label="Bot Information",
                value="info",
                description="Feedback and bot info",
                emoji="ℹ️"
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
                "❌ An error occurred while loading that category. Please try again.",
                ephemeral=True
            )


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(HelpCog(bot))
    logger.info("Help cog successfully loaded")