"""
Profile Helper Functions
Centralized functions for user profile management, statistics, and AniList profile processing
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

import discord

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "profile_helper.log"

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging
logger = logging.getLogger("ProfileHelper")
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

logger.info("Profile Helper logging system initialized")


# ===== USER STATISTICS PROCESSING =====

def process_anime_statistics(anime_stats: Dict) -> Dict[str, Any]:
    """
    Process anime statistics from AniList API response.
    """
    if not anime_stats:
        return {
            "count": 0,
            "mean_score": 0.0,
            "genres": [],
            "statuses": [],
            "scores": [],
            "formats": []
        }
    
    return {
        "count": anime_stats.get("count", 0),
        "mean_score": anime_stats.get("meanScore", 0.0),
        "genres": anime_stats.get("genres", []),
        "statuses": anime_stats.get("statuses", []),
        "scores": anime_stats.get("scores", []),
        "formats": anime_stats.get("formats", [])
    }


def process_manga_statistics(manga_stats: Dict) -> Dict[str, Any]:
    """
    Process manga statistics from AniList API response.
    """
    if not manga_stats:
        return {
            "count": 0,
            "mean_score": 0.0,
            "genres": [],
            "statuses": [],
            "scores": [],
            "formats": [],
            "countries": []
        }
    
    return {
        "count": manga_stats.get("count", 0),
        "mean_score": manga_stats.get("meanScore", 0.0),
        "genres": manga_stats.get("genres", []),
        "statuses": manga_stats.get("statuses", []),
        "scores": manga_stats.get("scores", []),
        "formats": manga_stats.get("formats", []),
        "countries": manga_stats.get("countries", [])
    }


def get_top_genres(genre_stats: List[Dict], limit: int = 5) -> List[Tuple[str, int]]:
    """
    Get top genres from genre statistics.
    Returns list of (genre_name, count) tuples.
    """
    if not genre_stats:
        return []
    
    # Sort by count descending
    sorted_genres = sorted(genre_stats, key=lambda x: x.get("count", 0), reverse=True)
    
    return [(genre.get("genre", "Unknown"), genre.get("count", 0)) 
            for genre in sorted_genres[:limit]]


def get_status_distribution(status_stats: List[Dict]) -> Dict[str, int]:
    """
    Get status distribution from status statistics.
    """
    distribution = {}
    
    for status in status_stats:
        status_name = status.get("status", "Unknown")
        count = status.get("count", 0)
        distribution[status_name] = count
    
    return distribution


def get_score_distribution(score_stats: List[Dict]) -> Dict[int, int]:
    """
    Get score distribution from score statistics.
    """
    distribution = {}
    
    for score in score_stats:
        score_value = score.get("score", 0)
        count = score.get("count", 0)
        if score_value:  # Skip 0 scores
            distribution[score_value] = count
    
    return distribution


def calculate_completion_rate(status_stats: List[Dict], media_type: str = "anime") -> float:
    """
    Calculate completion rate from status statistics.
    """
    total = 0
    completed = 0
    
    for status in status_stats:
        status_name = status.get("status", "").upper()
        count = status.get("count", 0)
        
        if status_name in ["COMPLETED", "CURRENT", "PAUSED", "DROPPED", "PLANNING"]:
            total += count
            if status_name == "COMPLETED":
                completed += count
    
    return (completed / total * 100) if total > 0 else 0.0


# ===== FAVORITES PROCESSING =====

def process_favorite_anime(favorite_anime: Dict) -> List[Dict[str, Any]]:
    """
    Process favorite anime from AniList API response.
    """
    if not favorite_anime or "nodes" not in favorite_anime:
        return []
    
    processed = []
    for anime in favorite_anime["nodes"]:
        processed.append({
            "id": anime.get("id"),
            "title": get_preferred_title(anime.get("title", {})),
            "cover_image": anime.get("coverImage", {}).get("large", ""),
            "site_url": anime.get("siteUrl", ""),
            "average_score": anime.get("averageScore"),
            "genres": anime.get("genres", []),
            "format": anime.get("format", ""),
            "episodes": anime.get("episodes"),
            "status": anime.get("status", "")
        })
    
    return processed


def process_favorite_manga(favorite_manga: Dict) -> List[Dict[str, Any]]:
    """
    Process favorite manga from AniList API response.
    """
    if not favorite_manga or "nodes" not in favorite_manga:
        return []
    
    processed = []
    for manga in favorite_manga["nodes"]:
        processed.append({
            "id": manga.get("id"),
            "title": get_preferred_title(manga.get("title", {})),
            "cover_image": manga.get("coverImage", {}).get("large", ""),
            "site_url": manga.get("siteUrl", ""),
            "average_score": manga.get("averageScore"),
            "genres": manga.get("genres", []),
            "format": manga.get("format", ""),
            "chapters": manga.get("chapters"),
            "volumes": manga.get("volumes"),
            "status": manga.get("status", "")
        })
    
    return processed


def process_favorite_characters(favorite_characters: Dict) -> List[Dict[str, Any]]:
    """
    Process favorite characters from AniList API response.
    """
    if not favorite_characters or "nodes" not in favorite_characters:
        return []
    
    processed = []
    for character in favorite_characters["nodes"]:
        processed.append({
            "id": character.get("id"),
            "name": character.get("name", {}).get("full", "Unknown"),
            "image": character.get("image", {}).get("large", ""),
            "site_url": character.get("siteUrl", "")
        })
    
    return processed


def process_favorite_studios(favorite_studios: Dict) -> List[Dict[str, Any]]:
    """
    Process favorite studios from AniList API response.
    """
    if not favorite_studios or "nodes" not in favorite_studios:
        return []
    
    processed = []
    for studio in favorite_studios["nodes"]:
        processed.append({
            "id": studio.get("id"),
            "name": studio.get("name", "Unknown"),
            "site_url": studio.get("siteUrl", "")
        })
    
    return processed


def process_favorite_staff(favorite_staff: Dict) -> List[Dict[str, Any]]:
    """
    Process favorite staff from AniList API response.
    """
    if not favorite_staff or "nodes" not in favorite_staff:
        return []
    
    processed = []
    for staff in favorite_staff["nodes"]:
        processed.append({
            "id": staff.get("id"),
            "name": staff.get("name", {}).get("full", "Unknown"),
            "image": staff.get("image", {}).get("large", ""),
            "site_url": staff.get("siteUrl", "")
        })
    
    return processed


# ===== TITLE UTILITIES =====

def get_preferred_title(title_data: Dict, prefer_english: bool = True) -> str:
    """
    Get preferred title from AniList title data.
    """
    if not title_data:
        return "Unknown"
    
    if prefer_english and title_data.get("english"):
        return title_data["english"]
    elif title_data.get("romaji"):
        return title_data["romaji"]
    elif title_data.get("native"):
        return title_data["native"]
    elif title_data.get("english"):
        return title_data["english"]
    else:
        return "Unknown"


def format_title_for_display(title: str, max_length: int = 50) -> str:
    """
    Format title for display with length limiting.
    """
    if not title:
        return "Unknown"
    
    if len(title) <= max_length:
        return title
    
    return title[:max_length - 3] + "..."


# ===== DISCORD EMBED UTILITIES =====

def create_profile_overview_embed(user_data: Dict, statistics: Dict) -> discord.Embed:
    """
    Create Discord embed for profile overview.
    """
    username = user_data.get("name", "Unknown")
    avatar = user_data.get("avatar", {}).get("large", "")
    banner = user_data.get("bannerImage", "")
    
    embed = discord.Embed(
        title=f"AniList Profile: {username}",
        url=f"https://anilist.co/user/{username}",
        color=discord.Color.blue()
    )
    
    if avatar:
        embed.set_thumbnail(url=avatar)
    
    if banner:
        embed.set_image(url=banner)
    
    # Add anime statistics
    anime_stats = statistics.get("anime", {})
    if anime_stats and anime_stats.get("count", 0) > 0:
        anime_text = f"**Count:** {anime_stats['count']:,}\n"
        if anime_stats.get("mean_score"):
            anime_text += f"**Mean Score:** {anime_stats['mean_score']:.1f}/100\n"
        
        completion_rate = calculate_completion_rate(anime_stats.get("statuses", []), "anime")
        if completion_rate > 0:
            anime_text += f"**Completion Rate:** {completion_rate:.1f}%"
        
        embed.add_field(name="📺 Anime", value=anime_text, inline=True)
    
    # Add manga statistics
    manga_stats = statistics.get("manga", {})
    if manga_stats and manga_stats.get("count", 0) > 0:
        manga_text = f"**Count:** {manga_stats['count']:,}\n"
        if manga_stats.get("mean_score"):
            manga_text += f"**Mean Score:** {manga_stats['mean_score']:.1f}/100\n"
        
        completion_rate = calculate_completion_rate(manga_stats.get("statuses", []), "manga")
        if completion_rate > 0:
            manga_text += f"**Completion Rate:** {completion_rate:.1f}%"
        
        embed.add_field(name="📖 Manga", value=manga_text, inline=True)
    
    return embed


def create_statistics_embed(username: str, statistics: Dict, stat_type: str = "anime") -> discord.Embed:
    """
    Create Discord embed for detailed statistics.
    """
    emoji = "📺" if stat_type == "anime" else "📖"
    title = f"{emoji} {username}'s {stat_type.title()} Statistics"
    
    embed = discord.Embed(
        title=title,
        color=discord.Color.blue()
    )
    
    stats = statistics.get(stat_type, {})
    if not stats or stats.get("count", 0) == 0:
        embed.description = f"No {stat_type} statistics found."
        return embed
    
    # Basic stats
    count = stats.get("count", 0)
    mean_score = stats.get("mean_score", 0)
    embed.add_field(name="Total Count", value=f"{count:,}", inline=True)
    
    if mean_score > 0:
        embed.add_field(name="Mean Score", value=f"{mean_score:.1f}/100", inline=True)
    
    # Completion rate
    completion_rate = calculate_completion_rate(stats.get("statuses", []), stat_type)
    if completion_rate > 0:
        embed.add_field(name="Completion Rate", value=f"{completion_rate:.1f}%", inline=True)
    
    # Top genres
    top_genres = get_top_genres(stats.get("genres", []), limit=5)
    if top_genres:
        genre_text = "\n".join([f"{genre}: {count}" for genre, count in top_genres])
        embed.add_field(name="Top Genres", value=genre_text, inline=True)
    
    # Status distribution
    status_dist = get_status_distribution(stats.get("statuses", []))
    if status_dist:
        status_text = "\n".join([f"{status.title()}: {count}" for status, count in status_dist.items()])
        embed.add_field(name="Status Distribution", value=status_text, inline=True)
    
    return embed


def create_favorites_embed(username: str, favorites: Dict, favorite_type: str = "anime") -> discord.Embed:
    """
    Create Discord embed for favorites.
    """
    type_emojis = {
        "anime": "📺",
        "manga": "📖",
        "characters": "👤",
        "studios": "🎬",
        "staff": "🎭"
    }
    
    emoji = type_emojis.get(favorite_type, "⭐")
    title = f"{emoji} {username}'s Favorite {favorite_type.title()}"
    
    embed = discord.Embed(
        title=title,
        color=discord.Color.gold()
    )
    
    items = favorites.get(favorite_type, [])
    if not items:
        embed.description = f"No favorite {favorite_type} found."
        return embed
    
    # Display favorites
    if favorite_type in ["anime", "manga"]:
        description_parts = []
        for i, item in enumerate(items[:10], 1):
            title = format_title_for_display(item.get("title", "Unknown"), 40)
            site_url = item.get("site_url", "")
            
            if site_url:
                description_parts.append(f"{i}. [{title}]({site_url})")
            else:
                description_parts.append(f"{i}. {title}")
        
        embed.description = "\n".join(description_parts)
    
    elif favorite_type == "characters":
        description_parts = []
        for i, character in enumerate(items[:10], 1):
            name = character.get("name", "Unknown")
            site_url = character.get("site_url", "")
            
            if site_url:
                description_parts.append(f"{i}. [{name}]({site_url})")
            else:
                description_parts.append(f"{i}. {name}")
        
        embed.description = "\n".join(description_parts)
    
    elif favorite_type in ["studios", "staff"]:
        description_parts = []
        for i, item in enumerate(items[:10], 1):
            name = item.get("name", "Unknown")
            site_url = item.get("site_url", "")
            
            if site_url:
                description_parts.append(f"{i}. [{name}]({site_url})")
            else:
                description_parts.append(f"{i}. {name}")
        
        embed.description = "\n".join(description_parts)
    
    return embed


# ===== FORMAT UTILITIES =====

def format_status_text(status: str) -> str:
    """
    Format status text for display.
    """
    status_map = {
        "CURRENT": "Currently Watching/Reading",
        "COMPLETED": "Completed",
        "PAUSED": "Paused",
        "DROPPED": "Dropped",
        "PLANNING": "Planning to Watch/Read",
        "REPEATING": "Rewatching/Rereading"
    }
    
    return status_map.get(status.upper(), status.title())


def format_format_text(format_name: str) -> str:
    """
    Format media format text for display.
    """
    format_map = {
        "TV": "TV Series",
        "TV_SHORT": "TV Short",
        "MOVIE": "Movie",
        "SPECIAL": "Special",
        "OVA": "OVA",
        "ONA": "ONA",
        "MUSIC": "Music Video",
        "MANGA": "Manga",
        "NOVEL": "Light Novel",
        "ONE_SHOT": "One Shot"
    }
    
    return format_map.get(format_name.upper(), format_name.title())


def format_score(score: Optional[Union[int, float]]) -> str:
    """
    Format score for display.
    """
    if score is None or score == 0:
        return "Not Rated"
    
    if isinstance(score, float):
        return f"{score:.1f}/100"
    else:
        return f"{score}/100"


def format_progress(current: Optional[int], total: Optional[int], media_type: str = "anime") -> str:
    """
    Format progress for display.
    """
    if current is None:
        return "No progress"
    
    unit = "episodes" if media_type == "anime" else "chapters"
    
    if total is None or total == 0:
        return f"{current} {unit}"
    else:
        return f"{current}/{total} {unit}"


# ===== USER PREFERENCES =====

def get_user_preferences(user_data: Dict) -> Dict[str, Any]:
    """
    Extract user preferences from AniList data.
    """
    options = user_data.get("options", {})
    
    return {
        "title_language": options.get("titleLanguage", "romaji"),
        "display_adult_content": options.get("displayAdultContent", False),
        "scoring_system": options.get("scoreFormat", "POINT_100"),
        "timezone": options.get("timezone"),
        "activity_merge_time": options.get("activityMergeTime")
    }


def should_prefer_english_titles(user_data: Dict) -> bool:
    """
    Check if user prefers English titles.
    """
    preferences = get_user_preferences(user_data)
    return preferences.get("title_language") == "english"


# ===== DATA VALIDATION =====

def validate_user_data(user_data: Dict) -> bool:
    """
    Validate user data structure.
    """
    required_fields = ["id", "name"]
    
    for field in required_fields:
        if field not in user_data or not user_data[field]:
            logger.warning(f"Missing required field in user data: {field}")
            return False
    
    return True


def validate_statistics_data(statistics: Dict) -> bool:
    """
    Validate statistics data structure.
    """
    if not statistics:
        return False
    
    # Check for anime or manga stats
    has_anime = "anime" in statistics and isinstance(statistics["anime"], dict)
    has_manga = "manga" in statistics and isinstance(statistics["manga"], dict)
    
    return has_anime or has_manga


# ===== ACHIEVEMENT PROCESSING =====

def generate_progress_bar(current: int, target: int, bar_length: int = 10) -> str:
    """
    Generate progress bar string for achievements.
    
    Args:
        current: Current value
        target: Target value
        bar_length: Length of progress bar (default 10)
    
    Returns:
        Progress bar string with filled and empty blocks
    """
    if target == 0:
        return "░" * bar_length
    
    filled = min(bar_length, max(0, int(current / target * bar_length)))
    return "█" * filled + "░" * (bar_length - filled)


def check_milestone_achievements(
    current: int,
    milestones: List[Tuple[int, str]],
    achieved: List[str],
    progress: List[str]
) -> None:
    """
    Check milestone achievements and add to achieved/progress lists.
    
    Args:
        current: Current value to check
        milestones: List of (threshold, title) tuples sorted by threshold
        achieved: List to append achieved achievements to
        progress: List to append progress achievements to
    """
    for threshold, title in milestones:
        if current >= threshold:
            achieved.append(title)
        else:
            prog_bar = generate_progress_bar(current, threshold)
            progress.append(f"{title}\n`{prog_bar}` {current}/{threshold}")
            break


def check_score_achievements(
    current_score: float,
    completed_count: int,
    min_completed: int,
    milestones: List[Tuple[float, str]],
    achieved: List[str],
    progress: List[str],
    label: str = ""
) -> None:
    """
    Check score-based achievements.
    
    Args:
        current_score: Current average score
        completed_count: Number of completed entries
        min_completed: Minimum completed entries required
        milestones: List of (threshold, title) tuples sorted by threshold
        achieved: List to append achieved achievements to
        progress: List to append progress achievements to
        label: Label for the achievement (e.g., "Manga", "Anime")
    """
    if completed_count < min_completed:
        return
    
    for threshold, title in milestones:
        if current_score >= threshold:
            achieved.append(f"{title} ({label}: {current_score:.1f})")
        else:
            next_threshold = next((t for t, _ in milestones if t > current_score), None)
            if next_threshold:
                prog_bar = generate_progress_bar(int(current_score * 10), int(next_threshold * 10))
                next_title = next(title for t, title in milestones if t == next_threshold)
                progress.append(f"{next_title} ({label})\n`{prog_bar}` {current_score:.1f}/{next_threshold}")
            break


def calculate_format_distribution(
    manga_stats: dict,
    anime_stats: dict
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Calculate format distributions for manga and anime.
    Uses country data to distinguish Manga/Manhwa/Manhua.
    Adjusts counts to exclude planning entries.
    
    Args:
        manga_stats: Manga statistics dict
        anime_stats: Anime statistics dict
    
    Returns:
        Tuple of (manga_format_distribution, anime_format_distribution)
    """
    # Manga format distribution
    total_manga = manga_stats.get("count", 0)
    m_planning = sum(s.get("count", 0) for s in manga_stats.get("statuses", []) 
                     if s.get("status") == "PLANNING")
    manga_planning_ratio = m_planning / total_manga if total_manga > 0 else 0
    
    logger.debug(f"Manga planning ratio: {manga_planning_ratio} (planning: {m_planning}, total: {total_manga})")
    
    format_distribution = {
        "Manga": 0,      # Japan
        "Manhwa": 0,     # South Korea
        "Manhua": 0,     # China
        "Light Novel": 0,
        "Novel": 0,
        "One Shot": 0,
        "Doujinshi": 0
    }
    
    # Process country data to get Manga/Manhwa/Manhua distinction
    for country_data in manga_stats.get("countries", []):
        country = country_data.get("country", "Unknown")
        count = country_data.get("count", 0)
        adjusted_count = int(count * (1 - manga_planning_ratio))
        logger.debug(f"Processing manga country: {country} with count: {count} -> adjusted: {adjusted_count}")
        
        if country == "JP":  # Japan
            format_distribution["Manga"] += adjusted_count
        elif country == "KR":  # South Korea
            format_distribution["Manhwa"] += adjusted_count
        elif country == "CN":  # China
            format_distribution["Manhua"] += adjusted_count
        else:
            format_distribution["Manga"] += adjusted_count
            logger.debug(f"Unknown country {country}, adding to Manga category")
    
    # Process format data for other types (Light Novel, Novel, One Shot, etc.)
    for f in manga_stats.get("formats", []):
        format_name = f.get("format", "Unknown")
        count = f.get("count", 0)
        adjusted_count = int(count * (1 - manga_planning_ratio))
        logger.debug(f"Processing manga format: {format_name} with count: {count} -> adjusted: {adjusted_count}")
        
        if format_name == "LIGHT_NOVEL":
            format_distribution["Light Novel"] = adjusted_count
        elif format_name == "NOVEL":
            format_distribution["Novel"] = adjusted_count
        elif format_name == "ONE_SHOT":
            format_distribution["One Shot"] = adjusted_count
        elif format_name == "DOUJINSHI":
            format_distribution["Doujinshi"] = adjusted_count
    
    logger.debug(f"Final manga format_distribution (excluding planning): {format_distribution}")
    
    # Anime format distribution
    total_anime = anime_stats.get("count", 0)
    a_planning = sum(s.get("count", 0) for s in anime_stats.get("statuses", []) 
                     if s.get("status") == "PLANNING")
    anime_planning_ratio = a_planning / total_anime if total_anime > 0 else 0
    
    logger.debug(f"Anime planning ratio: {anime_planning_ratio} (planning: {a_planning}, total: {total_anime})")
    
    anime_format_distribution = {}
    format_map = {
        "TV": "TV Series",
        "MOVIE": "Movie",
        "OVA": "OVA",
        "ONA": "ONA",
        "SPECIAL": "Special",
        "TV_SHORT": "TV Short",
        "MUSIC": "Music Video"
    }
    
    for f in anime_stats.get("formats", []):
        format_name = f.get("format", "Unknown")
        count = f.get("count", 0)
        adjusted_count = int(count * (1 - anime_planning_ratio))
        logger.debug(f"Processing anime format: {format_name} with count: {count} -> adjusted: {adjusted_count}")
        
        format_display = format_map.get(format_name, format_name.replace("_", " ").title())
        anime_format_distribution[format_display] = adjusted_count
    
    logger.debug(f"Final anime format_distribution (excluding planning): {anime_format_distribution}")
    
    return format_distribution, anime_format_distribution


