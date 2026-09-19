import random
import discord
import aiohttp
import asyncio
import re
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "media_helper.log"
ANILIST_API_URL = "https://graphql.anilist.co"
CACHE_TTL = 300  # seconds
WATCHLIST_CACHE_TTL = 300  # seconds
API_TIMEOUT = 30  # seconds
MAX_RETRIES = 15
MAX_DESCRIPTION_LENGTH = 500

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging with auto-clearing
logger = logging.getLogger("MediaHelper")
logger.setLevel(logging.DEBUG)

# Clear handlers to avoid duplicates
logger.handlers.clear()

# Create file handler that clears on startup
file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter(
    fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(file_handler)

logger.info("Media Helper logging system initialized")

# User progress caching system
progress_cache: Dict[Tuple[str, int], Tuple[str, str, int, float]] = {}

async def fetch_user_progress(session: aiohttp.ClientSession, username: str, media_id: int) -> Optional[Tuple[str, str, int]]:
    """Fetch individual user's progress for a media ID with comprehensive caching and logging."""
    now = asyncio.get_event_loop().time()
    key = (username, media_id)
    
    logger.debug(f"Fetching progress for {username} on media {media_id}")

    # Use cache if recent
    if key in progress_cache:
        cached = progress_cache[key]
        cache_age = now - cached[3]
        if cache_age < CACHE_TTL:
            logger.debug(f"Using cached progress for {username} (media {media_id}, age: {cache_age:.1f}s)")
            return cached[:3]
        else:
            logger.debug(f"Cache expired for {username} (media {media_id}, age: {cache_age:.1f}s)")

    query = """
    query ($username: String, $mediaId: Int) {
        MediaList(userName: $username, mediaId: $mediaId) {
            status
            progress
        }
    }
    """
    variables = {"username": username, "mediaId": media_id}

    try:
        logger.debug(f"Making API request for {username} progress on media {media_id}")
        async with session.post(
            ANILIST_API_URL, 
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        ) as resp:
            if resp.status != 200:
                logger.warning(f"Failed to fetch progress for {username} (media {media_id}): HTTP {resp.status}")
                return None
                
            data = await resp.json()
            media_list = data.get("data", {}).get("MediaList")
            
            if media_list and media_list.get("status"):
                result = (username, media_list["status"], media_list.get("progress", 0))
                progress_cache[key] = (*result, now)
                logger.info(f"Fetched and cached progress for {username}: {result[1]} ({result[2]} progress)")
                return result
            else:
                logger.debug(f"No progress data found for {username} on media {media_id}")
                return None
                
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching progress for {username} (media {media_id}): {e}")
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching progress for {username} (media {media_id})")
    except Exception as e:
        logger.error(f"Unexpected error fetching progress for {username} (media {media_id}): {e}", exc_info=True)

    return None


async def fetch_media(
    session: aiohttp.ClientSession,
    media_type: str,
    query: str | int,
    users: Optional[List[Tuple[int, str, str]]] = None,
    max_description: int = MAX_DESCRIPTION_LENGTH
) -> Optional[discord.Embed]:
    """Fetch Anime/Manga from AniList API and return a Discord Embed with user progress."""
    
    logger.info(f"Fetching {media_type} media for query: '{query}' with {len(users) if users else 0} users")

    # Determine search variables
    is_id_query = isinstance(query, int) or (isinstance(query, str) and query.isdigit())
    variables = {"id": int(query)} if is_id_query else {"search": query}
    logger.debug(f"Using {'ID' if is_id_query else 'search'} query with variables: {variables}")
    
    graphql_query = """
    query ($search: String, $id: Int, $type: MediaType) {
        Media(search: $search, id: $id, type: $type) {
            id
            title { romaji english native }
            description(asHtml: false)
            chapters
            volumes
            episodes
            status
            genres
            averageScore
            siteUrl
            source
            coverImage { large medium }
            format
        }
    }
    """

    try:
        logger.debug(f"Making GraphQL request to AniList for {media_type}")
        async with session.post(
            ANILIST_API_URL,
            json={"query": graphql_query, "variables": {**variables, "type": media_type}},
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        ) as resp:
            if resp.status != 200:
                logger.warning(f"Failed to fetch {media_type} '{query}': HTTP {resp.status}")
                return None

            data = await resp.json()
            media = data.get("data", {}).get("Media")
            if not media:
                logger.warning(f"No {media_type} found for query '{query}'")
                return None

            media_id = media["id"]
            logger.info(f"Successfully fetched {media_type} '{media['title'].get('romaji', 'Unknown')}' (ID: {media_id})")

            # Process and clean description
            description = media.get("description") or "No description available."
            description = re.sub(r"<br\s*/?>|</?i>|</?b>", "", description)
            if len(description) > max_description:
                description = description[:max_description] + "..."
                logger.debug(f"Truncated description to {max_description} characters")

            # Get title with fallback
            title_name = (media["title"].get("english") or 
                         media["title"].get("romaji") or 
                         media["title"].get("native") or 
                         "Unknown Title")

            # Create embed
            embed = discord.Embed(
                title=title_name,
                url=media.get("siteUrl"),
                description=f"{description}\n\n**Source:** {media.get('source', 'Unknown')}",
                color=discord.Color.blue()
            )

            # Add media-specific fields
            if media_type.upper() == "ANIME":
                episodes = media.get("episodes") or "Unknown"
                embed.add_field(name="Episodes", value=episodes, inline=True)
                logger.debug(f"Added episodes field: {episodes}")
            else:
                chapters = media.get("chapters") or "Unknown"
                volumes = media.get("volumes") or "Unknown"
                embed.add_field(name="Chapters", value=chapters, inline=True)
                embed.add_field(name="Volumes", value=volumes, inline=True)
                logger.debug(f"Added chapters: {chapters}, volumes: {volumes}")

            # Add common fields
            embed.add_field(name="Status", value=media.get("status", "Unknown"), inline=True)
            embed.add_field(name="Format", value=media.get("format", "Unknown"), inline=True)
            
            genres = media.get("genres") or []
            embed.add_field(name="Genres", value=", ".join(genres) if genres else "Unknown", inline=False)
            embed.add_field(name="Average Score", value=f"{media.get('averageScore', 'N/A')}/100", inline=True)

            # Set thumbnail
            cover_url = media.get("coverImage", {}).get("large") or media.get("coverImage", {}).get("medium")
            if cover_url:
                embed.set_thumbnail(url=cover_url)
                logger.debug("Set cover image thumbnail")

            # Fetch and process user progress
            if users:
                logger.debug(f"Fetching progress for {len(users)} users")
                tasks = [fetch_user_progress(session, user[2], media_id) for user in users]
                progress_results = await asyncio.gather(*tasks, return_exceptions=True)

                progress_label = "ep" if media_type.upper() == "ANIME" else "ch"
                status_groups: Dict[str, List[str]] = {}
                processed_count = 0
                
                for i, item in enumerate(progress_results):
                    if isinstance(item, Exception):
                        logger.warning(f"Error fetching progress for user {users[i][2]}: {item}")
                        continue
                        
                    if not item:
                        continue
                        
                    username, user_status, user_prog = item
                    if user_status.upper() == "COMPLETED":
                        continue  # Skip completed entries
                        
                    status_groups.setdefault(user_status, []).append(
                        f"`{username}`: {progress_label} `{user_prog}`"
                    )
                    processed_count += 1

                logger.debug(f"Processed progress for {processed_count} users across {len(status_groups)} status groups")

                # Format progress groups
                if status_groups:
                    grouped_text = ""
                    for status, user_list in status_groups.items():
                        grouped_text += f"**{status}**:\n" + "\n".join(user_list) + "\n\n"

                    if len(grouped_text) > 1024:
                        grouped_text = grouped_text[:1020] + "…"
                        logger.debug("Truncated progress field to fit embed limits")
                        
                    embed.add_field(name="User Progress", value=grouped_text.strip(), inline=False)
                else:
                    logger.debug("No active user progress to display")

            return embed

    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching {media_type} '{query}': {e}")
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching {media_type} '{query}' after {API_TIMEOUT}s")
    except Exception as e:
        logger.error(f"Unexpected error fetching {media_type} '{query}': {e}", exc_info=True)

    return None


# GraphQL queries for user media collections
USER_MEDIA_COLLECTION_QUERY = """
query ($username: String, $type: MediaType) {
  MediaListCollection(userName: $username, type: $type) {
    lists {
      entries {
        mediaId
        status
        score
        progress
        media { 
          chapters
          episodes
        }
      }
    }
  }
}
"""

async def fetch_anilist_entries(username: str, media_type: str) -> List[Dict]:
    """
    Fetches all media entries for a user from AniList with comprehensive logging and error handling.
    
    Args:
        username: The AniList username.
        media_type: Either "MANGA" or "ANIME".

    Returns:
        A list of dicts containing mediaId, status, score, progress, chapters/episodes.
    """
    logger.info(f"Fetching {media_type} entries for user: {username}")
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as session:
        try:
            async with session.post(
                ANILIST_API_URL, 
                json={
                    "query": USER_MEDIA_COLLECTION_QUERY, 
                    "variables": {"username": username, "type": media_type}
                }
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"AniList API request failed [{resp.status}] for {username} ({media_type})")
                    return []

                data = await resp.json()
                entries = []
                total_entries = 0
                
                # Process all lists in the collection
                for group in data.get("data", {}).get("MediaListCollection", {}).get("lists", []):
                    group_entries = group.get("entries", [])
                    total_entries += len(group_entries)
                    
                    for entry in group_entries:
                        media_info = entry.get("media", {})
                        
                        # Get appropriate count field based on media type
                        count_field = "chapters" if media_type.upper() == "MANGA" else "episodes"
                        total_count = media_info.get(count_field) or 0
                        
                        processed_entry = {
                            "id": entry.get("mediaId"),
                            "status": entry.get("status"),
                            "score": entry.get("score") or 0,
                            "progress": entry.get("progress") or 0,
                            count_field: total_count
                        }
                        entries.append(processed_entry)

                logger.info(f"Successfully fetched {len(entries)} {media_type} entries from {total_entries} total entries for {username}")
                return entries

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching {media_type} entries for {username}: {e}")
            return []
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {media_type} entries for {username} after {API_TIMEOUT}s")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching {media_type} entries for {username}: {e}", exc_info=True)
            return []

