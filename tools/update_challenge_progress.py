#!/usr/bin/env python3
"""
Update Challenge Progress Script

Updates a user's challenge progress by fetching data from AniList and updating the database.
Respects AniList's rate limit of 25 requests per minute (2.4s per request).

Usage:
    python tools/update_challenge_progress.py <discord_id> <guild_id>
    python tools/update_challenge_progress.py 123456789 987654321

Options:
    --dry-run    Show what would be updated without making changes
    --verbose    Show detailed progress information
"""

import asyncio
import aiohttp
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import (
    execute_db_operation,
    upsert_user_manga_progress_guild_aware,
)
from helpers.challenge_helper import (
    get_manga_difficulty,
    calculate_manga_points,
)

# Configuration
ANILIST_API = "https://graphql.anilist.co"
RATE_LIMIT_DELAY = 2.4  # 25 requests per minute = 2.4 seconds per request
REQUEST_TIMEOUT = 10  # seconds


class ProgressTracker:
    """Track and display progress of the update operation."""

    def __init__(self, total_manga: int, verbose: bool = False):
        self.total_manga = total_manga
        self.processed = 0
        self.updated = 0
        self.errors = 0
        self.start_time = datetime.now()
        self.verbose = verbose

    def increment(self, updated: bool = True, error: bool = False):
        """Increment counters and display progress."""
        self.processed += 1
        if updated:
            self.updated += 1
        if error:
            self.errors += 1

        # Show progress every 10 manga or on completion
        if self.processed % 10 == 0 or self.processed == self.total_manga:
            self._display_progress()

    def _display_progress(self):
        """Display current progress."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = self.processed / elapsed if elapsed > 0 else 0
        remaining = (self.total_manga - self.processed) / rate if rate > 0 else 0

        print(f"\r📊 Progress: {self.processed}/{self.total_manga} "
              f"({self.processed/self.total_manga*100:.1f}%) | "
              f"✅ {self.updated} updated | "
              f"❌ {self.errors} errors | "
              f"⏱️ ETA: {int(remaining)}s", end="", flush=True)

    def finish(self):
        """Display final summary."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        print(f"\n\n{'='*60}")
        print(f"✅ Update Complete!")
        print(f"{'='*60}")
        print(f"Total Manga: {self.total_manga}")
        print(f"Updated: {self.updated}")
        print(f"Errors: {self.errors}")
        print(f"Time Taken: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        print(f"Average Rate: {self.processed/elapsed:.2f} manga/second")
        print(f"{'='*60}\n")


async def fetch_anilist_info(discord_id: int) -> Optional[Dict]:
    """
    Fetch AniList account information for a Discord user.

    Args:
        discord_id: Discord user ID

    Returns:
        Dictionary with 'id' and 'username' keys, or None if not linked
    """
    row = await execute_db_operation(
        "get anilist info",
        "SELECT anilist_id, anilist_username FROM users WHERE discord_id = ?",
        (discord_id,),
        fetch_type='one'
    )

    if not row:
        return None

    anilist_id, anilist_username = row
    if not anilist_id and not anilist_username:
        return None

    return {"id": anilist_id, "username": anilist_username}


async def fetch_anilist_manga_progress(
    session: aiohttp.ClientSession,
    anilist_id: int,
    manga_id: int
) -> Dict:
    """
    Fetch AniList progress for a specific manga.

    Args:
        session: aiohttp session
        anilist_id: AniList user ID
        manga_id: AniList manga ID

    Returns:
        Dictionary with progress, status, repeat, started_at, media_status, medium_type
    """
    query = """
    query ($userId: Int, $mediaId: Int) {
      MediaList(userId: $userId, mediaId: $mediaId) {
        progress
        status
        repeat
        startedAt { year month day }
        media {
          status
          format
        }
      }
    }
    """
    variables = {"userId": anilist_id, "mediaId": manga_id}

    try:
        async with session.post(
            ANILIST_API,
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        ) as resp:
            if resp.status == 429:  # Rate limited
                retry_after = int(resp.headers.get('Retry-After', 60))
                print(f"\n⚠️ Rate limited! Waiting {retry_after}s...")
                await asyncio.sleep(retry_after)
                return await fetch_anilist_manga_progress(session, anilist_id, manga_id)

            if resp.status != 200:
                return {
                    "progress": 0, "status": "CURRENT", "repeat": 0,
                    "started_at": None, "media_status": None, "medium_type": "manga"
                }

            data = await resp.json()
            media_list = data.get("data", {}).get("MediaList")

            if not media_list:
                return {
                    "progress": 0, "status": "CURRENT", "repeat": 0,
                    "started_at": None, "media_status": None, "medium_type": "manga"
                }

            # Extract progress data
            progress = media_list.get("progress", 0)
            status = media_list.get("status", "CURRENT")
            repeat = media_list.get("repeat", 0)

            # Parse started date
            started = media_list.get("startedAt")
            started_at = None
            if started and started.get("year"):
                started_at = f"{started['year']:04}-{started.get('month', 1):02}-{started.get('day', 1):02}"

            # Get media metadata
            media = media_list.get("media", {})
            media_status = media.get("status") if media else None

            # Normalize medium type
            medium_format = media.get("format", "MANGA") if media else "MANGA"
            if medium_format == "MANHWA":
                medium_type = "manhwa"
            elif medium_format == "MANHUA":
                medium_type = "manhua"
            else:
                medium_type = "manga"

            return {
                "progress": progress,
                "status": status,
                "repeat": repeat,
                "started_at": started_at,
                "media_status": media_status,
                "medium_type": medium_type
            }

    except Exception as e:
        print(f"\n❌ Error fetching manga {manga_id}: {e}")
        return {
            "progress": 0, "status": "CURRENT", "repeat": 0,
            "started_at": None, "media_status": None, "medium_type": "manga"
        }


def determine_status(
    ani_progress: int,
    ani_status: str,
    ani_repeat: int,
    total_chapters: int,
    ani_started_at: Optional[str],
    challenge_start_date: Optional[str],
    media_status: Optional[str] = None
) -> str:
    """
    Determine manga status based on AniList data and challenge dates.

    Priority order:
    1. Skipped - Started before challenge with 25%+ progress (applies to ALL statuses: completed, caught up, paused, dropped, in progress)
    2. Reread - Completed with rereads ≥ 1
    3. Completed - Finished + manga FINISHED + no rereads
    4. Caught Up - Finished + manga RELEASING + no rereads
    5. In Progress - Currently reading, progress < total
    6. Paused - Paused status with ≥ 25 chapters
    7. Dropped - Dropped status
    8. Not Started - Default fallback
    """
    def _to_date(val):
        """Parse date from various formats to date object."""
        if not val:
            return None
        try:
            from datetime import datetime, date
            # If already a date object, return it
            if isinstance(val, date):
                return val
            # If datetime object, convert to date
            if isinstance(val, datetime):
                return val.date()
            # If string, parse it
            if isinstance(val, str):
                val = val.strip()
                # Try ISO format YYYY-MM-DD (most common from AniList and SQLite)
                if len(val) >= 10:
                    try:
                        return datetime.strptime(val[:10], "%Y-%m-%d").date()
                    except ValueError:
                        pass
                # Try other common formats
                formats = ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"]
                for fmt in formats:
                    try:
                        parsed = datetime.strptime(val, fmt)
                        return parsed.date()
                    except ValueError:
                        continue
        except Exception:
            pass
        return None

    # Baseline total chapters
    effective_total = total_chapters if (isinstance(total_chapters, (int, float)) and total_chapters > 0) else 1

    # Normalize numeric inputs
    try:
        ani_progress_num = max(0, int(ani_progress or 0))
    except Exception:
        ani_progress_num = 0

    try:
        ani_repeat_num = max(0, int(ani_repeat or 0))
    except Exception:
        ani_repeat_num = 0

    status_upper = (ani_status or "").upper()
    media_status_upper = (media_status or "").upper()

    # Parse dates for skipped check
    started_at_val = _to_date(ani_started_at)
    challenge_start_date_val = _to_date(challenge_start_date)

    # Calculate progress percentage for skipped check
    pct_progress = (ani_progress_num / effective_total) if effective_total else 0.0

    # Validate date types before comparison
    from datetime import date as date_type
    both_dates_valid = (
        started_at_val is not None 
        and challenge_start_date_val is not None
        and isinstance(started_at_val, date_type)
        and isinstance(challenge_start_date_val, date_type)
    )

    # Priority 1: SKIPPED - Started before challenge with 25%+ progress
    # Applies to ALL statuses: completed, caught up, paused, dropped, in progress
    # This ensures titles started before challenge existence are marked as skipped
    # IMPORTANT: Only mark as skipped if started_at is BEFORE challenge_start_date
    if both_dates_valid:
        date_comparison = started_at_val < challenge_start_date_val
        if date_comparison:  # Started BEFORE challenge
            if pct_progress >= 0.25:
                return "Skipped"

    # Priority 2: REREAD - Completed with multiple rereads
    if status_upper == "COMPLETED" and ani_progress_num >= effective_total and ani_repeat_num >= 1:
        return "Reread"

    # Priority 3 & 4: COMPLETED vs CAUGHT UP - Finished reading, check manga status
    if ani_progress_num >= effective_total and ani_repeat_num == 0:
        if status_upper == "COMPLETED":
            # User marked as completed - check if manga is finished
            if media_status_upper == "FINISHED":
                return "Completed"
            else:
                # Manga still releasing/hiatus/cancelled
                return "Caught Up"
        elif status_upper == "CURRENT":
            # User still has as "reading" but caught up
            return "Caught Up"

    # Priority 5: IN PROGRESS - Currently reading
    if status_upper == "CURRENT" and 0 < ani_progress_num < effective_total:
        return "In Progress"

    # Priority 6: PAUSED - Paused with sufficient progress
    if status_upper == "PAUSED" and ani_progress_num >= 25:
        return "Paused"

    # Priority 7: DROPPED - Dropped status
    if status_upper == "DROPPED":
        return "Dropped"

    # Priority 8: NOT STARTED - Default fallback
    return "Not Started"


async def get_guild_challenges(guild_id: int) -> List[Tuple[int, str, Optional[str]]]:
    """
    Get all challenges for a guild.

    Args:
        guild_id: Guild ID

    Returns:
        List of (challenge_id, title, start_date) tuples
    """
    # Use COALESCE to fallback to created_at if start_date is NULL (same as button logic)
    challenges = await execute_db_operation(
        "get guild challenges",
        "SELECT challenge_id, title, COALESCE(start_date, created_at) FROM guild_challenges WHERE guild_id = ?",
        (guild_id,),
        fetch_type='all'
    )

    return challenges if challenges else []


async def get_challenge_manga(guild_id: int, challenge_id: int) -> List[Tuple[int, str, int]]:
    """
    Get all manga for a challenge.

    Args:
        guild_id: Guild ID
        challenge_id: Challenge ID

    Returns:
        List of (manga_id, title, total_chapters) tuples
    """
    manga = await execute_db_operation(
        "get challenge manga",
        "SELECT manga_id, title, total_chapters FROM guild_challenge_manga WHERE guild_id = ? AND challenge_id = ?",
        (guild_id, challenge_id),
        fetch_type='all'
    )

    return manga if manga else []


async def update_user_challenge_progress(
    discord_id: int,
    guild_id: int,
    dry_run: bool = False,
    verbose: bool = False
) -> Dict:
    """
    Update all challenge progress for a user.

    Args:
        discord_id: Discord user ID
        guild_id: Guild ID
        dry_run: If True, only show what would be updated without persisting
        verbose: If True, show detailed progress

    Returns:
        Dictionary with summary statistics
    """
    print(f"\n{'='*60}")
    print(f"🔄 Challenge Progress Update")
    print(f"{'='*60}")
    print(f"Discord ID: {discord_id}")
    print(f"Guild ID: {guild_id}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPDATE'}")
    print(f"{'='*60}\n")

    # Get AniList info
    print("📋 Fetching user information...")
    anilist_info = await fetch_anilist_info(discord_id)

    if not anilist_info:
        print("❌ User has not linked their AniList account.")
        return {"error": "No AniList account linked"}

    anilist_id = anilist_info["id"]
    anilist_username = anilist_info["username"]
    print(f"✅ Found AniList: {anilist_username} (ID: {anilist_id})\n")

    # Get all challenges
    print("📋 Fetching guild challenges...")
    challenges = await get_guild_challenges(guild_id)

    if not challenges:
        print("❌ No challenges found for this guild.")
        return {"error": "No challenges found"}

    print(f"✅ Found {len(challenges)} challenges\n")

    # Collect all manga from all challenges
    print("📋 Collecting all manga from challenges...")
    all_manga = []  # List of (challenge_id, challenge_start_date, manga_id, manga_title, total_chapters)

    for challenge_id, challenge_title, challenge_start_date in challenges:
        manga_list = await get_challenge_manga(guild_id, challenge_id)
        for manga_id, manga_title, total_chapters in manga_list:
            all_manga.append((challenge_id, challenge_start_date, manga_id, manga_title, total_chapters))

        if verbose:
            print(f"  • {challenge_title}: {len(manga_list)} manga")

    total_manga = len(all_manga)
    print(f"✅ Total manga to process: {total_manga}\n")

    if total_manga == 0:
        print("❌ No manga found in any challenge.")
        return {"error": "No manga found"}

    # Estimate time
    estimated_time = total_manga * RATE_LIMIT_DELAY
    print(f"⏱️ Estimated time: {estimated_time/60:.1f} minutes ({total_manga} manga × {RATE_LIMIT_DELAY}s)\n")
    print("Starting update...\n")

    # Progress tracker
    tracker = ProgressTracker(total_manga, verbose)

    # Process all manga
    async with aiohttp.ClientSession() as session:
        for challenge_id, challenge_start_date, manga_id, manga_title, total_chapters in all_manga:
            try:
                # Fetch from AniList
                ani_data = await fetch_anilist_manga_progress(session, anilist_id, manga_id)

                # Extract data
                ani_progress = ani_data['progress']
                ani_status = ani_data['status']
                ani_repeat = ani_data['repeat']
                ani_started_at = ani_data['started_at']
                media_status = ani_data.get('media_status')
                medium_type = ani_data.get('medium_type', 'manga')

                # Determine status
                status = determine_status(
                    ani_progress, ani_status, ani_repeat,
                    total_chapters, ani_started_at, challenge_start_date, media_status
                )

                # Calculate points
                difficulty = await get_manga_difficulty(total_chapters, medium_type)
                points = calculate_manga_points(total_chapters, ani_progress, status, difficulty, ani_repeat)

                if verbose:
                    print(f"\n📖 {manga_title}")
                    print(f"   Progress: {ani_progress}/{total_chapters} | Status: {status} | Points: {points}")

                # Persist to database (unless dry run)
                if not dry_run:
                    await upsert_user_manga_progress_guild_aware(
                        discord_id,
                        guild_id,
                        manga_id,
                        manga_title,
                        ani_progress,
                        points,
                        status,
                        ani_repeat,
                        ani_started_at
                    )

                tracker.increment(updated=True, error=False)

            except Exception as e:
                if verbose:
                    print(f"\n❌ Error processing {manga_title}: {e}")
                tracker.increment(updated=False, error=True)

            # Rate limiting
            await asyncio.sleep(RATE_LIMIT_DELAY)

    # Finish
    tracker.finish()

    return {
        "total": total_manga,
        "updated": tracker.updated,
        "errors": tracker.errors,
        "time_taken": (datetime.now() - tracker.start_time).total_seconds()
    }


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update challenge progress for a user from AniList",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/update_challenge_progress.py 123456789 987654321
  python tools/update_challenge_progress.py 123456789 987654321 --dry-run
  python tools/update_challenge_progress.py 123456789 987654321 --verbose
        """
    )

    parser.add_argument('discord_id', type=int, help='Discord user ID')
    parser.add_argument('guild_id', type=int, help='Guild ID')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed progress information')

    args = parser.parse_args()

    try:
        result = await update_user_challenge_progress(
            args.discord_id,
            args.guild_id,
            dry_run=args.dry_run,
            verbose=args.verbose
        )

        if "error" in result:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️ Update cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
