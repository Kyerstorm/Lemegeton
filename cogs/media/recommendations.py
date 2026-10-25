from helpers.color_palette import PALETTE
import discord
from helpers.command_error_handler import application_error_message, FeedbackAwareView
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import logging
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime, timedelta
import time
from helpers.embed_helper import build_error_embed, build_warning_embed, build_info_embed, build_success_embed
from helpers.anilist_helper import post_graphql
from cogs_test.general_commands.dashboard import command_meta

# ------------------------------------------------------
# RECOMMENDATIONS COG LOGGING SETUP
# ------------------------------------------------------
logger = logging.getLogger('recommendations')
logger.setLevel(logging.INFO)

# Create logs directory if it doesn't exist
import os
if not os.path.exists('logs'):
    os.makedirs('logs')

# File handler for recommendations log
file_handler = logging.FileHandler('logs/recommendations.log')
file_handler.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Formatters
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(funcName)s:%(lineno)d - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to logger
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

logger.info("Recommendations cog logging initialized")

# ------------------------------------------------------
# CACHING SYSTEM
# ------------------------------------------------------
# Cache keys include guild, user, AniList account, and media category.
recommendations_cache = {}

# ------------------------------------------------------
# ANILIST API CONFIGURATION
# ------------------------------------------------------
# API URL is now handled by helpers.anilist_helper

# GraphQL query to fetch user's manga list
USER_MANGA_LIST_QUERY = """
query ($userName: String, $type: MediaType) {
    MediaListCollection(userName: $userName, type: $type) {
        lists {
            name
            status
            entries {
                id
                status
                score(format: POINT_10)
                media {
                    id
                    title {
                        romaji
                        english
                    }
                    format
                    status
                    averageScore
                    countryOfOrigin
                    recommendations(perPage: 25) {
                        nodes {
                            rating
                            mediaRecommendation {
                                id
                                title {
                                    romaji
                                    english
                                }
                                format
                                status
                                averageScore
                                countryOfOrigin
                                coverImage {
                                    large
                                }
                                genres
                                description
                                startDate {
                                    year
                                }
                                chapters
                                volumes
                                episodes
                            }
                        }
                    }
                }
            }
        }
    }
}
"""

# GraphQL query to fetch detailed media info for final results
MEDIA_DETAILS_QUERY = """
query ($id: Int) {
    Media(id: $id) {
        id
        title {
            romaji
            english
        }
        format
        status
        averageScore
        coverImage {
            large
        }
        genres
        description
        startDate {
            year
        }
        chapters
        volumes
        staff {
            nodes {
                name {
                    full
                }
                primaryOccupations
            }
        }
    }
}
"""

# ------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------
def normalize_score(score: float, score_format: str = "POINT_10") -> float:
    """Normalize different scoring systems to a 0-10 scale."""
    if score is None or score == 0:
        return 0.0
    
    if score_format == "POINT_100":
        return score / 10.0
    elif score_format == "POINT_10_DECIMAL":
        return score
    elif score_format == "POINT_5":
        return score * 2.0
    elif score_format == "POINT_3":
        return (score * 10.0) / 3.0
    else:  # POINT_10 or default
        return float(score)

def get_format_category(format_type: str, country_of_origin: str = None) -> str:
    """Categorize AniList manga-like formats using format and country of origin."""
    if format_type == "NOVEL":
        return "light_novels"
    # Use country of origin for more accurate categorization
    if country_of_origin:
        if country_of_origin == "KR":  # South Korea
            return "manhwa"
        elif country_of_origin == "CN":  # China
            return "manhua"
        elif country_of_origin == "JP":  # Japan
            return "manga"
    
    # Fallback to format-based categorization
    if format_type in ["MANGA", "ONE_SHOT"]:
        return "manga"
    elif format_type in ["MANHWA"]:
        return "manhwa"
    elif format_type in ["MANHUA"]:
        return "manhua"
    else:
        return "manga"  # Default fallback

def truncate_description(description: str, max_length: int = 200) -> str:
    """Truncate description to fit in embed."""
    if not description:
        return "No description available."
    
    # Remove HTML tags
    import re
    clean_desc = re.sub('<.*?>', '', description)
    
    if len(clean_desc) <= max_length:
        return clean_desc
    
    return clean_desc[:max_length-3] + "..."