async def fetch_media_by_title(session: aiohttp.ClientSession, title: str, media_type: str):
    """
    Fetch a single media entry from AniList by title with relations data.
    Returns the media object with relations (prequels, sequels, spin-offs, etc.)
    """
    logger.info(f"Fetching {media_type} by title: '{title}'")
    
    query = '''
    query ($search: String, $type: MediaType) {
      Media(search: $search, type: $type) {
        id
        title {
          romaji
          english
          native
        }
        format
        status
        relations {
          edges {
            relationType
            node {
              id
              title {
                romaji
                english
                native
              }
              format
              status
            }
          }
        }
      }
    }
    '''
    variables = {"search": title, "type": media_type}

    try:
        logger.debug(f"Making GraphQL request for media relations: {title}")
        async with session.post(
            ANILIST_API_URL, 
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        ) as resp:
            if resp.status != 200:
                logger.warning(f"Failed to fetch media by title '{title}' ({media_type}): HTTP {resp.status}")
                return None
                
            data = await resp.json()
            media = data.get("data", {}).get("Media")
            
            if media:
                relations_count = len(media.get("relations", {}).get("edges", []))
                logger.info(f"Successfully fetched '{media['title'].get('romaji', title)}' with {relations_count} relations")
            else:
                logger.warning(f"No media found for title '{title}' ({media_type})")
                
            return media
            
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching media by title '{title}': {e}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching media by title '{title}' after {API_TIMEOUT}s")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching media by title '{title}': {e}", exc_info=True)
        return None

