import discord
from discord.ext import commands
import logging
import math
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from config import ALL_STAR_STAGE1_ROLE_ID, ALL_STAR_STAGE2_ROLE_ID, ALL_STAR_COMPLETED_ROLE_ID

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "challenge_helper.log"
VALID_COMPLETION_STATUSES = {"Completed", "Caught Up", "Reread", "Skipped"}
MAX_BONUS_POINTS = 150
BONUS_PERCENTAGE = 0.1

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging with auto-clearing
logger = logging.getLogger("ChallengeHelper")
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

logger.info("Challenge Helper logging system initialized")

# Difficulty calculation constants
# ✅ Rebalanced with filled gaps for more granular difficulty assessment
DIFFICULTY_THRESHOLDS = [
    (25, 1.0),      # Very short
    (50, 1.5),      # Short
    (100, 2.0),     # Medium
    (200, 2.5),     # Long
    (300, 3.0),     # Very long
    (400, 3.25),    # ✅ Fill gap
    (500, 3.5),     # Epic
    (750, 3.75),    # ✅ Fill gap
    (1000, 4.0),    # Massive
    (1250, 4.15),   # ✅ Fill gap
    (1500, 4.3),    # Huge
    (1750, 4.45),   # ✅ Fill gap
    (2000, 4.6),    # Gigantic
    (float('inf'), 5.0)  # One Piece territory
]

# ✅ Reduced multiplier impact - was too subjective at 10% difference
MEDIUM_TYPE_MULTIPLIERS = {
    "manga": 1.05,    # Reduced from 1.1 (5% instead of 10%)
    "manhwa": 1.0,    # Baseline
    "manhua": 0.95    # Reduced from 0.9 (5% instead of 10%)
}

DIFFICULTY_LABELS = [
    (1.5, "Easy"),
    (2.5, "Medium"),
    (3.5, "Hard"),
    (4.5, "Very Hard"),
    (float('inf'), "Extreme")
]

async def get_manga_difficulty(total_chapters: int, medium_type: str = "manga") -> float:
    """
    Calculate numeric difficulty score for a single manga based on chapters and medium type.
    Returns a float score (1-5 scale, higher for longer titles and Manga > Manhwa > Manhua).
    """
    logger.debug(f"Calculating difficulty for {total_chapters} chapters, type: {medium_type}")
    
    try:
        # Validate input
        if not isinstance(total_chapters, int) or total_chapters < 0:
            logger.warning(f"Invalid total_chapters value: {total_chapters}, defaulting to 0")
            total_chapters = 0
            
        if not isinstance(medium_type, str):
            logger.warning(f"Invalid medium_type value: {medium_type}, defaulting to 'manga'")
            medium_type = "manga"
            
        # Calculate base score using threshold lookup
        base_score = 1.0
        for threshold, score in DIFFICULTY_THRESHOLDS:
            if total_chapters <= threshold:
                base_score = score
                break
                
        logger.debug(f"Base score for {total_chapters} chapters: {base_score}")
        
        # Apply medium type multiplier
        multiplier = MEDIUM_TYPE_MULTIPLIERS.get(medium_type.lower(), 1.0)
        if multiplier != MEDIUM_TYPE_MULTIPLIERS.get(medium_type.lower(), None):
            logger.debug(f"Unknown medium type '{medium_type}', using default multiplier 1.0")
            
        adjusted_score = base_score * multiplier
        final_score = min(5.0, adjusted_score)
        
        logger.info(f"Difficulty calculated: {total_chapters} {medium_type} chapters = {final_score:.2f}")
        return final_score
        
    except Exception as e:
        logger.error(f"Error calculating manga difficulty: {e}", exc_info=True)
        return 2.0  # Default fallback difficulty

