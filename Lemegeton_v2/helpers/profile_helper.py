"""
Profile Helper Functions
Centralized functions for user profile management, statistics, and AniList profile processing
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


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


# ===== FAVORITES PROCESSING =====


# ===== TITLE UTILITIES =====


# ===== DISCORD EMBED UTILITIES =====


# ===== FORMAT UTILITIES =====


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


# ===== USER PREFERENCES =====


# ===== DATA VALIDATION =====


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