async def fetch_user_stats(username: str) -> dict:
    """
    Fetch a user's overall AniList stats (anime + manga) with comprehensive logging.
    Includes counts, episodes/chapters read, average score, and genres.
    """
    logger.info(f"Fetching comprehensive stats for user: {username}")
    
    query = """
    query ($username: String) {
      User(name: $username) {
        id
        name
        statistics {
          anime {
            count
            episodesWatched
            meanScore
            genres {
              genre
              count
            }
            statuses {
              status
              count
            }
            scores {
              score
              count
            }
          }
          manga {
            count
            chaptersRead
            meanScore
            genres {
              genre
              count
            }
            statuses {
              status
              count
            }
            scores {
              score
              count
            }
          }
        }
      }
    }
    """
    variables = {"username": username}

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as session:
        try:
            logger.debug(f"Making API request for user stats: {username}")
            async with session.post(
                ANILIST_API_URL, 
                json={"query": query, "variables": variables}
            ) as resp:
                if resp.status == 404:
                    logger.warning(f"AniList user not found: {username}")
                    return {"error": "User not found"}
                elif resp.status != 200:
                    logger.warning(f"AniList API request failed [{resp.status}] for stats of {username}")
                    return {"error": f"API error: {resp.status}"}
                
                data = await resp.json()
                user_data = data.get("data", {}).get("User", {})
                
                if user_data:
                    stats = user_data.get("statistics", {})
                    anime_stats = stats.get("anime", {})
                    manga_stats = stats.get("manga", {})
                    
                    logger.info(f"Successfully fetched stats for {username}: "
                              f"Anime count: {anime_stats.get('count', 0)}, "
                              f"Manga count: {manga_stats.get('count', 0)}")
                else:
                    logger.warning(f"No user data found for {username}")
                    
                return data
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching stats for {username}: {e}")
            return {"error": f"Network error: {e}"}
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching stats for {username} after {API_TIMEOUT}s")
            return {"error": "Request timeout"}
        except Exception as e:
            logger.error(f"Unexpected error fetching stats for {username}: {e}", exc_info=True)
            return {"error": f"Unexpected error: {e}"}
