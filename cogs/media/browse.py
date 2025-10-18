import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import logging
from typing import List, Dict, Optional, Tuple
from discord.ui import View, Button
from database import get_all_users_guild_aware

logger = logging.getLogger("BrowseCog")
API_URL = "https://graphql.anilist.co"
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
        graphql_query = {
            "query": """
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
            """,
            "variables": {"search": query, "type": media_type}
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, json=graphql_query) as response:
                if response.status != 200:
                    logger.error(f"Failed AniList request: {response.status}")
                    return []
                data = await response.json()
                return data.get("data", {}).get("Page", {}).get("media", [])

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
                async with session.post(API_URL, json={"query": query, "variables": variables}) as resp:
                    if resp.status != 200:
                        logger.warning(f"AniList fetch failed ({resp.status}) for {anilist_username=} {media_id=}")
                        return None
                    payload = await resp.json()
        except Exception:
            logger.exception("Error requesting AniList user progress")
            return None

        user_opts = payload.get("data", {}).get("User", {}).get("mediaListOptions", {})
        score_format = user_opts.get("scoreFormat", "POINT_100")

        entry = payload.get("data", {}).get("MediaList")
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
                        await interaction.followup.send("❌ No results found.", ephemeral=True)
                        return
                    data = await response.json()
                    items = data.get("items", [])
                    if not items:
                        await interaction.followup.send("❌ No results found.", ephemeral=True)
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
            await interaction.followup.send("❌ No results found.", ephemeral=True)
            return

        media = results[0]

        # Filter by format to ensure correct media type
        if chosen_type == "MANGA_NOVEL" and media.get("format") != "NOVEL":
            await interaction.followup.send("❌ No Light Novel results found.", ephemeral=True)
            return
        elif chosen_type == "MANGA" and media.get("format") == "NOVEL":
            await interaction.followup.send("❌ No Manga results found (try Light Novel instead).", ephemeral=True)
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
                
                # Progress data (lazy-loaded in batches)
                self.all_users: Optional[List[Tuple]] = None  # All users from database
                self.loaded_user_progress: List[Dict] = []  # Users with valid progress
                self.current_batch_start = 0  # Current position in all_users
                self.batch_size = 10  # Load 10 users at a time
                self.all_data_loaded = False  # Whether we've checked all users
                self.current_progress_page = 0
                self.progress_pages: List[discord.Embed] = []
                
                self.rebuild_buttons()

            async def load_progress_data(self, load_initial_batch: bool = True):
                """Load initial batch of user progress data"""
                if self.all_users is None:
                    # Load all users from database, sorted alphabetically by anilist_username
                    self.all_users = await get_all_users_guild_aware(self.guild_id)
                    # Sort users alphabetically by anilist_username
                    self.all_users.sort(key=lambda u: (u[4] or "").lower() if len(u) >= 5 else "")
                
                if load_initial_batch:
                    await self.load_next_batch()

            async def load_next_batch(self) -> bool:
                """Load next batch of 10 users with valid progress. Returns True if more data was loaded."""
                if self.all_data_loaded:
                    return False
                
                loaded_count = 0
                initial_loaded_count = len(self.loaded_user_progress)
                
                # Process users in batches until we get 10 valid ones or run out of users
                while self.current_batch_start < len(self.all_users) and loaded_count < self.batch_size:
                    user = self.all_users[self.current_batch_start]
                    self.current_batch_start += 1
                    
                    # Expected structure: (id, discord_id, guild_id, username, anilist_username, anilist_id, ...)
                    if len(user) >= 5:
                        anilist_username = user[4]
                    else:
                        continue
                    
                    # Skip if no AniList username
                    if not anilist_username:
                        continue
                    
                    # Check if we already processed this user
                    if any(u["anilist_username"] == anilist_username for u in self.loaded_user_progress):
                        continue
                    
                    # Fetch progress for this user
                    anilist_progress = await self.bot.get_cog("BrowseCog").fetch_user_anilist_progress(
                        anilist_username, self.media_data.get("id", 0), self.real_type
                    )
                    
                    # Skip users without this media (404 or rate limit)
                    if not anilist_progress:
                        continue
                    
                    # Add valid user
                    self.loaded_user_progress.append({
                        "anilist_username": anilist_username,
                        "progress": anilist_progress.get("progress"),
                        "rating10": anilist_progress.get("rating10"),
                        "status": anilist_progress.get("status")
                    })
                    loaded_count += 1
                
                # Mark as fully loaded if we've processed all users
                if self.current_batch_start >= len(self.all_users):
                    self.all_data_loaded = True
                
                # Rebuild pagination pages with current loaded data
                self.rebuild_progress_pages()
                
                # Return True if we loaded new data
                return len(self.loaded_user_progress) > initial_loaded_count

            def rebuild_progress_pages(self):
                """Build paginated embeds from currently loaded user progress data"""
                self.progress_pages = []
                col_name = "Episodes" if self.real_type == "ANIME" else "Chapters"
                
                for page_idx in range(0, len(self.loaded_user_progress), 10):
                    page_users = self.loaded_user_progress[page_idx:page_idx + 10]
                    
                    progress_lines = [f"`{'User':<20} {col_name:<10} {'Rating':<7} {'Status':<12}`"]
                    progress_lines.append("`{:-<20} {:-<10} {:-<7} {:-<12}`".format("", "", "", ""))
                    
                    for user_data in page_users:
                        total = self.media_data.get("episodes") if self.real_type == "ANIME" else self.media_data.get("chapters")
                        progress_text = f"{user_data['progress']}/{total or '?'}" if user_data.get("progress") is not None else "—"
                        rating_text = f"{user_data['rating10']}/10" if user_data.get("rating10") is not None else "—"
                        status_text = user_data.get("status", "—")
                        
                        progress_lines.append(f"`{user_data['anilist_username']:<20} {progress_text:<10} {rating_text:<7} {status_text:<12}`")
                    
                    # Calculate page number display
                    total_pages = (len(self.loaded_user_progress) + 9) // 10
                    page_num = (page_idx // 10) + 1
                    
                    # Add loading indicator if more data might be available
                    loading_indicator = " (Loading more...)" if not self.all_data_loaded and page_idx + 10 >= len(self.loaded_user_progress) else ""
                    
                    progress_embed = discord.Embed(
                        title="👥 Registered Users' Progress",
                        description="\n".join(progress_lines),
                        color=discord.Color.blue()
                    )
                    media_title = self.media_data['title']['english'] or self.media_data['title']['romaji']
                    emoji = '🎬' if self.real_type == 'ANIME' else '📖'
                    progress_embed.set_footer(text=f"{emoji} {media_title} • Page {page_num}/{total_pages}{loading_indicator} • Fetched from AniList")
                    
                    self.progress_pages.append(progress_embed)

            def rebuild_buttons(self):
                self.clear_items()

                if self.current == "info":
                    btn = Button(
                        label="👥 User Progress",
                        style=discord.ButtonStyle.green
                    )

                    async def user_progress_callback(interaction: discord.Interaction):
                        await interaction.response.defer()
                        await self.load_progress_data(load_initial_batch=True)
                        
                        if not self.progress_pages:
                            try:
                                await interaction.followup.send("No registered users with progress for this title.", ephemeral=True)
                            except Exception:
                                pass
                            return

                        self.current = "progress"
                        self.current_progress_page = 0
                        self.rebuild_buttons()
                        await interaction.edit_original_response(embed=self.progress_pages[0], view=self)

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

                    # Previous page button
                    prev_btn = Button(
                        label="⬅️ Previous",
                        style=discord.ButtonStyle.grey,
                        disabled=(self.current_progress_page == 0)
                    )

                    async def prev_callback(interaction: discord.Interaction):
                        if self.current_progress_page > 0:
                            self.current_progress_page -= 1
                            self.rebuild_buttons()
                            await interaction.response.edit_message(
                                embed=self.progress_pages[self.current_progress_page],
                                view=self
                            )

                    prev_btn.callback = prev_callback
                    self.add_item(prev_btn)

                    # Next page button
                    next_btn = Button(
                        label="Next ➡️",
                        style=discord.ButtonStyle.grey,
                        disabled=(self.current_progress_page >= len(self.progress_pages) - 1 and self.all_data_loaded)
                    )

                    async def next_callback(interaction: discord.Interaction):
                        # Check if we're on the last page and might need to load more data
                        if self.current_progress_page >= len(self.progress_pages) - 1 and not self.all_data_loaded:
                            # Try to load next batch
                            await interaction.response.defer()
                            loaded_more = await self.load_next_batch()
                            
                            if not loaded_more and len(self.progress_pages) == 0:
                                # No more data and no pages to show
                                await interaction.followup.send("No more users found with progress for this title.", ephemeral=True)
                                return
                            elif not loaded_more:
                                # No more data but we have pages, just stay on current page
                                await interaction.followup.send("No more users found with progress for this title.", ephemeral=True)
                                return
                            else:
                                # Successfully loaded more data, update the message
                                self.rebuild_buttons()
                                await interaction.edit_original_response(embed=self.progress_pages[self.current_progress_page], view=self)
                                return
                        
                        # Normal pagination
                        if self.current_progress_page < len(self.progress_pages) - 1:
                            self.current_progress_page += 1
                            self.rebuild_buttons()
                            await interaction.response.edit_message(
                                embed=self.progress_pages[self.current_progress_page],
                                view=self
                            )

                    next_btn.callback = next_callback
                    self.add_item(next_btn)

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