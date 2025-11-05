import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from discord.ui import View, Button
from database import get_all_users_guild_aware
from helpers.embed_helper import build_error_embed, build_info_embed
from helpers.anilist_helper import post_graphql
from cogs_test.general_commands.dashboard import command_meta

logger = logging.getLogger("BrowseCog")
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes?q="

# Status order priority
STATUS_ORDER = {
    "REPEATING": 0,
    "COMPLETED": 1,
    "READING": 2,
    "PAUSED": 3,
    "DROPPED": 4,
    "PLANNING": 5,
    None: 6
}


class BrowseCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --------------------------------------------------
    # Fetch Media Info (Anime, Manga, LN)
    # --------------------------------------------------
    async def fetch_media(self, query: str, media_type: str) -> List[Dict]:
        query_str = """
        query ($search: String, $type: MediaType) {
            Page(perPage: 10) {
                media(search: $search, type: $type) {
                    id
                    title { romaji english }
                    description(asHtml: false)
                    averageScore
                    siteUrl
                    status
                    episodes
                    chapters
                    volumes
                    startDate { year month day }
                    endDate { year month day }
                    genres
                    coverImage { large medium }
                    bannerImage
                    externalLinks { site url }
                    format
                }
            }
        }
        """
        variables = {"search": query, "type": media_type}

        try:
            async with aiohttp.ClientSession() as session:
                data = await post_graphql(session, query_str, variables)
                if data is None:
                    logger.warning(f"Failed AniList request for query='{query}', type={media_type}")
                    return []
                return data.get("Page", {}).get("media", [])
        except Exception as e:
            logger.error(f"Failed AniList request: {e}", exc_info=True)
            return []

    # --------------------------------------------------
    # Fetch AniList Progress & Rating for a User
    # --------------------------------------------------
    async def fetch_user_anilist_progress(self, anilist_username: str, media_id: int, media_type: str) -> Optional[Dict]:
        if not anilist_username or not media_id:
            return None

        query = """
        query($userName: String, $mediaId: Int, $type: MediaType) {
            User(name: $userName) {
                mediaListOptions {
                    scoreFormat
                }
            }
            MediaList(userName: $userName, mediaId: $mediaId, type: $type) {
                progress
                score
                status
            }
        }
        """
        variables = {"userName": anilist_username, "mediaId": media_id, "type": media_type}

        try:
            async with aiohttp.ClientSession() as session:
                payload = await post_graphql(session, query, variables)
                if payload is None:
                    logger.warning(f"AniList fetch failed for {anilist_username=} {media_id=}")
                    return None
        except Exception as e:
            logger.exception("Error requesting AniList user progress: %s", e, exc_info=True)
            return None

        user_opts = payload.get("User", {}).get("mediaListOptions", {})
        score_format = user_opts.get("scoreFormat", "POINT_100")

        entry = payload.get("MediaList")
        if not entry:
            return None

        progress = entry.get("progress")
        score = entry.get("score")
        status = entry.get("status")

        # 📊 Normalize based on score format
        rating10: Optional[float] = None
        if score is not None:
            try:
                if score_format == "POINT_100":
                    rating10 = round(score / 10.0, 1)
                elif score_format in ("POINT_10", "POINT_10_DECIMAL"):
                    rating10 = float(score)
                elif score_format == "POINT_5":
                    rating10 = round((score / 5) * 10, 1)
                elif score_format == "POINT_3":
                    # 1=Bad, 2=Average, 3=Good → map roughly to 3, 6, 9 out of 10
                    mapping = {1: 3.0, 2: 6.0, 3: 9.0}
                    rating10 = mapping.get(score, None)
            except Exception:
                rating10 = None

        return {"progress": progress, "rating10": rating10, "status": status}

    # --------------------------------------------------
    # Fetch Page Users with Delays (Rate Limit Protection)
    # --------------------------------------------------
    async def fetch_page_users_with_delay(
        self, 
        usernames: List[str], 
        media_id: int, 
        media_type: str,
        delay: float = 0.67
    ) -> List[Dict]:
        """
        Fetch progress for multiple users sequentially with delays between requests.
        Returns list of user progress data (skips users without progress).
        """
        user_progress_list = []
        
        for username in usernames:
            if not username:
                continue
            
            # Fetch progress for this user
            anilist_progress = await self.fetch_user_anilist_progress(
                username, media_id, media_type
            )
            
            # Skip users without this media (404 or rate limit)
            if anilist_progress:
                user_progress_list.append({
                    "anilist_username": username,
                    "progress": anilist_progress.get("progress"),
                    "rating10": anilist_progress.get("rating10"),
                    "status": anilist_progress.get("status")
                })
            
            # Add delay between requests (except after the last one)
            if username != usernames[-1]:
                await asyncio.sleep(delay)
        
        return user_progress_list

    # --------------------------------------------------
    # Build Sorted User List with Progress (for pagination)
    # --------------------------------------------------
    async def build_sorted_user_progress_list(
        self, 
        users: List[Tuple], 
        media_id: int, 
        real_type: str
    ) -> List[Dict]:
        """
        Fetch progress for all users and return a sorted list.
        Sorted alphabetically by AniList username
        """
        user_progress_list = []
        processed_anilist_users = set()
        processed_discord_ids = set()

        for user in users:
            # Expected structure: (id, discord_id, guild_id, username, anilist_username, anilist_id, ...)
            if len(user) >= 5:
                discord_id = user[1]
                discord_name = user[3]
                anilist_username = user[4]
            else:
                logger.warning(f"Unexpected user row structure: {len(user)} columns")
                continue

            # Skip if no AniList username
            if not anilist_username:
                continue

            # Skip duplicates
            if anilist_username in processed_anilist_users or discord_id in processed_discord_ids:
                logger.debug(f"Skipping duplicate user: {anilist_username} (Discord ID: {discord_id})")
                continue

            anilist_progress = await self.fetch_user_anilist_progress(
                anilist_username, media_id, real_type
            )

            # Skip users without this media (404 or rate limit)
            if not anilist_progress:
                continue

            # Mark as processed
            processed_anilist_users.add(anilist_username)
            processed_discord_ids.add(discord_id)

            user_progress_list.append({
                "anilist_username": anilist_username,
                "progress": anilist_progress.get("progress"),
                "rating10": anilist_progress.get("rating10"),
                "status": anilist_progress.get("status")
            })

        # Sort alphabetically by AniList username
        user_progress_list.sort(key=lambda u: u["anilist_username"].lower())

        return user_progress_list

    # --------------------------------------------------
    # /Browse Command
    # --------------------------------------------------
    @app_commands.command(
        name="browse",
        description="Search Anime, Manga, Light Novels and General Novels"
    )
    @command_meta(section="Media", name="Browse")
    @app_commands.describe(
        media_type="Choose a media type",
        title="Choose the title"
    )
    @app_commands.choices(media_type=[
        app_commands.Choice(name="Anime", value="ANIME"),
        app_commands.Choice(name="Manga", value="MANGA"),
        app_commands.Choice(name="Light Novel", value="MANGA_NOVEL"),
        app_commands.Choice(name="General Novel", value="BOOK"),
    ])
    async def search(self, interaction: discord.Interaction, media_type: app_commands.Choice[str], title: str):
        await interaction.response.defer()

        chosen_type = media_type.value
        real_type = "MANGA" if chosen_type == "MANGA_NOVEL" else chosen_type

        if chosen_type == "BOOK":
            # 📚 Google Books Fetch
            async with aiohttp.ClientSession() as session:
                async with session.get(GOOGLE_BOOKS_URL + title) as response:
                    if response.status != 200:
                        embed = build_error_embed(
                            "No Results Found",
                            "No results found."
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
                    data = await response.json()
                    items = data.get("items", [])
                    if not items:
                        embed = build_error_embed(
                            "No Results Found",
                            "No results found."
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
                    book = items[0].get("volumeInfo", {})

            # --------------------------------------------------
            # Google Books Embed
            # --------------------------------------------------
            embed = discord.Embed(
                title=f"📚 {book.get('title', 'Unknown')}",
                url=book.get("infoLink"),
                description=book.get("description", "No description available."),
                color=discord.Color.random()
            )

            if "imageLinks" in book:
                embed.set_thumbnail(url=book["imageLinks"].get("thumbnail"))

            authors = ", ".join(book.get("authors", [])) if "authors" in book else "Unknown"
            embed.add_field(name="✍️ Authors", value=authors, inline=True)
            embed.add_field(name="📅 Published", value=book.get("publishedDate", "Unknown"), inline=True)
            embed.add_field(name="🏢 Publisher", value=book.get("publisher", "Unknown"), inline=True)
            embed.add_field(name="📄 Pages", value=book.get("pageCount", "Unknown"), inline=True)
            embed.add_field(name="⭐ Rating", value=str(book.get("averageRating", "?")) + "/5", inline=True)

            embed.set_footer(text="Fetched from Google Books")
            await interaction.followup.send(embed=embed)
            return

        # ✅ AniList Fetch
        results = await self.fetch_media(title, real_type)
        if not results:
            embed = build_error_embed(
                "No Results Found",
                "No results found."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        media = results[0]

        # Filter by format to ensure correct media type
        if chosen_type == "MANGA_NOVEL" and media.get("format") != "NOVEL":
            embed = build_error_embed(
                "No Light Novel Results",
                "No Light Novel results found."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        elif chosen_type == "MANGA" and media.get("format") == "NOVEL":
            embed = build_error_embed(
                "No Manga Results",
                "No Manga results found (try Light Novel instead)."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Format dates
        start_date = media.get("startDate", {})
        end_date = media.get("endDate", {})
        start_str = f"{start_date.get('year','?')}-{start_date.get('month','?')}-{start_date.get('day','?')}"
        end_str = (
            f"{end_date.get('year','?')}-{end_date.get('month','?')}-{end_date.get('day','?')}"
            if end_date else "Ongoing"
        )

        # Description
        raw_description = media.get("description") or "No description available."
        description = raw_description[:400] + "..." if len(raw_description) > 400 else raw_description
        genres = ", ".join(media.get("genres", [])) or "Unknown"

        # --------------------------------------------------
        # AniList Embed
        # --------------------------------------------------
        embed = discord.Embed(
            title=f"{'🎬' if real_type=='ANIME' else '📖'} {media['title']['english'] or media['title']['romaji']}",
            url=media["siteUrl"],
            description=description,
            color=discord.Color.random()
        )

        cover_url = media.get("coverImage", {}).get("medium") or media.get("coverImage", {}).get("large")
        if cover_url:
            embed.set_thumbnail(url=cover_url)

        banner_url = media.get("bannerImage")
        if banner_url:
            embed.set_image(url=banner_url)

        embed.add_field(name="⭐ Average Score", value=f"{media.get('averageScore', 'N/A')}%", inline=True)
        embed.add_field(name="📌 Status", value=media.get("status", "Unknown"), inline=True)

        if real_type == "ANIME":
            embed.add_field(name="📺 Episodes", value=media.get("episodes", '?'), inline=True)
        else:
            embed.add_field(name="📖 Chapters", value=media.get("chapters", '?'), inline=True)
            embed.add_field(name="📚 Volumes", value=media.get("volumes", '?'), inline=True)

        embed.add_field(name="🎭 Genres", value=genres, inline=False)
        embed.add_field(name="📅 Published", value=f"**Start:** {start_str}\n**End:** {end_str}", inline=False)

        mal_link = None
        for link in media.get("externalLinks", []):
            if link.get("site") == "MyAnimeList":
                mal_link = link.get("url")
                break
        if mal_link:
            embed.add_field(name="🔗 MyAnimeList", value=f"[View on MAL]({mal_link})", inline=False)

        embed.set_footer(text="Fetched from AniList")

        # --------------------------------------------------
        # PageView with Lazy-Loading
        # --------------------------------------------------
        class PageView(View):
            def __init__(self, embed1, media_data, real_type_val, guild_id, bot):
                super().__init__(timeout=300)
                self.embed1 = embed1
                self.media_data = media_data
                self.real_type = real_type_val
                self.guild_id = guild_id
                self.bot = bot
                self.current = "info"
                
                # Progress data (continuous loading)
                self.all_users: Optional[List[Tuple]] = None  # All users from database (sorted)
                self.loaded_user_progress: List[Dict] = []  # Continuous list of all loaded users with progress
                self.processed_usernames: set = set()  # Track all usernames we've attempted to fetch
                self.current_batch_start = 0  # Current position in all_users
                self.batch_size = 10  # Load 10 users at a time
                self.is_loading = False  # Track if currently loading
                
                self.rebuild_buttons()

            async def load_user_list(self):
                """Load all users from database, sorted alphabetically"""
                if self.all_users is None:
                    self.all_users = await get_all_users_guild_aware(self.guild_id)
                    # Sort users alphabetically by anilist_username
                    self.all_users.sort(key=lambda u: (u[4] or "").lower() if len(u) >= 5 else "")
                return self.all_users

            def get_next_batch_usernames(self) -> List[str]:
                """Get list of AniList usernames for the next batch to load"""
                if self.all_users is None:
                    return []
                
                usernames = []
                
                # Start from current_batch_start and get next batch_size users we haven't processed
                idx = self.current_batch_start
                
                while idx < len(self.all_users) and len(usernames) < self.batch_size:
                    user = self.all_users[idx]
                    # Expected structure: (id, discord_id, guild_id, username, anilist_username, anilist_id, ...)
                    if len(user) >= 5:
                        anilist_username = user[4]
                        if anilist_username and anilist_username not in self.processed_usernames:
                            usernames.append(anilist_username)
                    idx += 1
                
                return usernames

            def has_more_users(self) -> bool:
                """Check if there are more users to load"""
                if self.all_users is None:
                    return False
                return self.current_batch_start < len(self.all_users)

            async def load_next_batch(self) -> bool:
                """Load next batch of users and append to loaded_user_progress. Returns True if data was loaded."""
                if self.is_loading or not self.has_more_users():
                    return False
                
                self.is_loading = True
                
                try:
                    # Get usernames for next batch
                    usernames = self.get_next_batch_usernames()
                    
                    if not usernames:
                        # No more users to process
                        return False
                    
                    # Fetch progress with delays (0.67s)
                    browse_cog = self.bot.get_cog("BrowseCog")
                    user_progress = await browse_cog.fetch_page_users_with_delay(
                        usernames,
                        self.media_data.get("id", 0),
                        self.real_type,
                        delay=0.67
                    )
                    
                    # Mark all usernames as processed (even if they didn't have progress)
                    self.processed_usernames.update(usernames)
                    
                    # Append to continuous list
                    self.loaded_user_progress.extend(user_progress)
                    
                    # Update current_batch_start: advance past all users we just processed
                    # Find the next user that hasn't been processed yet
                    while self.current_batch_start < len(self.all_users):
                        user = self.all_users[self.current_batch_start]
                        if len(user) >= 5:
                            anilist_username = user[4]
                            if anilist_username:
                                if anilist_username in self.processed_usernames:
                                    self.current_batch_start += 1
                                    continue
                                else:
                                    # Found next unprocessed user
                                    break
                        self.current_batch_start += 1
                    
                    return len(user_progress) > 0
                finally:
                    self.is_loading = False

            def build_progress_embed(self) -> discord.Embed:
                """Build embed showing all loaded users"""
                col_name = "Episodes" if self.real_type == "ANIME" else "Chapters"
                
                progress_lines = [f"`{'User':<20} {col_name:<10} {'Rating':<7} {'Status':<12}`"]
                progress_lines.append("`{:-<20} {:-<10} {:-<7} {:-<12}`".format("", "", "", ""))
                
                if not self.loaded_user_progress:
                    progress_lines.append("`No users with progress found.`")
                else:
                    for user_data in self.loaded_user_progress:
                        total = self.media_data.get("episodes") if self.real_type == "ANIME" else self.media_data.get("chapters")
                        progress_text = f"{user_data['progress']}/{total or '?'}" if user_data.get("progress") is not None else "—"
                        rating_text = f"{user_data['rating10']}/10" if user_data.get("rating10") is not None else "—"
                        status_text = user_data.get("status", "—")
                        
                        progress_lines.append(f"`{user_data['anilist_username']:<20} {progress_text:<10} {rating_text:<7} {status_text:<12}`")
                
                # Check if description is too long (Discord limit is 4096 chars)
                description_text = "\n".join(progress_lines)
                if len(description_text) > 4096:
                    # Truncate but keep header
                    header = "\n".join(progress_lines[:2])
                    truncated = "\n".join(progress_lines[2:])
                    # Keep as many users as fit
                    max_chars = 4096 - len(header) - 50  # 50 chars buffer
                    lines = truncated.split("\n")
                    truncated_lines = []
                    for line in lines:
                        if len("\n".join(truncated_lines) + "\n" + line) > max_chars:
                            break
                        truncated_lines.append(line)
                    description_text = header + "\n" + "\n".join(truncated_lines) + "\n`... (truncated, use Load More to see more)`"
                
                progress_embed = discord.Embed(
                    title="👥 Registered Users' Progress",
                    description=description_text,
                    color=discord.Color.blue()
                )
                media_title = self.media_data['title']['english'] or self.media_data['title']['romaji']
                emoji = '🎬' if self.real_type == 'ANIME' else '📖'
                checked_count = len(self.processed_usernames)
                total_users = len(self.all_users) if self.all_users else 0
                footer_text = f"{emoji} {media_title} • {len(self.loaded_user_progress)} users loaded • {checked_count}/{total_users} database users checked"
                if self.has_more_users():
                    footer_text += " • Fetched from AniList"
                else:
                    footer_text += " • All users loaded • Fetched from AniList"
                progress_embed.set_footer(text=footer_text)
                
                return progress_embed

            def rebuild_buttons(self):
                self.clear_items()

                if self.current == "info":
                    btn = Button(
                        label="👥 User Progress",
                        style=discord.ButtonStyle.green
                    )

                    async def user_progress_callback(interaction: discord.Interaction):
                        await interaction.response.defer()
                        
                        # Load user list first
                        await self.load_user_list()
                        
                        if not self.all_users or len(self.all_users) == 0:
                            try:
                                embed = build_info_embed(
                                    "No Users Found",
                                    "No registered users found."
                                )
                                await interaction.followup.send(embed=embed, ephemeral=True)
                            except Exception:
                                pass
                            return

                        # Switch to progress view
                        self.current = "progress"
                        
                        # Show loading message
                        loading_embed = discord.Embed(
                            title="👥 Registered Users' Progress",
                            description="Loading user progress... This may take ~7 seconds.",
                            color=discord.Color.blue()
                        )
                        try:
                            await interaction.edit_original_response(embed=loading_embed, view=self)
                        except Exception:
                            pass
                        
                        # Load first batch
                        await self.load_next_batch()
                        embed = self.build_progress_embed()
                        
                        self.rebuild_buttons()
                        try:
                            await interaction.edit_original_response(embed=embed, view=self)
                        except Exception:
                            pass

                    btn.callback = user_progress_callback
                    self.add_item(btn)

                elif self.current == "progress":
                    # Back button
                    back_btn = Button(
                        label="📖 Media Info",
                        style=discord.ButtonStyle.blurple
                    )

                    async def media_info_callback(interaction: discord.Interaction):
                        self.current = "info"
                        self.rebuild_buttons()
                        await interaction.response.edit_message(embed=self.embed1, view=self)

                    back_btn.callback = media_info_callback
                    self.add_item(back_btn)

                    # Load More button
                    load_more_btn = Button(
                        label="Load More ➕",
                        style=discord.ButtonStyle.green,
                        disabled=(not self.has_more_users() or self.is_loading)
                    )

                    async def load_more_callback(interaction: discord.Interaction):
                        if not self.has_more_users() or self.is_loading:
                            embed = build_info_embed(
                                "Cannot Load More",
                                "No more users to load or already loading."
                            )
                            await interaction.response.send_message(embed=embed, ephemeral=True)
                            return
                        
                        # Show loading message
                        await interaction.response.defer()
                        loading_embed = discord.Embed(
                            title="👥 Registered Users' Progress",
                            description="Loading more users... This may take ~7 seconds.",
                            color=discord.Color.blue()
                        )
                        try:
                            await interaction.edit_original_response(embed=loading_embed, view=self)
                        except Exception:
                            pass
                        
                        # Load next batch
                        loaded = await self.load_next_batch()
                        
                        if loaded:
                            embed = self.build_progress_embed()
                            self.rebuild_buttons()
                            try:
                                await interaction.edit_original_response(embed=embed, view=self)
                            except Exception:
                                pass
                        else:
                            # No more users loaded
                            embed = self.build_progress_embed()
                            self.rebuild_buttons()
                            try:
                                await interaction.edit_original_response(embed=embed, view=self)
                            except Exception:
                                pass

                    load_more_btn.callback = load_more_callback
                    self.add_item(load_more_btn)

            async def on_timeout(self):
                self.clear_items()

        # Start with media info; always include the view so buttons are visible
        view = PageView(embed, media, real_type, interaction.guild_id, self.bot)
        await interaction.followup.send(embed=embed, view=view)


    # --------------------------------------------------
    # Autocomplete
    # --------------------------------------------------
    @search.autocomplete("title")
    async def autocomplete_search(self, interaction: discord.Interaction, current: str):
        if len(current) < 2:
            return []

        media_type = getattr(interaction.namespace, "media_type", None)
        choices = []

        if media_type == "BOOK":
            async with aiohttp.ClientSession() as session:
                async with session.get(GOOGLE_BOOKS_URL + current) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    for item in data.get("items", [])[:10]:
                        info = item.get("volumeInfo", {})
                        title = info.get("title", "Unknown")[:100]
                        choices.append(app_commands.Choice(name=title, value=title))
        else:
            search_type = "MANGA" if media_type in ("MANGA", "MANGA_NOVEL") else "ANIME"
            results = await self.fetch_media(current, search_type)
            for media in results[:10]:
                title = media["title"].get("romaji") or media["title"].get("english") or "Unknown"
                title = title[:100]
                choices.append(app_commands.Choice(name=title, value=title))

        return choices


async def setup(bot: commands.Bot):
    await bot.add_cog(BrowseCog(bot))