async def fetch_media_with_recommendations(session: aiohttp.ClientSession, media_id: int, media_type: str):
    """
    Fetch a media entry with its recommendations from AniList with comprehensive logging.
    Returns the raw Media object (not an Embed).
    """
    logger.info(f"Fetching {media_type} recommendations for media ID: {media_id}")
    
    query = """
    query ($id: Int, $type: MediaType) {
      Media(id: $id, type: $type) {
        id
        title {
          romaji
          english
          native
        }
        recommendations {
          edges {
            node {
              rating
              mediaRecommendation {
                id
                title {
                  romaji
                  english
                  native
                }
                averageScore
                format
                status
              }
            }
          }
        }
      }
    }
    """
    variables = {"id": media_id, "type": media_type}

    try:
        logger.debug(f"Making GraphQL request for media recommendations: {media_id}")
        async with session.post(
            ANILIST_API_URL, 
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        ) as resp:
            if resp.status != 200:
                logger.warning(f"AniList API request failed [{resp.status}] for {media_id} ({media_type}) recommendations")
                return None
                
            data = await resp.json()
            media = data.get("data", {}).get("Media")
            
            if media:
                recommendations = media.get("recommendations", {}).get("edges", [])
                logger.info(f"Successfully fetched recommendations for '{media['title'].get('romaji', 'Unknown')}': "
                          f"{len(recommendations)} recommendations found")
                
                # Log recommendation details
                if recommendations:
                    valid_recs = [r for r in recommendations if r.get("node", {}).get("mediaRecommendation")]
                    logger.debug(f"Found {len(valid_recs)} valid recommendations with rating data")
            else:
                logger.warning(f"No media found for ID {media_id} ({media_type})")
                
            return media
            
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching recommendations for {media_id} ({media_type}): {e}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching recommendations for {media_id} after {API_TIMEOUT}s")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching recommendations for {media_id} ({media_type}): {e}", exc_info=True)
        return None

async def fetch_random_media(media_type: str = "ANIME") -> Optional[discord.Embed]:
    """
    Fetch a completely random Anime, Manga, or Light Novel (LN) from AniList with comprehensive logging.
    """
    logger.info(f"Fetching random {media_type}")
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as session:
        attempts = 0
        
        for attempt in range(MAX_RETRIES):
            attempts = attempt + 1
            random_id = random.randint(1, 180000)
            logger.debug(f"Attempt {attempts}/{MAX_RETRIES}: Trying random ID {random_id}")

            if media_type in ["ANIME", "MANGA"]:
                embed = await fetch_media(session, media_type, random_id)
                if embed:
                    logger.info(f"Successfully found random {media_type} after {attempts} attempts: '{embed.title}'")
                    return embed

            elif media_type == "LN":
                query = """
                query ($id: Int) {
                  Media(id: $id, type: MANGA) {
                    id
                    format
                    title { romaji english native }
                    description(asHtml: false)
                    coverImage { large medium }
                    siteUrl
                    averageScore
                    status
                  }
                }
                """
                
                try:
                    async with session.post(
                        ANILIST_API_URL, 
                        json={"query": query, "variables": {"id": random_id}}
                    ) as resp:
                        if resp.status != 200:
                            logger.debug(f"Failed to fetch random LN ID {random_id}: HTTP {resp.status}")
                            continue
                            
                        data = await resp.json()
                        media = data.get("data", {}).get("Media")
                        
                        if not media or media.get("format") != "NOVEL":
                            logger.debug(f"ID {random_id} is not a light novel (format: {media.get('format') if media else 'None'})")
                            continue

                        # Process light novel data
                        title_name = (media["title"].get("english") or 
                                    media["title"].get("romaji") or 
                                    media["title"].get("native") or 
                                    "Unknown Light Novel")
                                    
                        description = media.get("description") or "No description available."
                        description = re.sub(r"<br\s*/?>|</?i>|</?b>", "", description)
                        if len(description) > MAX_DESCRIPTION_LENGTH:
                            description = description[:MAX_DESCRIPTION_LENGTH] + "..."

                        embed = discord.Embed(
                            title=title_name,
                            url=media.get("siteUrl"),
                            description=description,
                            color=discord.Color.purple()  # Different color for LNs
                        )
                        
                        embed.add_field(name="Type", value="Light Novel", inline=True)
                        embed.add_field(name="Status", value=media.get("status", "Unknown"), inline=True)
                        embed.add_field(name="Average Score", value=f"{media.get('averageScore', 'N/A')}/100", inline=True)

                        cover_url = media.get("coverImage", {}).get("large") or media.get("coverImage", {}).get("medium")
                        if cover_url:
                            embed.set_thumbnail(url=cover_url)

                        logger.info(f"Successfully found random light novel after {attempts} attempts: '{title_name}'")
                        return embed
                        
                except aiohttp.ClientError as e:
                    logger.debug(f"Network error fetching random LN ID {random_id}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error fetching random LN ID {random_id}: {e}")
                    continue

        logger.warning(f"Failed to find random {media_type} after {MAX_RETRIES} attempts")
        return None