async def get_challenge_difficulty(db, challenge_id: int, guild_id: int = None) -> str:
    """
    Calculate overall difficulty for a challenge based on all manga in it.

    Uses Method 2 (Balanced): (avg_chapters / 100) * (manga_count / 10)

    This replaces the old "average difficulty score" method with a more
    accurate calculation based on actual challenge data analysis.

    Returns a difficulty string: Easy / Medium / Hard / Very Hard / Extreme
    """
    logger.info(f"Calculating challenge difficulty for challenge ID: {challenge_id}")

    try:
        # Validate input
        if not isinstance(challenge_id, int) or challenge_id <= 0:
            logger.error(f"Invalid challenge_id: {challenge_id}")
            return "Medium"

        # Query for guild-specific or global challenge manga
        if guild_id:
            logger.debug(f"Querying guild_challenge_manga for guild {guild_id}, challenge {challenge_id}")
            cursor = await db.execute("""
                SELECT COUNT(*) as manga_count, AVG(total_chapters) as avg_chapters
                FROM guild_challenge_manga
                WHERE guild_id = ? AND challenge_id = ?
            """, (guild_id, challenge_id))
        else:
            logger.debug(f"Querying challenge_manga for challenge {challenge_id}")
            cursor = await db.execute("""
                SELECT COUNT(*) as manga_count, AVG(total_chapters) as avg_chapters
                FROM challenge_manga
                WHERE challenge_id = ?
            """, (challenge_id,))

        row = await cursor.fetchone()
        await cursor.close()

        if not row or row[0] == 0:
            logger.warning(f"No manga found for challenge {challenge_id}, returning default difficulty")
            return "Medium"

        manga_count = row[0]
        avg_chapters = row[1] or 0

        logger.debug(f"Found {manga_count} manga entries with avg {avg_chapters:.1f} chapters")

        # ✅ New Formula: (avg_chapters / 100) * (manga_count / 10)
        difficulty_score = (avg_chapters / 100.0) * (manga_count / 10.0)

        logger.debug(f"Difficulty score: {difficulty_score:.2f} = ({avg_chapters}/100) * ({manga_count}/10)")

        # Determine difficulty label based on score
        if difficulty_score < 0.8:
            difficulty_label = "Easy"
        elif difficulty_score < 1.5:
            difficulty_label = "Medium"
        elif difficulty_score < 2.5:
            difficulty_label = "Hard"
        elif difficulty_score < 4.0:
            difficulty_label = "Very Hard"
        else:
            difficulty_label = "Extreme"

        logger.info(f"Challenge {challenge_id} difficulty: {difficulty_label} (score: {difficulty_score:.2f}, {manga_count} manga, {avg_chapters:.1f} avg chapters)")
        return difficulty_label

    except Exception as e:
        logger.error(f"Error calculating challenge difficulty for {challenge_id}: {e}", exc_info=True)
        return "Medium"  # Safe fallback


# -----------------------------
# Points Calculation
# -----------------------------
# Points calculation constants
STATUS_MULTIPLIERS = {
    "Completed": 1.2,
    "Caught Up": 1.2,
    "Skipped": 0.3,    
    "Dropped": 0.3,
    "Paused": 0.5,     
    "In Progress": 0.8,
    "Not Started": 0,
    "Reread": 1.5       
}

# ✅ Rebalanced with square root scaling to prevent short manga exploitation
# Formula: base_points = 10 * sqrt(chapters / 25)
# This provides more balanced scaling between short and long manga
CHAPTER_BASE_POINTS = {
    25: 10,      # 10 * sqrt(25/25) = 10
    50: 14,      # 10 * sqrt(50/25) = 14.1
    100: 20,     # 10 * sqrt(100/25) = 20
    250: 32,     # 10 * sqrt(250/25) = 31.6
    500: 45,     # 10 * sqrt(500/25) = 44.7
    1000: 63,    # 10 * sqrt(1000/25) = 63.2
    2000: 89,    # 10 * sqrt(2000/25) = 89.4
    float('inf'): 120  # Cap for extreme cases
}

