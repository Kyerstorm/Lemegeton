from helpers.color_palette import PALETTE
import discord
from helpers.command_error_handler import FeedbackAwareView, application_error_message, handle_component_error
from discord import app_commands
from discord.ext import commands
import logging
from pathlib import Path
from config import ADMIN_DISCORD_ID, BOT_ID
from cogs_test.general_commands.dashboard import command_meta
from helpers.embed_helper import build_error_embed, build_warning_embed
from helpers.repo_stats import collect_repository_stats, format_bytes

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

        # Cache repository metrics once; the README updater uses the same calculation.
        try:
            self.repository_stats = collect_repository_stats()
        except Exception:
            logger.warning("Could not calculate repository statistics", exc_info=True)
            self.repository_stats = None
        
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
                    "desc": "Search or discover anime, manga, novels, books, webnovels, movies, and TV shows",
                    "usage": "/browse <media_type> [title] [filters]",
                    "note": "Title searches show detailed metadata. Leave title blank for multi-result TMDB movie/TV discovery with genre, keyword, year, runtime, language, director/cast, rating, and sort filters.",
                    "examples": ["/browse media_type:Movies", "/browse media_type:TV Shows genre:Drama year_from:2020", "/browse media_type:Movies genre:Science fiction minimum_rating:7.5 sort_by:Highest rated"]
                },
                "trending": {
                    "desc": "View trending anime, manga, light novels, movies, and TV shows",
                    "usage": "/trending [media_type] [time_window] [genre] [media_format]",
                    "note": "AniList powers anime/manga rankings; TMDB powers movie/TV trends. Day/week windows apply to TMDB and require TMDB_BEARER_TOKEN.",
                    "examples": ["/trending", "/trending media_type:Movies time_window:This Week", "/trending media_type:TV Shows genre:Drama"]
                },
                "recommendations": {
                    "desc": "Get personalized manga recommendations based on your highly-rated library",
                    "usage": "/recommendations [username]",
                    "note": "Uses available AniList library and rating data; it does not call an AI model. Results depend on the linked account and provider data.",
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
                    "note": "Generate grids for anime, manga, characters, or games. By default images are sent as Discord attachments; generated files can use a separately configured public S3/CDN bucket.",
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
            "👥 Community Archives & Events": {
                "panels": {
                    "desc": "Open the shared manga panel archive to browse, search, contribute, or manage your submissions",
                    "usage": "/panels",
                    "note": "Panel records are shared across servers, but archive settings and moderation are server-specific. Mature panels are hidden outside age-restricted channels. Private S3 originals are used when configured; the existing Discord-backed path remains supported.",
                    "examples": ["/panels"]
                },
                "panel-of-the-day": {
                    "desc": "View this server's selected safe panel for today",
                    "usage": "/panel-of-the-day",
                    "note": "Uses the server's configured daily selection and existing panel archive; it does not create a new submission.",
                    "examples": ["/panel-of-the-day"]
                },
                "archive": {
                    "desc": "Open the unified panel-style community archive for quotes, fanworks, moodboards, soundtracks, scenes, recommendations, and theories",
                    "usage": "/archive",
                    "note": "Choose an archive and action in the interactive menu. Browse uses card-style entries; Submit, Search, Report, and moderation actions open focused modals. Review permissions and originating-server restrictions are preserved.",
                    "examples": ["/archive"]
                },
                "media-bracket": {
                    "desc": "Create a server-specific elimination poll for media titles",
                    "usage": "/media-bracket <action> [title] [candidates] [bracket_id] [choice] [media_type]",
                    "note": "Actions: Start, Vote, Results. A new bracket needs 2–16 distinct candidates separated by |. Votes are server-specific and can be changed while open.",
                    "examples": ["/media-bracket action:results bracket_id:ABC123"]
                },
                "adaptation-vote": {
                    "desc": "Create a poll and compare community preferences between two adaptations or versions",
                    "usage": "/adaptation-vote <action> [title] [option_a] [option_b] [poll_id] [choice] [media_type] [source_url]",
                    "note": "Actions: Create, Vote, Results. Vote with A or B. Results represent community preference, not an objective quality score; polls are server-specific.",
                    "examples": ["/adaptation-vote action:results poll_id:ABC123", "/adaptation-vote action:vote poll_id:ABC123 choice:A"]
                },
                "media-quiz": {
                    "desc": "Add source-linked trivia, play a random question, or submit an answer privately",
                    "usage": "/media-quiz <action> [question] [answer] [source_url]",
                    "note": "Actions: Add, Play, Answer. Questions belong to the current server; answering requires an active quiz session in the same channel.",
                    "examples": ["/media-quiz action:play", "/media-quiz action:answer answer:Example"]
                },
                "media-night": {
                    "desc": "Open or join this server's community media-night voting",
                    "usage": "/media-night start | /media-night close",
                    "note": "Start a server/channel-specific voting session with provider filters, title-labelled voting buttons, and live vote totals; the host or a moderator can close it.",
                    "examples": ["/media-night start", "/media-night close"]
                },
                "discussion": {
                    "desc": "Open one discussion modal for chapter, volume, episode, season, or general media threads",
                    "usage": "/discussion",
                    "note": "Choose the discussion scope, then enter a work title and explicit spoiler cutoff. A public starter message and server-local thread are created.",
                    "examples": ["/discussion"]
                }
            },
            "🌐 Cross-Media Discovery": {
                "discovery-hub": {
                    "desc": "Open the guided menu for media discovery and community features",
                    "usage": "/discovery-hub",
                    "note": "Choose a section from the private dropdown. This is a guide, not a title search.",
                    "examples": ["/discovery-hub"]
                },
                "compare": {
                    "desc": "Compare two or more media entries side-by-side",
                    "usage": "/compare",
                    "note": "Shows fields supported by the selected media categories; available metadata varies by provider.",
                    "examples": ["/compare"]
                },
                "franchise": {
                    "desc": "Explore provider-declared relationships and supported adaptations",
                    "usage": "/franchise <title> [category]",
                    "note": "AniList relationships, TMDB collection membership, recommendations, and cross-provider matches are labelled separately. Similar titles are not confirmed adaptations.",
                    "examples": ["/franchise Re:Zero", "/franchise Dune category:BOOK"]
                },
                "similar": {
                    "desc": "Find related media across supported providers",
                    "usage": "/similar <title> <category>",
                    "note": "Combines provider suggestions, conservative genre overlap, saved links, and eligible human-written community recommendations. Sources remain distinct.",
                    "examples": ["/similar Frieren category:ANIME", "/similar Dune category:BOOK"]
                },
                "connections": {
                    "desc": "Resolve a title and browse its known media relationships",
                    "usage": "/connections <title> [category]",
                    "note": "Reuses the franchise resolver and title-selection menu to keep similarly named works separate.",
                    "examples": ["/connections The Apothecary Diaries", "/connections Lord of the Mysteries category:WEBNOVEL"]
                },
                "link-suggest": {
                    "desc": "Open a guided relationship menu and modal to suggest a connection between two media works",
                    "usage": "/link-suggest",
                    "note": "Choose source and target media categories and the relationship type first, then provide two HTTPS metadata URLs and evidence. Suggestions remain pending until moderators in the current server review them.",
                    "examples": ["/link-suggest"]
                },
                "link-review": {
                    "desc": "Inspect and review this server's proposed media relationships",
                    "usage": "/link-review [decision] [suggestion_id] [reason]",
                    "note": "Review actions are moderator-gated and scoped to this server. List suggestions first to obtain an ID.",
                    "examples": ["/link-review", "/link-review decision:inspect suggestion_id:12", "/link-review decision:approved suggestion_id:12"]
                }
            },
            "📚 Books & Webnovels": {
                "reading": {
                    "desc": "Open the unified Reading Hub for nominations, votes, selection, scheduled group discussions, and reading-order exploration",
                    "usage": "/reading",
                    "note": "Choose an action and media category. Nominations and votes are server-local; discussion scheduling requires a moderator and a future ISO-8601 time with a timezone.",
                    "examples": ["/reading"]
                },
                "author-works": {
                    "desc": "Search Google Books for titles attributed to an author",
                    "usage": "/author-works <author>",
                    "note": "Attribution and edition coverage depend on Google Books records.",
                    "examples": ["/author-works Ursula K. Le Guin"]
                },
                "webnovel-updates": {
                    "desc": "Search live Novel Updates and Novel Phoenix pages for webnovel metadata",
                    "usage": "/webnovel-updates <title>",
                    "note": "Set NOVELUPDATES_DATASET_PATH to a local upstream CSV/JSON file for fast indexed lookup. The v0.1.5 snapshot is dated 2025-08-21; misses fall back to live scraping, and snapshot metadata can be stale.",
                    "examples": ["/webnovel-updates Lord of the Mysteries"]
                },
            "🎬 Movies & TV": {
                "tv-guide": {
                    "desc": "Browse supported TV seasons, episodes, and air-date information",
                    "usage": "/tv-guide",
                    "note": "Shows season and episode metadata returned by supported providers; missing episode data is not inferred.",
                    "examples": ["/tv-guide"]
                },
                "release-calendar": {
                    "desc": "Browse supported upcoming anime, movie, and TV release dates",
                    "usage": "/release-calendar",
                    "note": "The menu offers a seven-day preview, modal-based digest configuration, and per-server digest disabling. Dates depend on provider availability and may not be exhaustive.",
                    "examples": ["/release-calendar"]
                },
                "where-to-watch": {
                    "desc": "Find listed streaming, rental, and purchase providers for a movie or TV series",
                    "usage": "/where-to-watch <title> <media_type> [region]",
                    "note": "Requires TMDB_BEARER_TOKEN. Region defaults to this server's configured country; availability can change.",
                    "examples": ["/where-to-watch Dune media_type:Movie", "/where-to-watch Severance media_type:TV region:IE"]
                },
                "person-credits": {
                    "desc": "Browse a TMDB person's combined film and television credits",
                    "usage": "/person-credits <name>",
                    "note": "Choose the exact person from results to avoid mixing people with similar names. Requires TMDB_BEARER_TOKEN.",
                    "examples": ["/person-credits Denis Villeneuve"]
                },
                "trailers": {
                    "desc": "Find TMDB-listed videos, trailers, and teasers",
                    "usage": "/trailers <title> <media_type>",
                    "note": "Choose the exact movie or series first. Only supported YouTube and Vimeo links are displayed. Requires TMDB_BEARER_TOKEN.",
                    "examples": ["/trailers Dune media_type:Movie", "/trailers Arcane media_type:TV"]
                },
                "collection-guide": {
                    "desc": "Explore a movie's TMDB collection and listed films",
                    "usage": "/collection-guide <title>",
                    "note": "Uses source collection membership and release dates. Release order does not establish story chronology.",
                    "examples": ["/collection-guide Toy Story"]
                },
                "media-region": {
                    "desc": "Set this server's default country for streaming availability",
                    "usage": "/media-region <region>",
                    "note": "Requires Manage Server permission. Enter a two-letter country code such as IE, GB, US, or JP.",
                    "examples": ["/media-region IE"]
                }
            },
            "🎮 Gaming": {
                "game": {
                    "desc": "Search IGDB for game metadata and enrich exact matches with Steam store details",
                    "usage": "/game <title>",
                    "note": "Shows developers, publishers, platforms, release information, and available Steam data. Ambiguous results use a selection menu; Steam matches are not inferred from fuzzy titles.",
                    "examples": ["/game Hades", "/game Baldur's Gate 3"]
                },
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
                "github": {
                    "desc": "GitHub commit tracker - new commits are posted to bot update channels automatically (Bot Moderator only)",
                    "usage": "/github recent [count] [publish_to] | /github status | /github check",
                    "note": "Commits are checked every few minutes and posted to every configured bot updates channel. Use `recent` to preview or re-post the latest commits, `check` to poll immediately.",
                    "examples": ["/github recent", "/github recent count:10 publish_to:All Servers", "/github status", "/github check"]
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
        """Return registered application-command names; prefix commands have a private owner section."""
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

        # Documentation page, not a slash-command category; always keep it in the menu.
        filtered["💻 Code"] = {}
        return filtered

    async def _is_bot_owner(self, user: discord.abc.User) -> bool:
        """Resolve owner access using the configured owner ID and application ownership."""
        if ADMIN_DISCORD_ID and user.id == ADMIN_DISCORD_ID:
            return True
        try:
            return bool(await self.bot.is_owner(user))
        except Exception:
            logger.debug("Unable to resolve bot owner for user %s", getattr(user, "id", "unknown"), exc_info=True)
            return False

    def _get_owner_prefix_commands(self) -> dict:
        """Build prefix-command metadata for the owner-only help category."""
        result = {}
        try:
            commands_iter = self.bot.walk_commands()
        except Exception:
            commands_iter = getattr(self.bot, "commands", [])

        for command in commands_iter:
            try:
                name = getattr(command, "qualified_name", None) or getattr(command, "name", None)
                if not name:
                    continue
                signature = (getattr(command, "signature", "") or "").strip()
                usage = "!" + name + ((" " + signature) if signature else "")
                description = (
                    getattr(command, "help", None)
                    or getattr(command, "description", None)
                    or getattr(command, "short_doc", None)
                    or "Prefix command."
                )
                aliases = list(getattr(command, "aliases", []) or [])
                note = "Prefix command."
                if aliases:
                    note += " Aliases: " + ", ".join("!" + alias for alias in aliases[:8]) + "."
                result[name] = {
                    "desc": str(description)[:500],
                    "usage": usage[:200],
                    "note": note[:500],
                    "examples": [usage[:200]],
                }
            except Exception:
                logger.debug("Skipping an unreadable prefix command in owner help", exc_info=True)

        return result

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
        app_commands.Choice(name="🌐 Cross-Media Discovery", value="cross_media"),
        app_commands.Choice(name="📚 Books & Webnovels", value="books"),
        app_commands.Choice(name="🎬 Movies & TV", value="screen"),
        app_commands.Choice(name="👥 Community Archives & Events", value="community"),
        app_commands.Choice(name="💻 Code", value="code"),
    ])
    async def help(self, interaction: discord.Interaction, category: app_commands.Choice[str] = None):
        """Display comprehensive help information for bot commands."""
        
        try:
            logger.info(f"Help command requested by {interaction.user.display_name} (ID: {interaction.user.id}) - Category: {category.value if category else 'overview'}")
            
            # Keep user-specific help data local to this invocation to avoid cross-user leakage.
            filtered_categories = self._get_filtered_command_categories()
            is_owner = await self._is_bot_owner(interaction.user)
            if is_owner:
                prefix_commands = self._get_owner_prefix_commands()
                if prefix_commands:
                    filtered_categories["🔒 Bot Owner — Prefix Commands"] = prefix_commands

            if category is None:
                embed = await self._create_overview_embed(interaction, filtered_categories)
            else:
                embed = await self._create_category_embed(category.value, interaction, filtered_categories)

            # Ephemeral response plus user-bound navigation keeps this help private.
            view = HelpNavigationView(self, interaction.user, filtered_categories, is_owner=is_owner)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.info(f"Help information sent successfully to {interaction.user.display_name}")
            
        except Exception as e:
            logger.error(f"Error displaying help information: {e}", exc_info=True)
            
            error_embed = build_error_embed(
                title="Error",
                description=application_error_message(e)
            )
            
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=error_embed, ephemeral=True)
            except discord.HTTPException:
                logger.debug("Could not send help error response", exc_info=True)

    async def _create_overview_embed(
        self,
        interaction: discord.Interaction,
        categories: dict = None,
    ) -> discord.Embed:
        """Create an overview using only the categories visible to this requester."""
        categories = categories if categories is not None else self.command_categories
        total_commands = sum(len(items) for items in categories.values())

        embed = discord.Embed(
            title="🤖 Lemegeton Bot - Command Help",
            description=(
                "**Welcome to Lemegeton!** Media discovery, community features, and gaming metadata connected through existing providers.\n\n"
                "**✦ Get started**\n"
                "1. Use `/help` and choose a category from the dropdown.\n"
                "2. Use `/browse` to search supported media.\n"
                "3. Open `/discovery-hub` for the guided discovery menu.\n"
                "4. Use `/feedback` to suggest improvements or report a bug.\n\n"
                "**✦ Browse the systems below**"
            ),
            color=PALETTE.PRIMARY
        )
        
        # Add category overview
        category_overview = []
        for category_name, commands in categories.items():
            command_count = len(commands)
            if category_name == "💻 Code":
                category_overview.append(f"{category_name} • **Architecture guide**")
            else:
                category_overview.append(f"{category_name} • **{command_count} commands**")
        
        embed.add_field(
            name="Available Categories",
            value="\n".join(category_overview),
            inline=False
        )
        
        if self.repository_stats:
            stats = self.repository_stats
            language_breakdown = " · ".join(
                f"{name}: {count:,}"
                for name, count in sorted(
                    stats["language_lines"].items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ) or "No source files detected"
            if len(language_breakdown) > 500:
                language_breakdown = language_breakdown[:497] + "..."

            embed.add_field(
                name="📊 Repository statistics",
                value=(
                    f"**Files:** {stats['tracked_files']:,} tracked · "
                    f"{stats['text_files']:,} text · {stats['source_files']:,} source\n"
                    f"**Source lines:** {stats['source_lines']:,} "
                    f"({stats['nonblank_source_lines']:,} non-blank)\n"
                    f"**Text lines:** {stats['text_lines']:,} · "
                    f"**Characters:** {stats['text_characters']:,} (excluding line breaks)\n"
                    f"**Text size:** {format_bytes(stats['text_bytes'])}\n"
                    f"**Source mix:** {language_breakdown}"
                ),
                inline=False,
            )

        embed.add_field(
            name="💡 Pro Tips",
            value=(
                "• Use the dropdown below to browse by feature\n"
                "• Some AniList personal features require `/login`; public metadata searches may not\n"
                "• Provider outages can temporarily affect results\n"
                "• Use `/feedback` to report a reproducible issue"
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
            text=f"{total_commands} available commands • Select a category to explore",
            icon_url=getattr(getattr(self.bot, "user", None), "display_avatar", None).url if getattr(getattr(self.bot, "user", None), "display_avatar", None) else None
        )
        
        return embed

    async def _create_category_embed(
        self,
        category_key: str,
        interaction: discord.Interaction,
        categories: dict = None,
    ) -> discord.Embed:
        """Create a category page using only commands visible to this requester."""
        categories = categories if categories is not None else self.command_categories
        if category_key == "owner" and not await self._is_bot_owner(interaction.user):
            return build_warning_embed(
                title="Owner Commands",
                description="This help category is available only to the bot owner.",
            )

        category_mapping = {
            "account": "🔐 Account Management",
            "anime": "📺 Anime & Manga",
            "gaming": "🎮 Gaming",
            "customization": "🎨 Customization",
            "server": "⚙️ Server Management",
            "admin": "👑 Admin",
            "social": "👥 Social",
            "utilities": "🛠️ Utilities",
            "cross_media": "🌐 Cross-Media Discovery",
            "books": "📚 Books & Webnovels",
            "screen": "🎬 Movies & TV",
            "community": "👥 Community Archives & Events",
            "code": "💻 Code",
            "owner": "🔒 Bot Owner — Prefix Commands",
        }
        category_name = category_mapping.get(category_key, "Unknown Category")
        command_items = categories.get(category_name, {})

        if category_key == "code":
            embed = discord.Embed(
                title="💻 Code",
                description=(
                    "A maintainer-friendly guide to how Lemegeton's command, provider, database, and image-storage systems fit together. "
                    "External providers can be incomplete or temporarily unavailable."
                ),
                color=PALETTE.PRIMARY,
            )
            sections = [
                (
                    "◇ Command layer",
                    "Slash-command cogs validate input, collect provider data, and render embeds or selection menus. This help menu filters curated descriptions against commands registered at runtime, so unloaded commands are not presented as available.",
                ),
                (
                    "◇ Cross-media command map",
                    "/franchise explores provider-declared relationships and labels recommendations separately. /connections and the Reading Hub reuse the title resolver. /similar combines provider suggestions, genre overlap, saved links, and eligible human-written community recommendations. /game starts with IGDB and only adds Steam details for a suitable exact title match.",
                ),
                (
                    "◇ Metadata providers",
                    "AniList supplies supported anime/manga metadata and relationships; TMDB supplies movie/TV information, credits, videos, collections, and region availability; Google Books supplies book/author records; live Novel Updates and Novel Phoenix search provide webnovel metadata; IGDB supplies game metadata, with Steam used for optional store enrichment.",
                ),
                (
                    "◇ Relationship graph",
                    "helpers/media_graph.py records and retrieves linked media with provenance. Provider-confirmed relationships, provider recommendations, locally calculated genre overlap, and moderator-approved community links remain distinct. A similar title or shared genre is not proof of an adaptation.",
                ),
                (
                    "◇ PostgreSQL and server boundaries",
                    "media_relationship_graph stores deduplicated relationships and provenance. Other systems retain their existing tables, while media_assets stores object metadata rather than image bytes. Community discussions, suggestions, and server-owned resources are queried using the invoking guild ID.",
                ),
                (
                    "◇ Image storage and privacy",
                    "S3_BUCKET stores private originals such as uploaded Panels and Custom Role source images; private links use short-lived signed URLs. /panel-of-the-day reads the shared panel asset without making private originals public. Generated /3x3 grids and staff-character collages can use a separate S3_PUBLIC_BUCKET and HTTPS S3_PUBLIC_BASE_URL. Public output is disabled unless that separate destination is configured; Discord attachments remain the fallback. Never reuse the private bucket as the public bucket.",
                ),
                (
                    "◇ Errors and reporting",
                    "Provider calls use timeouts and fallbacks where implemented. Unhandled slash-command failures go through the shared private error reporter, and component failures are captured by FeedbackAwareView. Detailed exceptions stay in logs instead of chat. Report repeatable problems with /feedback, including the command, expected result, actual result, and source link.",
                ),
            ]
            for section_title, section_text in sections:
                embed.add_field(name=section_title, value=section_text[:1024], inline=False)
            embed.set_footer(text="System guide · Use /feedback to report mismatches with the running bot")
            return embed

        embed = discord.Embed(
            title=category_name,
            description=f"**{len(command_items)} commands** in this category.",
            color=PALETTE.PRIMARY if category_key == "owner" else PALETTE.SECONDARY,
        )

        for cmd_name, cmd_info in command_items.items():
            field_value = (
                f"**Description:** {cmd_info.get('desc', 'No description available.')}"
                f"\n**Usage:** `{cmd_info.get('usage', 'Not available')}`\n"
            )
            examples = cmd_info.get("examples") or []
            if examples:
                field_value += "**Examples:**\n" + "\n".join(f"  • `{example}`" for example in examples[:3]) + "\n"
            if cmd_info.get("note"):
                field_value += f"\n*{cmd_info['note']}*"
            if len(field_value) > 1000:
                field_value = field_value[:997] + "..."

            command_prefix = "!" if category_key == "owner" else "/"
            embed.add_field(
                name=(command_prefix + cmd_name)[:256],
                value=field_value,
                inline=False,
            )

        tips = self._get_category_tips(category_key)
        if tips:
            embed.add_field(name="Category Tips", value=tips[:1000], inline=False)

        avatar = getattr(getattr(self.bot, "user", None), "display_avatar", None)
        embed.set_footer(
            text="Use the category menu to continue exploring",
            icon_url=avatar.url if avatar else None,
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
                "• Use /similar for cross-provider discovery; recommendations use available provider and library data\n"
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
                "• Track GitHub commits with `/github`\n"
                "• Configure bot update channels\n"
                "• All admin commands require Bot Moderator or Admin permissions"
            ),
            "social": (
                "• Compare your anime/manga tastes with others using `/affinity`\n"
                "• View server leaderboards for activity rankings\n"
                "• Submit feedback to help improve the bot\n"
                "• Leaderboards are server-specific and update automatically"
            ),
            "community": (
                "• Archive submissions may wait for local moderator approval\n"
                "• Use /archive to check your submissions, report approved content, or review server-local queues\n"
                "• Archive reports and review actions are scoped to their originating server\n"
                "• Brackets, adaptation polls, and quiz sessions are server-specific"
            ),
            "cross_media": (
                "• Choose the exact work when a search offers a selection menu\n"
                "• Provider relationships, recommendations, and community suggestions are different evidence types\n"
                "• /link-suggest submits a proposal; moderators decide whether it is approved\n"
                "• /discovery-hub is the guided entry point for this group"
            ),
            "books": (
                "• /author-works searches Google Books by author\n"
                "• /webnovel-updates searches live Novel Updates and Novel Phoenix metadata; adult-rated entries are filtered\n"
                "• The /reading menu shows available release relationships, not assumed story chronology\n"
                "• Use /discussion and add a clear chapter/volume or episode cutoff"
            ),
            "screen": (
                "• TMDB-based commands require TMDB_BEARER_TOKEN\n"
                "• Set a default region with /media-region (Manage Server permission)\n"
                "• Provider availability can change; use its displayed source link to verify\n"
                "• Release dates and collection membership do not prove story chronology"
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


class HelpNavigationView(FeedbackAwareView):
    """Navigation view for help command with dropdown menu."""
    
    def __init__(
        self,
        help_cog: HelpCog,
        user: discord.abc.User,
        categories: dict,
        *,
        is_owner: bool = False,
    ):
        super().__init__(timeout=300)
        self.help_cog = help_cog
        self.user = user
        self.categories = categories
        self.is_owner = is_owner
        self.add_item(CategorySelect(help_cog, categories, is_owner=is_owner))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the original user to interact with the view."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                embed=build_warning_embed(
                    description="You can't use this menu. Use `/help` to get your own help interface!"
                ),
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        """Disable the expired dropdown so the message reflects its timeout state."""
        for item in self.children:
            item.disabled = True
        message = getattr(self, "message", None)
        if message is not None:
            try:
                await message.edit(view=self)
            except discord.HTTPException:
                logger.debug("Could not disable the expired help menu", exc_info=True)


class CategorySelect(discord.ui.Select):
    """Dropdown select menu for choosing help categories."""
    
    def __init__(self, help_cog: HelpCog, categories: dict, *, is_owner: bool = False):
        self.help_cog = help_cog
        self.categories = categories

        options = [
            discord.SelectOption(
                label="Overview",
                value="overview",
                description="Quick start, command totals, and support links",
                emoji="📋",
            ),
        ]
        category_options = [
            ("Account Management", "account", "Registration and account settings", "🔐"),
            ("Anime & Manga", "anime", "Browse and discover supported titles", "📺"),
            ("Gaming", "gaming", "Game metadata and Steam integration", "🎮"),
            ("Customization", "customization", "Themes and personalization", "🎨"),
            ("Server Management", "server", "Server configuration and moderation", "⚙️"),
            ("Admin", "admin", "Bot-wide administration and protected commands", "👑"),
            ("Social", "social", "Leaderboards, affinity, and feedback", "👥"),
            ("Utilities", "utilities", "Help, notifications, and everyday tools", "🛠️"),
            ("Cross-Media Discovery", "cross_media", "Adaptations, connected titles, and suggestions", "🌐"),
            ("Books & Webnovels", "books", "Author records, webnovels, and reading order", "📚"),
            ("Movies & TV", "screen", "Availability, credits, trailers, and discussions", "🎬"),
            ("Community Archives & Events", "community", "Archives, moderation, polls, and community trivia", "👥"),
            ("Code", "code", "How commands, providers, database, and storage fit together", "💻"),
        ]
        category_names_by_value = {
            "account": "🔐 Account Management",
            "anime": "📺 Anime & Manga",
            "gaming": "🎮 Gaming",
            "customization": "🎨 Customization",
            "server": "⚙️ Server Management",
            "admin": "👑 Admin",
            "social": "👥 Social",
            "utilities": "🛠️ Utilities",
            "cross_media": "🌐 Cross-Media Discovery",
            "books": "📚 Books & Webnovels",
            "screen": "🎬 Movies & TV",
            "community": "👥 Community Archives & Events",
            "code": "💻 Code",
        }
        for label, value, description, emoji in category_options:
            if value == "code" or category_names_by_value[value] in categories:
                options.append(
                    discord.SelectOption(
                        label=label,
                        value=value,
                        description=description[:100],
                        emoji=emoji,
                    )
                )

        if is_owner and "🔒 Bot Owner — Prefix Commands" in categories:
            options.append(
                discord.SelectOption(
                    label="Bot Owner Prefix Commands",
                    value="owner",
                    description="Private list of prefix commands for the bot owner",
                    emoji="🔒",
                )
            )

        super().__init__(
            placeholder="Choose a help category…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle selection from the dropdown menu."""
        
        selected_value = self.values[0]
        
        try:
            if selected_value == "overview":
                embed = await self.help_cog._create_overview_embed(interaction, self.categories)
            else:
                embed = await self.help_cog._create_category_embed(selected_value, interaction, self.categories)
            
            await interaction.response.edit_message(embed=embed, view=self.view)
            
            logger.info(f"Help category '{selected_value}' displayed for {interaction.user.display_name}")
            
        except Exception as e:
            logger.error("Error in help category selection", exc_info=True)
            await handle_component_error(
                interaction,
                e,
                component=f"help-category:{selected_value}",
                source=self,
            )


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(HelpCog(bot))
    logger.info("Help cog successfully loaded")