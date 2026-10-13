"""
AniList API Helper Functions
Centralized functions for interacting with AniList GraphQL API
"""

import aiohttp
import asyncio
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


TRENDING_ANIME_QUERY = """
query {
    Page(page: 1, perPage: 10) {
        media(sort: TRENDING_DESC, type: ANIME) {
            title {
                romaji
                english
            }
        }
    }
}
"""


async def fetch_trending_anime_titles(
    session: aiohttp.ClientSession, timeout: int = API_TIMEOUT
) -> Optional[List[str]]:
    """
    Fetch trending anime title strings from AniList (English preferred, then romaji).

    Returns:
        Non-empty list of titles, or None if the request failed or returned no usable titles.
    """
    data = await post_graphql(session, TRENDING_ANIME_QUERY, {}, timeout=timeout)
    if not data or not isinstance(data, dict):
        return None
    if data.get("__http_status__") is not None:
        return None
    page = data.get("Page")
    if not isinstance(page, dict):
        return None
    media = page.get("media")
    if not isinstance(media, list):
        return None
    titles: List[str] = []
    for anime in media:
        if not isinstance(anime, dict):
            continue
        title_data = anime.get("title")
        if not isinstance(title_data, dict):
            continue
        title = title_data.get("english") or title_data.get("romaji")
        if title and isinstance(title, str) and title.strip():
            titles.append(title.strip())
    return titles if titles else None


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


# ===== USER PROGRESS FUNCTIONS =====


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