def calculate_manga_points(
    total_chapters: int,
    chapters_read: int,
    status: str,
    difficulty: float,
    repeat_count: int = 0
) -> int:
    """
    Calculate points for a single manga based on chapters, status, difficulty, and reread count with logging.
    """
    logger.debug(f"Calculating points: {total_chapters}ch, {chapters_read} read, {status}, diff: {difficulty}, repeats: {repeat_count}")
    
    try:
        # Validate inputs
        if not isinstance(total_chapters, int) or total_chapters < 0:
            logger.warning(f"Invalid total_chapters: {total_chapters}, using 0")
            total_chapters = 0
            
        if not isinstance(chapters_read, int) or chapters_read < 0:
            logger.warning(f"Invalid chapters_read: {chapters_read}, using 0")
            chapters_read = 0
            
        if not isinstance(difficulty, (int, float)) or difficulty <= 0:
            logger.warning(f"Invalid difficulty: {difficulty}, using 3.0")
            difficulty = 3.0
            
        if not isinstance(repeat_count, int) or repeat_count < 0:
            logger.warning(f"Invalid repeat_count: {repeat_count}, using 0")
            repeat_count = 0
            
        # Determine base points from chapter count
        base_points = CHAPTER_BASE_POINTS[float('inf')]  # Default to highest
        for threshold, points in CHAPTER_BASE_POINTS.items():
            if total_chapters < threshold:
                base_points = points
                break
                
        logger.debug(f"Base points for {total_chapters} chapters: {base_points}")
        
        # Get status multiplier
        if status == "Reread":
            # ✅ Cap at 1 reread to prevent infinite scaling
            effective_rereads = min(repeat_count, 1)
            multiplier = 1.5 + max(effective_rereads - 1, 0) * 0.3
            if repeat_count > 1:
                logger.debug(f"Reread multiplier: {multiplier} (repeat count: {repeat_count}, capped at {effective_rereads})")
            else:
                logger.debug(f"Reread multiplier: {multiplier} (repeat count: {repeat_count})")
        else:
            multiplier = STATUS_MULTIPLIERS.get(status, 0)
            if status not in STATUS_MULTIPLIERS:
                logger.warning(f"Unknown status '{status}', using 0 multiplier")
            logger.debug(f"Status multiplier for '{status}': {multiplier}")

        # ✅ Apply balanced difficulty scaling (0.8x to 1.3x range instead of arbitrary /3.0)
        # Old: difficulty / 3.0 gave 0.33x to 1.67x (too extreme)
        # New: 0.8 + (difficulty / 10.0) gives 0.9x to 1.3x (more balanced)
        difficulty_factor = 0.8 + (difficulty / 10.0)
        logger.debug(f"Difficulty factor: {difficulty_factor:.2f} (difficulty: {difficulty:.2f})")

        # Calculate base points
        points = base_points * multiplier * difficulty_factor

        # ✅ Apply partial completion for all incomplete statuses (including Skipped)
        if status in ["In Progress", "Paused", "Dropped", "Skipped"] and total_chapters > 0:
            completion_ratio = min(chapters_read / total_chapters, 1.0)
            points *= completion_ratio
            logger.debug(f"{status} completion ratio: {completion_ratio:.2f} ({chapters_read}/{total_chapters} chapters)")
        
        final_points = max(0, round(points))
        logger.info(f"Points calculated: {total_chapters}ch {status} (diff: {difficulty:.1f}) = {final_points} points")
        
        return final_points
        
    except Exception as e:
        logger.error(f"Error calculating manga points: {e}", exc_info=True)
        return 0

def calculate_challenge_completion_bonus(user_progress: list) -> int:
    """
    Calculate bonus points for completing a challenge with comprehensive logging.
    Returns bonus points if all manga in the challenge are marked as completed statuses.
    """
    logger.debug(f"Calculating completion bonus for {len(user_progress)} progress entries")
    
    try:
        if not user_progress:
            logger.warning("No user progress data provided")
            return 0
            
        if not isinstance(user_progress, list):
            logger.error(f"Invalid user_progress type: {type(user_progress)}")
            return 0
        
        # Check completion status for all entries
        completed_entries = []
        incomplete_entries = []
        
        for i, entry in enumerate(user_progress):
            if not isinstance(entry, dict):
                logger.warning(f"Entry {i} is not a dict: {type(entry)}")
                continue
                
            status = entry.get("status", "Unknown")
            if status in VALID_COMPLETION_STATUSES:
                completed_entries.append(entry)
            else:
                incomplete_entries.append((i, status))
                
        logger.debug(f"Completed entries: {len(completed_entries)}, Incomplete: {len(incomplete_entries)}")
        
        if incomplete_entries:
            logger.debug(f"Incomplete statuses found: {[status for _, status in incomplete_entries]}")
            return 0
            
        # Calculate total points from completed entries
        total_points = 0
        for entry in completed_entries:
            entry_points = entry.get("points", 0)
            if isinstance(entry_points, (int, float)):
                total_points += entry_points
            else:
                logger.warning(f"Invalid points value in entry: {entry_points}")
                
        logger.debug(f"Total points from entries: {total_points}")
        
        if total_points <= 0:
            logger.warning("No valid points found in progress entries")
            return 0
            
        # Calculate bonus (10% of total points, capped at 150)
        bonus_percentage = 0.1
        bonus_points = round(total_points * bonus_percentage)
        final_bonus = min(bonus_points, MAX_BONUS_POINTS)
        
        logger.info(f"Challenge completion bonus: {final_bonus} points ({bonus_percentage*100}% of {total_points}, capped at {MAX_BONUS_POINTS})")
        return final_bonus
        
    except Exception as e:
        logger.error(f"Error calculating challenge completion bonus: {e}", exc_info=True)
        return 0