# ------------------------------------------------------
# PAGINATION VIEW CLASS - ONE TITLE PER PAGE
# ------------------------------------------------------
class RecommendationsView(FeedbackAwareView):
    def __init__(
        self, user_id: int, recommendations_data: Dict[str, List],
        username: str, media_type: str = "MANGA",
    ):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.recommendations_data = recommendations_data
        self.username = username
        self.media_type = media_type
        self.current_category = "anime" if media_type == "ANIME" else "manga"
        self.current_index = 0
        self.embeds_cache = {}
        category_order = (
            ["anime"] if media_type == "ANIME"
            else ["light_novels"] if media_type == "LIGHT_NOVEL"
            else ["manga", "manhwa", "manhua", "light_novels"]
        )
        for category in category_order:
            if recommendations_data.get(category):
                self.current_category = category
                break
        
        # Update button states
        self.update_button_states()
        
        logger.info(f"Initialized recommendations view for user {user_id} with {len(recommendations_data)} categories")

    def update_button_states(self):
        """Update button styles and states based on current page."""
        self.clear_items()
        
        if self.media_type == "ANIME":
            categories = [("anime", "Anime", "🎬", self.manga_button_callback)]
        elif self.media_type == "LIGHT_NOVEL":
            categories = [("light_novels", "Light Novels", "📚", self.light_novel_button_callback)]
        else:
            categories = [
                ("manga", "Manga", "📖", self.manga_button_callback),
                ("manhwa", "Manhwa", "🇰🇷", self.manhwa_button_callback),
                ("manhua", "Manhua", "🇨🇳", self.manhua_button_callback),
                ("light_novels", "Light Novels", "📚", self.light_novel_button_callback),
            ]
        for category, label, emoji, callback in categories:
            button = discord.ui.Button(
                label=label,
                custom_id=category,
                style=discord.ButtonStyle.primary if self.current_category == category else discord.ButtonStyle.secondary,
                emoji=emoji,
                disabled=not self.recommendations_data.get(category),
            )
            button.callback = callback
            self.add_item(button)
        
        # Navigation buttons (second row)
        current_recs = self.recommendations_data.get(self.current_category, [])
        total_count = len(current_recs)
        
        if total_count > 1:
            # Previous button
            prev_button = discord.ui.Button(
                label="◀️ Previous",
                style=discord.ButtonStyle.gray,
                disabled=self.current_index == 0,
                row=1
            )
            prev_button.callback = self.previous_callback
            self.add_item(prev_button)
            
            # Page indicator button (non-clickable)
            page_button = discord.ui.Button(
                label=f"{self.current_index + 1}/{total_count}",
                style=discord.ButtonStyle.gray,
                disabled=True,
                row=1
            )
            self.add_item(page_button)
            
            # Next button
            next_button = discord.ui.Button(
                label="Next ▶️",
                style=discord.ButtonStyle.gray,
                disabled=self.current_index >= total_count - 1,
                row=1
            )
            next_button.callback = self.next_callback
            self.add_item(next_button)

    async def create_embed(self) -> discord.Embed:
        """Create detailed embed for current recommendation."""
        current_recs = self.recommendations_data.get(self.current_category, [])
        if not current_recs or self.current_index >= len(current_recs):
            return build_error_embed(
                "No Recommendations",
                f"No {self.current_category} recommendations found."
            )
        
        rec = current_recs[self.current_index]
        media = rec['media']
        vote_count = rec['vote_count']
        
        title_data = media.get("title") or {}
        title = title_data.get("english") or title_data.get("romaji") or title_data.get("native") or "Unknown title"
        is_anime = self.current_category == "anime"
        media_path = "anime" if is_anime else "manga"
        media_icon = "🎬" if is_anime else ("📚" if self.current_category == "light_novels" else "📖")
        embed = discord.Embed(
            title=f"{media_icon} {title}",
            url=f"https://anilist.co/{media_path}/{media['id']}",
            description=truncate_description(media.get('description', ''), 300),
            color=PALETTE.PRIMARY
        )
        
        # Set thumbnail if available
        cover_url = (media.get("coverImage") or {}).get("large")
        if cover_url:
            embed.set_thumbnail(url=cover_url)
        
        # Add fields similar to browse.py
        embed.add_field(
            name="⭐ Average Score", 
            value=f"{media['averageScore']}/100" if media.get('averageScore') is not None else "N/A", 
            inline=True
        )
        
        embed.add_field(
            name="📌 Status", 
            value=(media.get("status") or "Unknown").replace("_", " ").title(),
            inline=True
        )
        
        embed.add_field(
            name="👥 Recommendation Votes", 
            value=f"{vote_count} votes", 
            inline=True
        )
        
        if is_anime:
            if media.get("episodes") is not None:
                embed.add_field(name="📺 Episodes", value=str(media["episodes"]), inline=True)
        else:
            if media.get("chapters") is not None:
                embed.add_field(name="📖 Chapters", value=str(media["chapters"]), inline=True)
            if media.get("volumes") is not None:
                embed.add_field(name="📚 Volumes", value=str(media["volumes"]), inline=True)
        
        # Format
        format_type = media.get('format', '').replace('_', ' ').title()
        if format_type:
            embed.add_field(name="📋 Format", value=format_type, inline=True)
        
        # Genres
        genres = media.get('genres', [])
        if genres:
            genre_text = ', '.join(genres[:5])  # Limit to 5 genres
            if len(genres) > 5:
                genre_text += f" +{len(genres) - 5} more"
            embed.add_field(name="� Genres", value=genre_text, inline=False)
        
        # Start date
        start_date = media.get('startDate', {})
        if start_date and start_date.get('year'):
            embed.add_field(
                name="📅 Start Date", 
                value=f"{start_date.get('year', '?')}", 
                inline=True
            )
        
        # Footer with page info
        total_recs = len(current_recs)
        embed.set_footer(
            text=f"{self.current_category.title()} Recommendation {self.current_index + 1}/{total_recs} • Recommended for {self.username}",
            icon_url="https://anilist.co/img/icons/android-chrome-512x512.png"
        )
        
        logger.info(f"Created embed for {title} (index {self.current_index}/{total_recs})")
        return embed

    async def manga_button_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "This menu is not for you!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            await interaction.response.defer()
            
            self.current_category = "anime" if self.media_type == "ANIME" else "manga"
            self.current_index = 0
            self.update_button_states()
            
            embed = await self.create_embed()
            await interaction.edit_original_response(embed=embed, view=self)
            
            logger.info(f"User {self.user_id} switched to manga recommendations")
        except Exception as e:
            logger.error(f"Error in manga_button_callback: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    application_error_message(e)
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

    async def manhwa_button_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "This menu is not for you!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            await interaction.response.defer()
            
            self.current_category = "manhwa"
            self.current_index = 0
            self.update_button_states()
            
            embed = await self.create_embed()
            await interaction.edit_original_response(embed=embed, view=self)
            
            logger.info(f"User {self.user_id} switched to manhwa recommendations")
        except Exception as e:
            logger.error(f"Error in manhwa_button_callback: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    application_error_message(e)
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

    async def manhua_button_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "This menu is not for you!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            await interaction.response.defer()
            
            self.current_category = "manhua"
            self.current_index = 0
            self.update_button_states()
            
            embed = await self.create_embed()
            await interaction.edit_original_response(embed=embed, view=self)
            
            logger.info(f"User {self.user_id} switched to manhua recommendations")
        except Exception as e:
            logger.error(f"Error in manhua_button_callback: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    "An error occurred while switching categories. Please try again."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

    async def light_novel_button_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                embed=build_error_embed("Permission Denied", "This menu is not for you!"),
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        self.current_category = "light_novels"
        self.current_index = 0
        self.update_button_states()
        embed = await self.create_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    async def previous_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "This menu is not for you!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            await interaction.response.defer()
            
            if self.current_index > 0:
                self.current_index -= 1
                self.update_button_states()
                
                embed = await self.create_embed()
                await interaction.edit_original_response(embed=embed, view=self)
                
                logger.info(f"User {self.user_id} went to previous recommendation (index {self.current_index})")
        except Exception as e:
            logger.error(f"Error in previous_callback: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    application_error_message(e)
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "This menu is not for you!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            await interaction.response.defer()
            
            current_recs = self.recommendations_data.get(self.current_category, [])
            if self.current_index < len(current_recs) - 1:
                self.current_index += 1
                self.update_button_states()
                
                embed = await self.create_embed()
                await interaction.edit_original_response(embed=embed, view=self)
                
                logger.info(f"User {self.user_id} went to next recommendation (index {self.current_index})")
        except Exception as e:
            logger.error(f"Error in next_callback: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    application_error_message(e)
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

    async def on_timeout(self):
        """Handle view timeout."""
        for item in self.children:
            item.disabled = True
        logger.info(f"Recommendations view timed out for user {self.user_id}")

# ------------------------------------------------------
# MAIN RECOMMENDATIONS COG
# ------------------------------------------------------
class RecommendationsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Recommendations cog initialized")
    
    def get_cached_recommendations(
        self, guild_id: Optional[int], user_id: int, username: str, media_type: str,
    ) -> Optional[Tuple[Dict[str, List], str]]:
        """Read cache scoped by guild, user, AniList account, and media category."""
        cache_key = (guild_id, user_id, username.casefold(), media_type)
        if cache_key not in recommendations_cache:
            return None
        cache_entry = recommendations_cache[cache_key]
        cache_time = cache_entry["timestamp"]
        
        # Check if cache is less than 24 hours old
        if time.time() - cache_time < 86400:  # 24 hours in seconds
            logger.info(f"Using cached recommendations for user {user_id}")
            return cache_entry["data"], cache_entry["username"]
        else:
            # Remove expired cache
            del recommendations_cache[cache_key]
            logger.info("Expired recommendations for user %s in guild %s", user_id, guild_id)
            return None
    
    def cache_recommendations(
        self, guild_id: Optional[int], user_id: int, username: str,
        media_type: str, recommendations_data: Dict[str, List],
    ):
        """Cache results with guild, AniList account, and category isolation."""
        cache_key = (guild_id, user_id, username.casefold(), media_type)
        recommendations_cache[cache_key] = {
            "data": recommendations_data,
            "timestamp": time.time(),
            "username": username,
        }
        logger.info("Cached %s recommendations for user %s in guild %s", media_type, user_id, guild_id)

    async def fetch_user_manga_list(self, username: str, media_type: str = "MANGA") -> Tuple[List[Dict], set]:
        """Fetch a user's AniList list for the chosen supported media category."""
        logger.info("Fetching %s list for AniList user %s", media_type, username)

        variables = {
            "userName": username,
            "type": media_type,
        }
        
        async with aiohttp.ClientSession() as session:
            data = await post_graphql(session, USER_MANGA_LIST_QUERY, variables)
            if data is None:
                logger.error("AniList API returned None for manga list query")
                raise Exception("AniList API returned None")
            
            manga_list = []
            user_media_ids = set()
            
            if data.get("MediaListCollection", {}).get("lists"):
                for manga_list_entry in data["MediaListCollection"]["lists"]:
                    for entry in manga_list_entry.get("entries", []):
                        media = entry.get("media", {})
                        media_id = media.get("id")
                        
                        if media_id:
                            user_media_ids.add(media_id)
                        
                        # Exclude planning status from recommendation sources (unrated/incomplete)
                        if entry.get("status") != "PLANNING":
                            manga_list.append(entry)
            
            logger.info("Retrieved %s %s entries (excluding planning)", len(manga_list), media_type.lower())
            logger.info(f"User has {len(user_media_ids)} total media IDs in their list")
            return manga_list, user_media_ids

    def filter_high_rated_manga(self, manga_list: List[Dict]) -> List[Dict]:
        """Filter manga with scores >= 7/10 (normalized from various scoring systems)."""
        logger.info("Filtering manga with scores >= 7/10")
        
        filtered_manga = []
        for entry in manga_list:
            raw_score = entry.get("score", 0)
            if raw_score and raw_score > 0:
                # The GraphQL query uses score(format: POINT_10) which normalizes to 10-point scale
                # But let's be extra safe and handle other formats if they slip through
                normalized_score = normalize_score(raw_score, "POINT_10")
                if normalized_score >= 7.0:
                    filtered_manga.append(entry)
                    logger.debug(f"Included manga with score {raw_score} (normalized: {normalized_score})")
        
        logger.info(f"Filtered to {len(filtered_manga)} highly-rated manga (score >= 7.0)")
        return filtered_manga

    def extract_recommendations(
        self, manga_list: List[Dict], user_media_ids: set, media_type: str = "MANGA",
    ) -> Dict[str, List]:
        """Extract provider recommendations by requested media type, excluding seen list entries."""
        if media_type == "ANIME":
            category_names = ["anime"]
        elif media_type == "LIGHT_NOVEL":
            category_names = ["light_novels"]
        else:
            category_names = ["manga", "manhwa", "manhua", "light_novels"]
        recommendations_by_category = {
            category: defaultdict(lambda: {"max_rating": 0, "occurrences": 0, "media": None})
            for category in category_names
        }
        
        excluded_count = 0
        
        for entry in manga_list:
            media = entry.get("media", {})
            recommendations = media.get("recommendations", {}).get("nodes", [])
            
            for rec in recommendations:
                rec_media = rec.get("mediaRecommendation")
                if not rec_media:
                    continue
                    
                # Allow planning titles in final results (user might want to read them)
                rec_status = rec_media.get("status")
                if rec_status not in ["RELEASING", "FINISHED", "NOT_YET_RELEASED"]:
                    continue
                
                media_id = rec_media.get("id")
                if not media_id:
                    continue
                
                # Skip if user already has this title in their list
                if media_id in user_media_ids:
                    excluded_count += 1
                    continue
                
                format_type = rec_media.get("format", "MANGA")
                if media_type == "LIGHT_NOVEL" and format_type != "NOVEL":
                    continue
                country_of_origin = rec_media.get("countryOfOrigin")
                category = (
                    "anime" if media_type == "ANIME"
                    else "light_novels" if media_type == "LIGHT_NOVEL"
                    else get_format_category(format_type, country_of_origin)
                )
                
                # Get AniList recommendation rating (upvotes)
                recommendation_rating = rec.get("rating", 0) or 0
                
                # Track both max rating and occurrence count
                current_entry = recommendations_by_category[category][media_id]
                
                # Update max rating if this recommendation has higher rating
                if recommendation_rating > current_entry["max_rating"]:
                    current_entry["max_rating"] = recommendation_rating
                    current_entry["media"] = rec_media
                elif current_entry["media"] is None:
                    current_entry["media"] = rec_media
                
                # Always increment occurrence count
                current_entry["occurrences"] += 1
        
        logger.info(
            "Extracted recommendation candidates by category: %s",
            {category: len(entries) for category, entries in recommendations_by_category.items()},
        )
        logger.info(f"Excluded {excluded_count} recommendations already in user's list")
        logger.info("Tracking both AniList ratings and occurrence counts for filtering")
        
        return recommendations_by_category

    def filter_and_rank_recommendations(
        self, recommendations_by_category: Dict, genre: Optional[str] = None,
        year_from: Optional[int] = None, year_to: Optional[int] = None,
    ) -> Dict[str, List]:
        """Filter by real candidate metadata, then rank AniList's recommendation signals."""
        logger.info("Filtering recommendations with occurrence >=3 AND rating >=3")
        
        final_recommendations = {}
        
        for category, rec_dict in recommendations_by_category.items():
            # Double filter: occurrence >=3 AND rating >=3
            filtered_recs = {}
            for media_id, data in rec_dict.items():
                media = data.get("media") or {}
                if data["occurrences"] < 3 or data["max_rating"] < 3:
                    continue
                if genre and not any(
                    genre.casefold() in str(value).casefold()
                    for value in (media.get("genres") or [])
                ):
                    continue
                raw_year = (media.get("startDate") or {}).get("year")
                if year_from is not None or year_to is not None:
                    if not isinstance(raw_year, int):
                        continue
                    if year_from is not None and raw_year < year_from:
                        continue
                    if year_to is not None and raw_year > year_to:
                        continue
                filtered_recs[media_id] = data
            
            # Create list with media details and ratings
            rec_list = []
            for media_id, data in filtered_recs.items():
                if data["media"]:
                    rec_list.append({
                        "media": data["media"],
                        "vote_count": data["max_rating"],  # Display AniList rating as vote count
                        "occurrences": data["occurrences"]  # Track how many different manga recommended it
                    })
            
            # Sort by rating (descending), then by occurrences (descending), then by average score
            rec_list.sort(key=lambda x: (
                x["vote_count"], 
                x["occurrences"], 
                x["media"].get("averageScore") or 0
            ), reverse=True)
            
            final_recommendations[category] = rec_list[:10]  # Top 10 for each category
            
            logger.info(f"Category {category}: {len(filtered_recs)} recommendations "
                       f"(occurrence >=3 AND rating >=3), top {len(final_recommendations[category])} selected")
        
        return final_recommendations

    @app_commands.command(name="recommendations", description="Get AniList recommendations for anime, manga, or light novels")
    @command_meta(section="Media", name="Recommendations")
    @app_commands.describe(
        username="AniList username (optional, uses your linked account if not provided)",
        media_type="AniList category to recommend",
        genre="Optional genre name filter",
        year_from="Earliest release year",
        year_to="Latest release year",
    )
    @app_commands.choices(media_type=[
        app_commands.Choice(name="Manga (including manhwa/manhua)", value="MANGA"),
        app_commands.Choice(name="Anime", value="ANIME"),
        app_commands.Choice(name="Light Novels", value="LIGHT_NOVEL"),
    ])
    async def recommendations(
        self, interaction: discord.Interaction, username: Optional[str] = None,
        media_type: Optional[app_commands.Choice[str]] = None, genre: Optional[str] = None,
        year_from: Optional[int] = None, year_to: Optional[int] = None,
    ):
        """Generate recommendations based on AniList's native recommendation graph."""
        selected_type = media_type.value if media_type else "MANGA"
        api_type = "MANGA" if selected_type == "LIGHT_NOVEL" else selected_type
        genre = " ".join((genre or "").split()) or None
        if year_from is not None and not 1900 <= year_from <= 2100:
            return await interaction.response.send_message(
                embed=build_error_embed("Invalid Year", "year_from must be between 1900 and 2100."),
                ephemeral=True,
            )
        if year_to is not None and not 1900 <= year_to <= 2100:
            return await interaction.response.send_message(
                embed=build_error_embed("Invalid Year", "year_to must be between 1900 and 2100."),
                ephemeral=True,
            )
        if year_from is not None and year_to is not None and year_from > year_to:
            return await interaction.response.send_message(
                embed=build_error_embed("Invalid Year Range", "year_from cannot be later than year_to."),
                ephemeral=True,
            )
        logger.info("Recommendations requested by %s for %s", interaction.user.id, selected_type)
        
        # Defer the response as this will take time
        await interaction.response.defer()
        
        try:
            # Get username
            if not username:
                # Import database functions to get linked username
                try:
                    import sys
                    import os
                    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                    from database import get_user_guild_aware
                    
                    user_data = await get_user_guild_aware(interaction.user.id, interaction.guild_id)
                    db_username = user_data[4] if user_data else None  # anilist_username is at index 4
                    if not db_username:
                        embed = build_error_embed(
                            "No Username Found",
                            "No AniList username provided and no linked account found. Please provide a username or link your account with `/login`."
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
                    username = db_username
                    logger.info(f"Retrieved username '{username}' from database for user {interaction.user.id}")
                except Exception as e:
                    logger.error(f"Error retrieving username from database: {e}", exc_info=True)
                    embed = build_error_embed(
                        "Database Error",
                        "Automatic username lookup failed. You can enter an AniList username manually.\n\n" + application_error_message(e)
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
            
            # Check cache first
            cached_data = None
            if not genre and year_from is None and year_to is None:
                cached_data = self.get_cached_recommendations(
                    interaction.guild_id, interaction.user.id, username, selected_type,
                )
            if cached_data:
                final_recommendations, cached_username = cached_data
                
                # Show cache hit message
                cache_embed = discord.Embed(
                    title="⚡ Loading Cached Recommendations...",
                    description=f"Found recent recommendations for {cached_username} (cached within 24 hours)",
                    color=PALETTE.SUCCESS
                )
                await interaction.followup.send(embed=cache_embed)
                
                # Create pagination view with cached data
                view = RecommendationsView(
                    interaction.user.id, final_recommendations, cached_username, selected_type,
                )
                initial_embed = await view.create_embed()
                await interaction.edit_original_response(embed=initial_embed, view=view)
                
                logger.info(f"Served cached recommendations for user {interaction.user.id}")
                return
            
            # Show initial loading message
            loading_embed = discord.Embed(
                title="🔍 Generating Recommendations...",
                description=f"Analyzing {username}'s {selected_type.replace('_', ' ').lower()} list to find recommendations...",
                color=PALETTE.PRIMARY
            )
            await interaction.followup.send(embed=loading_embed)
            
            # Stage 1: Fetch user's manga list
            logger.info(f"Stage 1: Fetching manga list for {username}")
            try:
                manga_list, user_media_ids = await self.fetch_user_manga_list(username, api_type)
                if selected_type == "LIGHT_NOVEL":
                    manga_list = [
                        entry for entry in manga_list
                        if (entry.get("media") or {}).get("format") == "NOVEL"
                    ]
                if not manga_list:
                    embed = build_error_embed(
                        "No Media Found",
                        f"No {selected_type.replace('_', ' ').lower()} found in {username}'s AniList list (excluding planning entries)."
                    )
                    await interaction.edit_original_response(embed=embed)
                    return
            except Exception as e:
                logger.error(f"Error fetching manga list: {e}", exc_info=True)
                embed = build_error_embed(
                    "Error",
                    f"Could not fetch manga list for '{username}'. Check the username, then try again.\n\n" + application_error_message(e)
                )
                await interaction.edit_original_response(embed=embed)
                return
            
            # Stage 2: Filter high-rated manga
            logger.info("Stage 2: Filtering high-rated manga")
            filtered_manga = self.filter_high_rated_manga(manga_list)
            if not filtered_manga:
                embed = build_warning_embed(
                    "No High-Rated Manga",
                    f"{username} has no manga rated 7/10 or higher to base recommendations on."
                )
                await interaction.edit_original_response(embed=embed)
                return
            
            # Stage 3: Extract recommendations
            logger.info("Stage 3: Extracting recommendations")
            recommendations_by_category = self.extract_recommendations(
                filtered_manga, user_media_ids, selected_type,
            )
            
            # Stage 4: Filter and rank recommendations
            logger.info("Stage 4: Filtering and ranking recommendations")
            final_recommendations = self.filter_and_rank_recommendations(
                recommendations_by_category, genre=genre, year_from=year_from, year_to=year_to,
            )
            
            # Check if we have any recommendations
            total_recommendations = sum(len(recs) for recs in final_recommendations.values())
            if total_recommendations == 0:
                embed = build_warning_embed(
                    "No Recommendations Found",
                    "No recommendations matched the selected category and filters. Try a broader genre or year range."
                )
                await interaction.edit_original_response(embed=embed)
                return
            
            # Create pagination view
            logger.info("Stage 5: Creating pagination view")
            view = RecommendationsView(
                interaction.user.id, final_recommendations, username, selected_type,
            )
            if not genre and year_from is None and year_to is None:
                self.cache_recommendations(
                    interaction.guild_id, interaction.user.id, username,
                    selected_type, final_recommendations,
                )
            
            # Create initial embed (first recommendation in first available category)
            initial_embed = await view.create_embed()
            
            await interaction.edit_original_response(embed=initial_embed, view=view)
            
            logger.info(f"Recommendations command completed successfully for user {interaction.user.id}")
            
        except Exception as e:
            logger.error(f"Error in recommendations command: {e}", exc_info=True)
            embed = build_error_embed(
                "Error",
                application_error_message(e)
            )
            await interaction.edit_original_response(embed=embed)

async def setup(bot):
    await bot.add_cog(RecommendationsCog(bot))
    logger.info("Recommendations cog loaded successfully")