def calculate_achievements(statistics: Dict) -> List[Dict[str, Any]]:
    """
    Calculate user achievements based on statistics.
    """
    achievements = []
    
    anime_stats = statistics.get("anime", {})
    manga_stats = statistics.get("manga", {})
    
    # Anime achievements
    anime_count = anime_stats.get("count", 0)
    if anime_count >= 100:
        achievements.append({
            "name": "Anime Enthusiast",
            "description": "Watched 100+ anime",
            "icon": "📺",
            "progress": anime_count,
            "target": 100
        })
    
    if anime_count >= 500:
        achievements.append({
            "name": "Anime Expert",
            "description": "Watched 500+ anime",
            "icon": "🏆",
            "progress": anime_count,
            "target": 500
        })
    
    # Manga achievements
    manga_count = manga_stats.get("count", 0)
    if manga_count >= 50:
        achievements.append({
            "name": "Manga Reader",
            "description": "Read 50+ manga",
            "icon": "📖",
            "progress": manga_count,
            "target": 50
        })
    
    if manga_count >= 200:
        achievements.append({
            "name": "Manga Collector",
            "description": "Read 200+ manga",
            "icon": "📚",
            "progress": manga_count,
            "target": 200
        })
    
    # Score achievements
    anime_mean = anime_stats.get("mean_score", 0)
    if anime_mean >= 80:
        achievements.append({
            "name": "Critic",
            "description": "High mean anime score (80+)",
            "icon": "⭐",
            "progress": anime_mean,
            "target": 80
        })
    
    return achievements