# -----------------------------
# Role Assignment
# -----------------------------
async def assign_challenge_role(bot: commands.Bot, discord_id: int, guild_id: int, challenge_id: int, challenge_progress: list):
    """
    Assign role for a specific challenge based on user's progress with comprehensive logging.
    Only assigns role when all titles are completed, caught up, reread, or skipped.

    Args:
        bot: Discord bot instance
        discord_id: Discord user ID
        guild_id: Guild ID for multi-guild support
        challenge_id: Challenge ID
        challenge_progress: List of progress entries with status information

    Returns:
        List of roles that were assigned
    """
    logger.info(f"Assigning challenge role for user {discord_id}, guild {guild_id}, challenge {challenge_id}")
    assigned_roles = []

    try:
        # Validate inputs
        if not isinstance(discord_id, int) or discord_id <= 0:
            logger.error(f"Invalid discord_id: {discord_id}")
            return assigned_roles

        if not isinstance(guild_id, int) or guild_id <= 0:
            logger.error(f"Invalid guild_id: {guild_id}")
            return assigned_roles

        if not isinstance(challenge_id, int) or challenge_id <= 0:
            logger.error(f"Invalid challenge_id: {challenge_id}")
            return assigned_roles

        if not isinstance(challenge_progress, list):
            logger.error(f"Invalid challenge_progress type: {type(challenge_progress)}")
            return assigned_roles

        # Import database function to get guild-specific challenge roles
        from database import get_challenge_role_ids_for_guild

        # Get challenge role configuration for this guild
        challenge_role_ids = await get_challenge_role_ids_for_guild(guild_id)

        # Check if challenge has role assignments configured
        if challenge_id not in challenge_role_ids:
            logger.debug(f"No role configuration found for challenge {challenge_id} in guild {guild_id}")
            return assigned_roles

        total_titles = len(challenge_progress)
        logger.debug(f"Total titles in challenge: {total_titles}")
        
        if total_titles == 0:
            logger.warning(f"No titles found in challenge progress for challenge {challenge_id}")
            return assigned_roles

        # Check completion status
        completed_entries = []
        incomplete_entries = []
        
        for i, entry in enumerate(challenge_progress):
            if not isinstance(entry, dict):
                logger.warning(f"Progress entry {i} is not a dict: {type(entry)}")
                continue
                
            status = entry.get("status", "Unknown")
            if status in VALID_COMPLETION_STATUSES:
                completed_entries.append(entry)
                logger.debug(f"Entry {i}: {status} (completed)")
            else:
                incomplete_entries.append((i, status))
                logger.debug(f"Entry {i}: {status} (incomplete)")
        
        completed_count = len(completed_entries)
        logger.debug(f"Completion status: {completed_count}/{total_titles} completed")
        
        if completed_count != total_titles:
            logger.info(f"Challenge {challenge_id} not fully completed by user {discord_id} ({completed_count}/{total_titles})")
            return assigned_roles

        # Determine role to assign
        thresholds = challenge_role_ids[challenge_id]
        completion_percentage = 1.0  # 100% completion

        role_to_assign = None
        for threshold in sorted(thresholds.keys(), reverse=True):
            if completion_percentage >= threshold:
                role_to_assign = thresholds[threshold]
                logger.debug(f"Role selected: {role_to_assign} for threshold {threshold}")
                break

        if not role_to_assign:
            logger.warning(f"No role found for completion percentage {completion_percentage}")
            return assigned_roles

        # Get Discord guild and member
        logger.debug(f"Getting guild {guild_id}")
        guild = bot.get_guild(guild_id)
        if not guild:
            logger.error(f"Guild {guild_id} not found")
            return assigned_roles

        logger.debug(f"Getting member {discord_id}")
        member = guild.get_member(discord_id)
        if not member:
            logger.warning(f"Member {discord_id} not found in guild {guild_id}")
            return assigned_roles

        # Remove other challenge roles first
        existing_challenge_roles = [r for r in member.roles if r.id in thresholds.values() and r.id != role_to_assign]
        if existing_challenge_roles:
            logger.debug(f"Removing {len(existing_challenge_roles)} existing challenge roles")
            try:
                await member.remove_roles(*existing_challenge_roles, reason=f"Challenge {challenge_id} role update")
                logger.info(f"Removed roles: {[r.name for r in existing_challenge_roles]}")
            except Exception as e:
                logger.error(f"Failed to remove existing roles: {e}")

        # Add new role
        role = guild.get_role(role_to_assign)
        if not role:
            logger.error(f"Role {role_to_assign} not found in guild")
            return assigned_roles
            
        if role in member.roles:
            logger.debug(f"User {discord_id} already has role {role.name}")
            return assigned_roles

        try:
            await member.add_roles(role, reason=f"Completed Challenge {challenge_id}")
            assigned_roles.append(role)
            logger.info(f"Assigned role '{role.name}' to user {discord_id} for challenge {challenge_id}")
            
            # Send congratulatory message
            try:
                await member.send(
                    f"🎉 Congratulations! You've completed Challenge {challenge_id} and have been awarded the role **{role.name}**!"
                )
                logger.debug(f"Sent congratulatory message to user {discord_id}")
            except discord.Forbidden:
                logger.debug(f"Could not send DM to user {discord_id} (DMs disabled)")
            except Exception as dm_error:
                logger.warning(f"Failed to send congratulatory message: {dm_error}")
                
        except Exception as e:
            logger.error(f"Failed to assign role {role.name} to user {discord_id}: {e}")

            # Enforce mutual-exclusion for All Star roles using role IDs if configured
            try:
                to_remove_ids = []
                # If we have role IDs configured, use them for removal
                if ALL_STAR_COMPLETED_ROLE_ID and role.id == ALL_STAR_COMPLETED_ROLE_ID:
                    if ALL_STAR_STAGE2_ROLE_ID:
                        to_remove_ids.append(ALL_STAR_STAGE2_ROLE_ID)
                elif ALL_STAR_STAGE2_ROLE_ID and role.id == ALL_STAR_STAGE2_ROLE_ID:
                    if ALL_STAR_STAGE1_ROLE_ID:
                        to_remove_ids.append(ALL_STAR_STAGE1_ROLE_ID)

                # If no IDs configured or no matches, fall back to name-based checks
                if not to_remove_ids:
                    if role.name == "All Star Completed":
                        for r in member.roles:
                            if r.name == "All Star Stage 2":
                                to_remove_ids.append(r.id)
                    elif role.name == "All Star Stage 2":
                        for r in member.roles:
                            if r.name == "All Star Stage 1":
                                to_remove_ids.append(r.id)

                if to_remove_ids:
                    roles_to_remove = [guild.get_role(rid) for rid in to_remove_ids if guild.get_role(rid) is not None]
                    if roles_to_remove:
                        try:
                            await member.remove_roles(*roles_to_remove, reason="Mutual exclusion for All Star roles")
                            logger.info(f"Removed mutually exclusive roles {[r.name for r in roles_to_remove]} from user {discord_id}")
                        except Exception as rem_err:
                            logger.error(f"Failed to remove mutually exclusive roles for user {discord_id}: {rem_err}")
            except Exception as e:
                logger.debug(f"No mutual-exclusion role changes required or error occurred: {e}")

        return assigned_roles
        
    except Exception as e:
        logger.error(f"Error in assign_challenge_role: {e}", exc_info=True)
        return assigned_roles

