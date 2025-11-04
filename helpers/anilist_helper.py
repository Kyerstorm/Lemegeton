"""
AniList API Helper Functions
Centralized functions for interacting with AniList GraphQL API
"""

import aiohttp
import asyncio
import random
import re
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "anilist_helper.log"
ANILIST_API_URL = "https://graphql.anilist.co"
GRAPHQL_URL = "https://graphql.anilist.co"
API_TIMEOUT = 30
MAX_RETRIES = 5

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging
logger = logging.getLogger("AniListHelper")
logger.setLevel(logging.DEBUG)

# Clear handlers to avoid duplicates
logger.handlers.clear()

# Create file handler
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

logger.info("AniList Helper logging system initialized")


# ===== BASIC API FUNCTIONS =====

async def post_graphql(session: aiohttp.ClientSession, query: str, variables: Dict[str, Any],
                      timeout: int = API_TIMEOUT) -> Optional[Dict[str, Any]]:
    """
    Post a GraphQL query to AniList API with error handling.
    """
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    try:
        async with session.post(GRAPHQL_URL, json={"query": query, "variables": variables}, 
                               headers=headers, timeout=timeout) as resp:
            if resp.status == 200:
                j = await resp.json()
                if "errors" in j:
                    logger.warning(f"GraphQL errors: {j['errors']}")
                    return None
                return j.get("data")
            else:
                logger.warning(f"HTTP {resp.status} response from AniList")
                return {"__http_status__": resp.status}
    except asyncio.TimeoutError:
        logger.warning("Request timeout to AniList API")
        return None
    except aiohttp.ClientError as e:
        logger.warning(f"Client error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in post_graphql: {e}")
        return None