# Watchlist caching system
WATCHLIST_CACHE: Dict[str, Tuple[dict, float]] = {}

WATCHLIST_QUERY = """
query ($username: String) {
  anime: MediaListCollection(userName: $username, type: ANIME, status_in: [CURRENT, REPEATING]) {
    lists {
      entries {
        progress
        media {
          id
          title {
            romaji
            english
            native
          }
          episodes
          siteUrl
        }
      }
    }
  }
  manga: MediaListCollection(userName: $username, type: MANGA, status_in: [CURRENT, REPEATING]) {
    lists {
      entries {
        progress
        media {
          id
          title {
            romaji
            english
            native
          }
          chapters
          format
          siteUrl
        }
      }
    }
  }
}
"""

async def fetch_watchlist(username: str) -> Optional[dict]:
    """
    Fetches a user's current anime + manga watchlist from AniList with comprehensive caching and logging.

    Args:
        username (str): AniList username.

    Returns:
        dict: {
            "anime": [ ... ],
            "manga": [ ... ]
        }
        or None if fetch failed.
    """
    logger.info(f"Fetching watchlist for user: {username}")
    now = asyncio.get_event_loop().time()

    # Check cache first
    if username in WATCHLIST_CACHE:
        cached_data, cached_time = WATCHLIST_CACHE[username]
        cache_age = now - cached_time
        if cache_age < WATCHLIST_CACHE_TTL:
            logger.debug(f"Using cached watchlist for {username} (age: {cache_age:.1f}s)")
            return cached_data
        else:
            logger.debug(f"Cache expired for {username} (age: {cache_age:.1f}s)")

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as session:
        try:
            logger.debug(f"Making API request for watchlist: {username}")
            async with session.post(
                ANILIST_API_URL,
                json={"query": WATCHLIST_QUERY, "variables": {"username": username}},
            ) as resp:
                # Handle specific error codes
                if resp.status == 404:
                    logger.warning(f"AniList user not found: {username}")
                    return None
                elif resp.status == 429:
                    logger.warning(f"Rate limited by AniList for {username}")
                    return None
                elif resp.status != 200:
                    logger.warning(f"AniList watchlist fetch failed ({resp.status}) for {username}")
                    return None

                data = await resp.json()
                
                # Process response data
                anime_lists = data.get("data", {}).get("anime", {}).get("lists", [])
                manga_lists = data.get("data", {}).get("manga", {}).get("lists", [])
                
                # Count entries
                anime_count = sum(len(lst.get("entries", [])) for lst in anime_lists)
                manga_count = sum(len(lst.get("entries", [])) for lst in manga_lists)
                
                result = {
                    "anime": anime_lists,
                    "manga": manga_lists,
                }

                # Cache the result
                WATCHLIST_CACHE[username] = (result, now)
                
                logger.info(f"Successfully fetched watchlist for {username}: "
                          f"{anime_count} anime, {manga_count} manga entries")
                return result

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching watchlist for {username}: {e}")
            return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching watchlist for {username} after {API_TIMEOUT}s")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching watchlist for {username}: {e}", exc_info=True)
            return None