async def fetch_anilist_user_id(username: str) -> Optional[int]:
    """
    Fetch AniList user ID from username.
    """
    query = """
    query($username: String) {
        User(name: $username) {
            id
        }
    }
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            data = await post_graphql(session, query, {"username": username})
            if data and "User" in data:
                return data["User"]["id"]
    except Exception as e:
        logger.error(f"Error fetching user ID for {username}: {e}")
    return None


async def fetch_anilist_user_basic(username: str) -> Optional[Dict[str, Any]]:
    """
    Fetch basic AniList user information (id, name, avatar).
    Returns dict with 'id', 'name', and 'avatar' keys, or None if user not found.
    """
    query = """
    query($name: String) {
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
    
    try:
        async with aiohttp.ClientSession() as session:
            data = await post_graphql(session, query, {"name": username})
            if data and "User" in data:
                user = data["User"]
                avatar = user.get("avatar", {})
                return {
                    "id": user["id"],
                    "name": user.get("name", username),
                    "avatar": avatar.get("large") or avatar.get("medium")
                }
    except Exception as e:
        logger.error(f"Error fetching basic user info for {username}: {e}")
    return None


# ===== MEDIA FETCHING FUNCTIONS =====

async def fetch_media_by_id(media_id: int, media_type: str) -> Optional[Dict]:
    """
    Fetch detailed media information by ID and type.
    """
    query = """
    query($id: Int, $type: MediaType) {
        Media(id: $id, type: $type) {
            id
            siteUrl
            title { romaji english native }
            description(asHtml: false)
            coverImage { large medium color }
            bannerImage
            type
            status
            episodes
            chapters
            volumes
            startDate { year month day }
            endDate { year month day }
            studios { nodes { id name } }
            popularity
            favourites
            source
            format
            averageScore
            genres
            tags { id name rank isMediaSpoiler }
            relations { edges { relationType node { id siteUrl title { romaji english native } coverImage { large } type status } } }
            characters(page:1, perPage:50) { edges { id role node { id name { full native } image { large } } } }
            staff(page:1, perPage:50) { edges { id role node { id name { full } language image { large } } } }
            stats { scoreDistribution { score amount } statusDistribution { status amount } }
            recommendations { edges { node { mediaRecommendation { id title { romaji english } coverImage { large } siteUrl } } } }
            externalLinks { site url }
        }
    }
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            data = await post_graphql(session, query, {"id": media_id, "type": media_type})
            if data and "Media" in data:
                return data["Media"]
    except Exception as e:
        logger.error(f"Error fetching media {media_id}: {e}")
    return None


async def fetch_media_by_search(query_text: str, media_type: str, exclude_novels: bool = False, per_page: int = 10) -> List[Dict]:
    """
    Search for media by title.
    """
    query = """
    query ($search: String, $type: MediaType, $perPage: Int) {
        Page(perPage: $perPage) {
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
    
    try:
        async with aiohttp.ClientSession() as session:
            data = await post_graphql(session, query, {
                "search": query_text, 
                "type": media_type, 
                "perPage": per_page
            })
            
            if data and "Page" in data:
                media_list = data["Page"]["media"]
                
                # Filter out light novels if requested
                if exclude_novels:
                    media_list = [media for media in media_list if media.get("format") != "LIGHT_NOVEL"]
                
                return media_list
    except Exception as e:
        logger.error(f"Error searching media '{query_text}': {e}")
    return []


# ===== USER PROGRESS FUNCTIONS =====

async def fetch_user_media_progress(username: str, media_id: int, media_type: str) -> Optional[Dict]:
    """
    Fetch user's progress and rating for a specific media.
    Returns dict with 'progress', 'score', and 'rating10' (normalized to /10 scale).
    """
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
        }
    }
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            data = await post_graphql(session, query, {
                "userName": username, 
                "mediaId": media_id, 
                "type": media_type
            })
            
            if not data:
                return None
                
            user_opts = data.get("User", {}).get("mediaListOptions", {})
            score_format = user_opts.get("scoreFormat", "POINT_100")
            
            entry = data.get("MediaList")
            if not entry:
                return None
                
            progress = entry.get("progress")
            score = entry.get("score")
            
            # Normalize score to /10 scale
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
                    
            return {
                "progress": progress, 
                "score": score, 
                "rating10": rating10,
                "score_format": score_format
            }
            
    except Exception as e:
        logger.error(f"Error fetching progress for {username}, media {media_id}: {e}")
    return None


async def fetch_user_stats(username: str) -> Optional[Dict]:
    """
    Fetch comprehensive user statistics from AniList.
    """
    query = """
    query($username: String) {
        User(name: $username) {
            id
            name
            siteUrl
            avatar { large }
            bannerImage
            about(asHtml: false)
            statistics {
                anime {
                    count
                    meanScore
                    standardDeviation
                    minutesWatched
                    episodesWatched
                }
                manga {
                    count
                    meanScore
                    standardDeviation
                    chaptersRead
                    volumesRead
                }
            }
            favourites {
                anime { nodes { id title { romaji } coverImage { large } } }
                manga { nodes { id title { romaji } coverImage { large } } }
                characters { nodes { id name { full } image { large } } }
                staff { nodes { id name { full } image { large } } }
                studios { nodes { id name } }
            }
        }
    }
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            data = await post_graphql(session, query, {"username": username})
            if data and "User" in data:
                return data["User"]
    except Exception as e:
        logger.error(f"Error fetching user stats for {username}: {e}")
    return None


# ===== ACTIVITY FUNCTIONS =====

async def fetch_activity(activity_id: int) -> Optional[Dict]:
    """
    Fetch AniList activity by ID.
    """
    query = """
    query($id: Int) {
        Activity(id: $id) {
            __typename

            ... on TextActivity {
                id
                text
                likeCount
                replyCount
                siteUrl
                user { id name siteUrl avatar { large } }
                replies { id text likeCount user { id name siteUrl avatar { large } } }
            }

            ... on MessageActivity {
                id
                message
                likeCount
                replyCount
                siteUrl
                messenger { id name siteUrl avatar { large } }
                recipient { id name siteUrl avatar { large } }
                replies { id text likeCount user { id name siteUrl avatar { large } } }
            }

            ... on ListActivity {
                id
                status
                progress
                likeCount
                replyCount
                siteUrl
                user { id name siteUrl avatar { large } }
                media { id siteUrl title { romaji } coverImage { large } bannerImage }
                replies { id text likeCount user { id name siteUrl avatar { large } } }
            }
        }
    }
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            data = await post_graphql(session, query, {"id": activity_id})
            if data and "Activity" in data:
                return data["Activity"]
    except Exception as e:
        logger.error(f"Error fetching activity {activity_id}: {e}")
    return None


# ===== BULK SCRAPING FUNCTIONS =====

def get_page_info_query(media_type: str) -> str:
    """Generate query for getting page information."""
    return f'''
    query ($page: Int, $perPage: Int, $sort: [MediaSort]) {{
        Page(page: $page, perPage: $perPage) {{
            pageInfo {{
                total
                currentPage
                lastPage
                hasNextPage
                perPage
            }}
            media(type: {media_type}, sort: $sort) {{
                id
            }}
        }}
    }}
    '''


def get_full_scraping_query(media_type: str) -> str:
    """Generate query for full media scraping."""
    return f'''
    query ($page: Int, $perPage: Int, $sort: [MediaSort]) {{
        Page(page: $page, perPage: $perPage) {{
            pageInfo {{
                total
                currentPage
                lastPage
                hasNextPage
                perPage
            }}
            media(type: {media_type}, sort: $sort) {{
                id
                idMal
                title {{
                    romaji
                    english
                    userPreferred
                }}
                averageScore
                popularity
                favourites
                coverImage {{ medium }}
                startDate {{ year month day }}
                siteUrl
            }}
        }}
    }}
    '''


async def fetch_page_with_retries(session: aiohttp.ClientSession, media_type: str, page_num: int,
                                 sort: str, batch_size: int = 50, retries: int = MAX_RETRIES,
                                 backoff_base: float = 0.5, backoff_max: float = 30.0,
                                 jitter: bool = True) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch a single page with retries and exponential backoff.
    Returns list of media dicts or None if ultimately failed.
    """
    attempt = 0
    while attempt <= retries:
        variables = {"page": page_num, "perPage": batch_size, "sort": [sort]}
        data = await post_graphql(session, get_full_scraping_query(media_type), variables)

        # If we got a dict signaling HTTP status, inspect it
        if isinstance(data, dict) and "__http_status__" in data:
            status = data["__http_status__"]
            # 429 -> respect backoff and retry
            if status == 429:
                wait = min(backoff_max, backoff_base * (2 ** attempt))
                if jitter:
                    wait = wait * (0.5 + random.random() * 0.5)
                await asyncio.sleep(wait)
                attempt += 1
                continue
            # 5xx -> transient server error: backoff + retry
            if 500 <= status < 600:
                wait = min(backoff_max, backoff_base * (2 ** attempt))
                if jitter:
                    wait += random.random() * 0.5
                await asyncio.sleep(wait)
                attempt += 1
                continue
            # 4xx other than 429 -> probably client issue; give up
            return None

        # If data is None (timeout or client error), backoff and retry
        if data is None:
            wait = min(backoff_max, backoff_base * (2 ** attempt))
            if jitter:
                wait *= (0.75 + random.random() * 0.5)
            await asyncio.sleep(wait)
            attempt += 1
            continue

        # Successful response: extract list
        media = data.get("Page", {}).get("media", [])
        return media

    # out of retries
    logger.warning(f"Failed to fetch page {page_num} after {retries} retries")
    return None


# ===== TEXT CLEANING FUNCTIONS =====

def clean_anilist_text(text: Optional[str]) -> str:
    """
    Clean AniList text content (descriptions, activity text, etc.).
    """
    if not text:
        return ""
        
    # Remove HTML tags if AniList returned any
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)

    # ~~~text~~~ → text (any content in triple tildes)
    text = re.sub(r"~{3}(.*?)~{3}", r"\1", text, flags=re.DOTALL)

    # Remove wrapping ~ around img/vid placeholders
    text = re.sub(r"~+imgx?\((https?://[^\s)]+)\)~+", r"img(\1)", text)
    text = re.sub(r"~+vid\((https?://[^\s)]+)\)~+", r"vid(\1)", text)

    # Remove media placeholders and raw media links (leave other links)
    text = re.sub(r"(?:imgx?|vid)\((https?://[^\s)]+)\)", "", text)
    text = re.sub(r"https?://[^\s]+(?:\.png|\.jpg|\.jpeg|\.gif|\.mp4|\.webm|\.webp)", "", text)

    # Spoilers
    text = re.sub(r"~!(.*?)!~", r"||\1||", text)

    # Headers mapping
    text = re.sub(r"^# (.+)$", r"__**\1**__", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r"**\1**", text, flags=re.MULTILINE)
    text = re.sub(r"^### (.+)$", r"_\1_", text, flags=re.MULTILINE)

    # Trim long whitespace
    return text.strip()


def extract_media_links(text: Optional[str]) -> tuple[List[str], str]:
    """
    Extract media links from AniList text and return cleaned text.
    Returns (media_links, cleaned_text).
    """
    if not text:
        return [], ""
        
    media_links = []
    
    # Extract img/vid placeholders
    for m in re.finditer(r"(?:imgx?|vid)\((https?://[^\s)]+)\)", text):
        media_links.append(m.group(1))
        
    # Extract direct media links
    for m in re.finditer(r"(https?://[^\s]+(?:\.png|\.jpg|\.jpeg|\.gif|\.webp|\.mp4|\.webm))", text):
        url = m.group(1)
        if url not in media_links:
            media_links.append(url)
            
    # Clean text by removing media
    cleaned = re.sub(r"(?:imgx?|vid)\((https?://[^\s)]+)\)", "", text)
    cleaned = re.sub(r"https?://[^\s]+(?:\.png|\.jpg|\.jpeg|\.gif|\.mp4|\.webm|\.webp)", "", cleaned)
    
    return media_links, cleaned.strip()


def format_date(date_dict: Dict[str, Any]) -> str:
    """
    Format AniList date object to string.
    """
    if not date_dict:
        return "Unknown"
        
    y = date_dict.get("year")
    m = date_dict.get("month")
    day = date_dict.get("day")
    
    if not y:
        return "Unknown"
    if not m:
        return f"{y}"
    if not day:
        return f"{y}-{m:02d}"
    return f"{y}-{m:02d}-{day:02d}"


def format_description(description: str, max_length: int = 400) -> str:
    """
    Format and truncate description text.
    """
    if not description:
        return "No description available."
        
    cleaned = clean_anilist_text(description)
    if len(cleaned) > max_length:
        return cleaned[:max_length] + "..."
    return cleaned