import asyncio
import os
import time
import re
import html
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp

try:
    import aiosqlite
    _AIOSQLITE_AVAILABLE = True
except ImportError:
    _AIOSQLITE_AVAILABLE = False
    aiosqlite = None

import database
from helpers.command_logger import log_command
from helpers.embed_helper import build_error_embed, build_success_embed, build_warning_embed, build_info_embed
from cogs_test.general_commands.dashboard import command_meta

# Set up logging
logger = logging.getLogger("NewsBot")


# ---------------------- Scraper Config ----------------------

STATIC_NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

JINA_READER_PREFIX = "https://r.jina.ai/http://"
NITTER_STATUS_URL = "https://status.d420.de/"
MXTTR_PREFIX = "https://nitter.mxttr.it/"

_dead_instances: Dict[str, datetime] = {}


# ---------------------- Scraper Utils ----------------------

def _convert_to_twitter_url(url: str) -> str:
    """Convert Nitter URLs to proper X URLs."""
    if not url:
        return url
    
    # Extract the path from Nitter URLs
    # Pattern: https://nitter.instance.com/username/status/1234567890
    nitter_pattern = r'https?://[^/]+/(.*)'
    match = re.match(nitter_pattern, url)
    
    if match:
        path = match.group(1)
        # Remove any fragments (like #m)
        path = path.split('#')[0]
        
        # Convert to proper X URL
        x_url = f"https://xeezz.com/{path}"
        print(f"🔄 Converted {url} → {x_url}")
        return x_url
    
    return url


def _clean_text(s: str) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<.*?>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return discord.utils.escape_markdown(s)

def _parse_rfc2822_date(datestr: str) -> Optional[datetime]:
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(datestr)
    except Exception:
        try:
            return datetime.strptime(datestr, "%a, %d %b %Y %H:%M:%S %Z")
        except Exception:
            return None

async def fetch_live_nitter_instances(session: aiohttp.ClientSession, limit: int = 30) -> List[str]:
    candidates = list(STATIC_NITTER_INSTANCES)
    
    print(f"🔍 Starting with {len(candidates)} static Nitter instances")
    
    try:
        async with session.get(NITTER_STATUS_URL, timeout=8) as resp:
            if resp.status == 200:
                text = await resp.text()
                found = re.findall(r"https?://[a-z0-9.-]*nitter[^\s'\"<>|]+", text, re.I)
                print(f"📋 Found {len(found)} potential instances from status page")
                
                for f in found:
                    # Clean the URL by removing any status indicators
                    f_clean = f.split('|')[0].rstrip('/')  # Remove everything after | and trailing /
                    
                    # Validate URL format
                    if re.match(r'^https?://[a-z0-9.-]+\.[a-z]{2,}$', f_clean, re.I):
                        if f_clean not in candidates:
                            candidates.append(f_clean)
                            print(f"✅ Added clean instance: {f_clean}")
                    else:
                        print(f"❌ Rejected malformed URL: {f}")
    except Exception as e:
        print(f"⚠️ Failed to fetch from status page: {str(e)}")

    try:
        gist_url = "https://gist.githubusercontent.com/cmj/7dace466c983e07d4e3b13be4b786c29/raw"
        async with session.get(gist_url, timeout=8) as resp2:
            if resp2.status == 200:
                txt = await resp2.text()
                found = re.findall(r"https?://[^\s'\"<>|]+", txt)
                print(f"📋 Found {len(found)} potential instances from gist")
                
                for f in found:
                    # Clean the URL
                    f_clean = f.split('|')[0].rstrip('/')
                    
                    if ("nitter" in f_clean and 
                        re.match(r'^https?://[a-z0-9.-]+\.[a-z]{2,}$', f_clean, re.I) and
                        f_clean not in candidates):
                        candidates.append(f_clean)
                        print(f"✅ Added clean gist instance: {f_clean}")
    except Exception as e:
        print(f"⚠️ Failed to fetch from gist: {str(e)}")

    # Remove duplicates while preserving order
    unique = []
    for c in candidates:
        if c not in unique:
            unique.append(c)
        if len(unique) >= limit:
            break
    
    print(f"🎯 Final list: {len(unique)} clean Nitter instances")
    return unique


# ---------------------- Scraper Methods ----------------------

async def _fetch_nitter_rss_instance(session: aiohttp.ClientSession, base: str, username: str, limit: int = 5) -> List[Dict]:
    if base in _dead_instances and _dead_instances[base] > datetime.utcnow():
        print(f"⏸️ Skipping dead instance: {base}")
        return []
    
    url = f"{base.rstrip('/')}/{username}/rss"
    tweets = []
    print(f"🌐 Trying Nitter instance: {base}")
    
    try:
        async with session.get(url, timeout=10) as resp:
            print(f"📊 {base} responded with status: {resp.status}")
            if resp.status != 200:
                _dead_instances[base] = datetime.utcnow() + timedelta(minutes=10)
                print(f"❌ Marking {base} as dead for 10 minutes")
                return []
            
            text = await resp.text()
            if not text.strip():
                print(f"⚠️ Empty response from {base} - likely rate limited or no content")
                # Don't mark as dead for empty responses, might be temporary
                return []
            
            print(f"📄 Response length: {len(text)} characters")
            
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(text)
            except ET.ParseError as e:
                print(f"❌ XML parse error from {base}: {str(e)[:100]}")
                _dead_instances[base] = datetime.utcnow() + timedelta(minutes=10)
                return []
                
            items = root.findall(".//item")
            print(f"📋 Found {len(items)} RSS items from {base}")
            
            for item in items[:limit]:
                guid_el = item.find("guid")
                link_el = item.find("link")
                desc_el = item.find("description")
                pub_el = item.find("pubDate")

                guid = guid_el.text if guid_el is not None else ""
                link = link_el.text if link_el is not None else ""
                desc = desc_el.text if desc_el is not None else ""
                pub = pub_el.text if pub_el is not None else ""

                tid_match = re.search(r"/status/(\d+)$", guid) or re.search(r"/([^/]+)$", guid)
                tid = tid_match.group(1) if tid_match else (guid.split("/")[-1] if guid else "")

                date_obj = _parse_rfc2822_date(pub) or datetime.utcnow()

                tweets.append({
                    "id": tid,
                    "url": _convert_to_twitter_url(link),
                    "text": _clean_text(desc) if desc and len(desc.strip()) > 5 else f"New tweet from @{username}",
                    "date": date_obj
                })
                
            print(f"✅ Successfully parsed {len(tweets)} tweets from {base}")
            
    except asyncio.TimeoutError:
        print(f"⏰ Timeout error for {base}")
        _dead_instances[base] = datetime.utcnow() + timedelta(minutes=10)
        return []
    except Exception as e:
        print(f"❌ Unexpected error from {base}: {str(e)}")
        _dead_instances[base] = datetime.utcnow() + timedelta(minutes=10)
        return []
    return tweets

async def _fetch_with_nitter(username: str, limit: int = 5) -> List[Dict]:
    async with aiohttp.ClientSession() as session:
        instances = await fetch_live_nitter_instances(session)
        for inst in STATIC_NITTER_INSTANCES:
            if inst not in instances:
                instances.append(inst)
        for base in instances:
            try:
                tweets = await _fetch_nitter_rss_instance(session, base, username, limit)
                if tweets:
                    return tweets
            except Exception:
                continue
    return []

async def _fetch_with_jina(username: str, limit: int = 5) -> List[Dict]:
    url = f"{JINA_READER_PREFIX}twitter.com/{username}"
    tweets = []
    print(f"🤖 Trying Jina reader for @{username}: {url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=12) as resp:
                print(f"📊 Jina responded with status: {resp.status}")
                if resp.status != 200:
                    print(f"❌ Jina request failed with status {resp.status}")
                    return []
                    
                text = await resp.text()
                if not text.strip():
                    print("⚠️ Empty response from Jina")
                    return []
                    
                print(f"📄 Jina response length: {len(text)} characters")
                
                # Parse HTML to find tweet content more accurately
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text, 'html.parser')
                
                # Look for X.com URLs too (Twitter rebrand)
                patterns = [
                    r"https?://(?:www\.)?twitter\.com/[^/]+/status/(\d+)",
                    r"https?://(?:www\.)?xeezz\.com/[^/]+/status/(\d+)"
                ]
                
                # Find all elements containing tweet URLs
                tweet_elements = []
                
                # Find all elements containing tweet URLs
                for pattern in patterns:
                    for match in re.finditer(pattern, text):
                        url = match.group(0)
                        tid = match.group(1)
                        
                        # Find the element containing this URL
                        url_element = soup.find(lambda tag: tag.get('href') == url or url in str(tag))
                        if url_element:
                            # Try to find the tweet text - look for parent containers that might contain the tweet
                            tweet_container = url_element
                            for _ in range(5):  # Go up 5 levels max
                                tweet_container = tweet_container.parent if tweet_container.parent else tweet_container
                                text_content = tweet_container.get_text(strip=True)
                                if text_content and len(text_content) > 20 and len(text_content) < 500:
                                    # Check if this looks like tweet content (not bio)
                                    if not any(word in text_content.lower() for word in ['bio', 'description', 'profile', 'follow', 'following', 'followers']):
                                        tweet_elements.append((tid, url, text_content))
                                        break
                            
                            # Fallback: extract text around the URL in the raw HTML
                            if not any(t[0] == tid for t in tweet_elements):
                                start = max(0, match.start() - 200)
                                end = min(len(text), match.end() + 300)
                                snippet = text[start:end]
                                
                                # Remove HTML tags
                                snippet = re.sub(r'<[^>]+>', '', snippet)
                                # Clean up whitespace
                                snippet = re.sub(r'\s+', ' ', snippet).strip()
                                
                                # Extract text before the URL (likely the tweet content)
                                url_pos = snippet.find(url.replace('https://', '').replace('http://', ''))
                                if url_pos > 0:
                                    tweet_text = snippet[:url_pos].strip()
                                    if tweet_text and len(tweet_text) > 10:
                                        tweet_elements.append((tid, url, tweet_text))
                
                # Remove duplicates
                seen_ids = set()
                unique_tweets = []
                for tid, url, text in tweet_elements:
                    if tid not in seen_ids:
                        seen_ids.add(tid)
                        unique_tweets.append({
                            "id": tid,
                            "url": _convert_to_twitter_url(url),
                            "text": _clean_text(text),
                            "date": datetime.utcnow()
                        })
                
                tweets = unique_tweets[:limit]
                print(f"✅ Jina extracted {len(tweets)} tweets with improved parsing")
                    
    except asyncio.TimeoutError:
        print("⏰ Jina request timed out")
        return []
    except Exception as e:
        print(f"❌ Jina error: {str(e)}")
        return []
    return tweets

async def _fetch_with_mxttr(username: str, limit: int = 5) -> List[Dict]:
    url = f"{MXTTR_PREFIX}{username}/rss"
    tweets = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=12) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(text)
                except ET.ParseError:
                    return []
                items = root.findall(".//item")
                for item in items[:limit]:
                    link_el = item.find("link")
                    desc_el = item.find("description")
                    pub_el = item.find("pubDate")

                    link = link_el.text if link_el is not None else ""
                    desc = desc_el.text if desc_el is not None else ""
                    pub = pub_el.text if pub_el is not None else ""

                    tid_match = re.search(r"/status/(\d+)$", link)
                    tid = tid_match.group(1) if tid_match else link.split("/")[-1]

                    date_obj = _parse_rfc2822_date(pub) or datetime.utcnow()

                    tweets.append({
                        "id": tid,
                        "url": _convert_to_twitter_url(link),
                        "text": _clean_text(desc) if desc and len(desc.strip()) > 5 else f"New tweet from @{username}",
                        "date": date_obj
                    })
    except Exception:
        return []
    return tweets

async def fetch_tweets(username: str, limit: int = 5) -> List[Dict]:
    username = username.replace("@", "").lower()
    print(f"🔍 Attempting to fetch tweets for @{username}")
    
    for i, fetcher in enumerate([_fetch_with_nitter, _fetch_with_jina, _fetch_with_mxttr], 1):
        fetcher_name = fetcher.__name__.replace('_fetch_with_', '').upper()
        try:
            print(f"📡 Trying method {i}/3: {fetcher_name}")
            tweets = await fetcher(username, limit)
            if tweets:
                print(f"✅ {fetcher_name} succeeded: Found {len(tweets)} tweets")
                return tweets
            else:
                print(f"⚠️ {fetcher_name} returned no tweets")
        except Exception as e:
            print(f"❌ {fetcher_name} failed: {str(e)}")
            continue
    
    print(f"💥 All scraping methods failed for @{username}")
    return []


# ---------------------- Cog ----------------------

def bot_moderator_only():
    """
    App command check that allows either:
      • Discord server administrators or guild owners
      • Database-defined bot moderators
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        user = interaction.user

        # ✅ Allow server admins or guild owners
        if isinstance(user, discord.Member):
            if user.guild_permissions.administrator or user == interaction.guild.owner:
                return True

        # ✅ Fallback to database moderator system
        try:
            return await database.is_user_bot_moderator(user)
        except Exception as e:
            import logging
            logging.getLogger("NewsBot").error(f"Moderator permission check failed: {e}")
            return False

    return app_commands.check(predicate)



class NewsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._task_started = False
        self._watchdog_started = False
        print("🔧 NewsCog: __init__ called")

    async def initialize(self):
        """Initialize the news cog and start background task."""
        if not _AIOSQLITE_AVAILABLE:
            print("❌ aiosqlite not available - news cog disabled")
            logger.error("aiosqlite not available - news cog disabled", exc_info=True)
            return

        try:
            print("✅ News cog initialized using main database")
            logger.info("News cog initialized using main database")

            # Ensure task starts - it will run immediately after bot is ready
            # thanks to the before_loop decorator
            await self._ensure_task_running()

            # Start watchdog task to monitor main task
            await self._ensure_watchdog_running()

            print("✅ Background tasks started - first tweet check will run as soon as bot is ready")
            logger.info("Background tasks started - first tweet check will run as soon as bot is ready")

        except Exception as e:
            print(f"❌ Failed to initialize news cog: {e}")
            logger.error(f"Failed to initialize news cog: {e}", exc_info=True)
            import traceback
            traceback.print_exc()

    async def _ensure_task_running(self):
        """Ensure the background task is running."""
        try:
            if not self.check_tweets.is_running():
                print("🚀 Starting background tweet checking task...")
                logger.info("Starting background tweet checking task")
                self.check_tweets.start()
                self._task_started = True
                print("✅ Background tweet checking task started successfully")
                logger.info("Background tweet checking task started successfully")
            else:
                print("✅ Background tweet checking task is already running")
                logger.info("Background tweet checking task is already running")
                self._task_started = True
        except RuntimeError as e:
            # Task might already be running or starting
            if "already running" in str(e).lower() or "already started" in str(e).lower():
                print("✅ Background task already running (caught RuntimeError)")
                logger.info("Background task already running (caught RuntimeError)")
                self._task_started = True
            else:
                print(f"❌ Failed to start background task: {e}")
                logger.error(f"Failed to start background task: {e}", exc_info=True)
                raise
        except Exception as e:
            print(f"❌ Unexpected error starting background task: {e}")
            logger.error(f"Unexpected error starting background task: {e}", exc_info=True)
            raise

    async def _ensure_watchdog_running(self):
        """Ensure the watchdog task is running."""
        try:
            if not self.task_watchdog.is_running():
                print("🐕 Starting task watchdog...")
                logger.info("Starting task watchdog to monitor background task")
                self.task_watchdog.start()
                self._watchdog_started = True
                print("✅ Task watchdog started successfully")
                logger.info("Task watchdog started successfully")
            else:
                print("✅ Task watchdog is already running")
                logger.info("Task watchdog is already running")
                self._watchdog_started = True
        except RuntimeError as e:
            if "already running" in str(e).lower() or "already started" in str(e).lower():
                print("✅ Watchdog already running (caught RuntimeError)")
                logger.info("Watchdog already running (caught RuntimeError)")
                self._watchdog_started = True
            else:
                print(f"❌ Failed to start watchdog: {e}")
                logger.error(f"Failed to start watchdog: {e}", exc_info=True)
                raise
        except Exception as e:
            print(f"❌ Unexpected error starting watchdog: {e}")
            logger.error(f"Unexpected error starting watchdog: {e}", exc_info=True)
            raise

    async def cog_load(self):
        """Called when the cog is loaded."""
        print("🔧 NewsCog: cog_load called")
        logger.info("NewsCog: cog_load called")
        await self.initialize()

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        print("🔧 NewsCog: cog_unload called")
        logger.info("NewsCog: cog_unload called")
        
        if self.task_watchdog.is_running():
            print("⏹️ Stopping task watchdog...")
            logger.info("Stopping task watchdog")
            self.task_watchdog.cancel()
            self._watchdog_started = False
        
        if self.check_tweets.is_running():
            print("⏹️ Stopping background tweet checking task...")
            logger.info("Stopping background tweet checking task")
            self.check_tweets.cancel()
            self._task_started = False

    # ---------------------- JSON Storage Methods ----------------------

    def _load_news_accounts(self) -> List[Dict]:
        """Load news accounts from JSON file."""
        try:
            with open('data/news_accounts.json', 'r') as f:
                data = json.load(f)
                return data.get('accounts', [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_news_accounts(self, accounts: List[Dict]):
        """Save news accounts to JSON file."""
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/news_accounts.json', 'w') as f:
                json.dump({'accounts': accounts}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving news accounts: {e}", exc_info=True)

    def _load_news_metadata(self) -> Dict:
        """Load news metadata from JSON file."""
        try:
            with open('data/news_metadata.json', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_news_metadata(self, metadata: Dict):
        """Save news metadata to JSON file."""
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/news_metadata.json', 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving news metadata: {e}", exc_info=True)

    def _load_news_filters(self) -> List[str]:
        """Load news filters from JSON file."""
        try:
            with open('data/news_filters.json', 'r') as f:
                data = json.load(f)
                return data.get('filters', [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_news_filters(self, filters: List[str]):
        """Save news filters to JSON file."""
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/news_filters.json', 'w') as f:
                json.dump({'filters': filters}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving news filters: {e}", exc_info=True)

    # JSON-based replacements for database functions
    async def get_news_accounts_json(self) -> List[Dict]:
        """Get all monitored news accounts from JSON."""
        return self._load_news_accounts()

    async def add_news_account_json(self, handle: str, channel_id: int) -> bool:
        """Add a new monitored news account to JSON."""
        try:
            accounts = self._load_news_accounts()
            # Check if account already exists
            if any(acc['handle'] == handle for acc in accounts):
                return False
            
            accounts.append({
                'handle': handle,
                'channel_id': channel_id,
                'last_tweet_id': None
            })
            self._save_news_accounts(accounts)
            logger.info(f"Added news account: {handle} -> channel {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding news account {handle}: {e}", exc_info=True)
            return False

    async def remove_news_account_json(self, handle: str) -> bool:
        """Remove a monitored news account from JSON."""
        try:
            accounts = self._load_news_accounts()
            original_length = len(accounts)
            accounts = [acc for acc in accounts if acc['handle'] != handle]
            
            if len(accounts) < original_length:
                self._save_news_accounts(accounts)
                logger.info(f"Removed news account: {handle}")
                return True
            else:
                logger.warning(f"News account not found: {handle}")
                return False
        except Exception as e:
            logger.error(f"Error removing news account {handle}: {e}", exc_info=True)
            return False

    async def update_last_tweet_id_json(self, handle: str, tweet_id: str) -> bool:
        """Update the last tweet ID for a monitored account in JSON."""
        try:
            accounts = self._load_news_accounts()
            for account in accounts:
                if account['handle'] == handle:
                    account['last_tweet_id'] = tweet_id
                    self._save_news_accounts(accounts)
                    return True
            return False
        except Exception as e:
            logger.error(f"Error updating last tweet ID for {handle}: {e}", exc_info=True)
            return False

    async def get_news_last_check_json(self) -> Optional[datetime]:
        """Get the last news check timestamp from JSON."""
        try:
            metadata = self._load_news_metadata()
            last_check_str = metadata.get('last_check')
            if last_check_str:
                return datetime.fromisoformat(last_check_str)
            return None
        except Exception as e:
            logger.error(f"Error getting news last check time: {e}", exc_info=True)
            return None

    async def set_news_last_check_json(self, check_time: datetime) -> bool:
        """Set the last news check timestamp in JSON."""
        try:
            metadata = self._load_news_metadata()
            metadata['last_check'] = check_time.isoformat()
            self._save_news_metadata(metadata)
            return True
        except Exception as e:
            logger.error(f"Error setting news last check time: {e}", exc_info=True)
            return False

    async def get_news_filters_json(self) -> List[str]:
        """Get all news filter keywords from JSON."""
        return self._load_news_filters()

    async def add_news_filter_json(self, word: str) -> bool:
        """Add a new news filter keyword to JSON."""
        try:
            filters = self._load_news_filters()
            word_lower = word.lower()
            if word_lower not in filters:
                filters.append(word_lower)
                self._save_news_filters(filters)
                logger.info(f"Added news filter keyword: {word}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error adding news filter keyword {word}: {e}", exc_info=True)
            return False

    async def remove_news_filter_json(self, word: str) -> bool:
        """Remove a news filter keyword from JSON."""
        try:
            filters = self._load_news_filters()
            word_lower = word.lower()
            if word_lower in filters:
                filters.remove(word_lower)
                self._save_news_filters(filters)
                logger.info(f"Removed news filter keyword: {word}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing news filter keyword {word}: {e}", exc_info=True)
            return False

    # Account-specific whitelist JSON methods
    def _load_account_whitelists(self) -> Dict[str, List[str]]:
        """Load account-specific whitelists from JSON file."""
        try:
            with open('data/account_whitelists.json', 'r') as f:
                data = json.load(f)
                return data.get('whitelists', {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_account_whitelists(self, whitelists: Dict[str, List[str]]):
        """Save account-specific whitelists to JSON file."""
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/account_whitelists.json', 'w') as f:
                json.dump({'whitelists': whitelists}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving account whitelists: {e}", exc_info=True)

    # JSON-based replacements for account whitelist database functions
    async def get_account_whitelists_json(self) -> Dict[str, List[str]]:
        """Get all account-specific whitelists from JSON."""
        return self._load_account_whitelists()

    async def add_account_whitelist_json(self, handle: str, keyword: str) -> bool:
        """Add a whitelist keyword for a specific account to JSON."""
        try:
            whitelists = self._load_account_whitelists()
            keyword_lower = keyword.lower()

            if handle not in whitelists:
                whitelists[handle] = []

            if keyword_lower not in whitelists[handle]:
                whitelists[handle].append(keyword_lower)
                self._save_account_whitelists(whitelists)
                logger.info(f"Added whitelist keyword '{keyword}' for account {handle}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error adding whitelist keyword '{keyword}' for {handle}: {e}", exc_info=True)
            return False

    async def remove_account_whitelist_json(self, handle: str, keyword: str) -> bool:
        """Remove a whitelist keyword for a specific account from JSON."""
        try:
            whitelists = self._load_account_whitelists()
            keyword_lower = keyword.lower()

            if handle in whitelists and keyword_lower in whitelists[handle]:
                whitelists[handle].remove(keyword_lower)
                # Remove empty lists
                if not whitelists[handle]:
                    del whitelists[handle]
                self._save_account_whitelists(whitelists)
                logger.info(f"Removed whitelist keyword '{keyword}' for account {handle}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing whitelist keyword '{keyword}' for {handle}: {e}", exc_info=True)
            return False

    async def get_account_whitelist_json(self, handle: str) -> List[str]:
        """Get whitelist keywords for a specific account from JSON."""
        whitelists = self._load_account_whitelists()
        return whitelists.get(handle, [])

    # Replace individual commands with single admin interface
    @bot_moderator_only()
    @app_commands.command(name="admin-news-manage", description="Manage Twitter news monitoring system")
    @command_meta(section="Media", name="News Management")
    @log_command
    async def news_manage(self, interaction: discord.Interaction):
        """Main news management interface with all functionality."""
        # Check if interaction is still valid before attempting to defer
        try:
            await interaction.response.defer()
        except discord.NotFound:
            # Interaction expired, log and return
            logger.error("Interaction expired before deferring - user may have waited too long", exc_info=True)
            return
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}", exc_info=True)
            return
        
        try:
            # Get current system status
            accounts = await self.get_news_accounts_json()
            all_account_whitelists = await self.get_account_whitelists_json()  # Now using JSON storage
            total_whitelist_keywords = sum(len(keywords) for keywords in all_account_whitelists.values())
            
            # Create status embed
            status_lines = []
            status_lines.append("✅ Database: Connected (Main Database)")
            
            try:
                tweets = await fetch_tweets("nasa", 1)
                if tweets:
                    status_lines.append("✅ Scraping: Working")
                else:
                    status_lines.append("⚠️ Scraping: No tweets found")
            except Exception:
                status_lines.append("❌ Scraping: Error")

            # Add watchdog status
            if hasattr(self, 'task_watchdog') and self.task_watchdog.is_running():
                status_lines.append("✅ Watchdog: Active (monitors every 5 minutes)")
            else:
                status_lines.append("❌ Watchdog: Not running")

            if hasattr(self, 'check_tweets') and self.check_tweets.is_running():
                status_lines.append("✅ Background Task: Running")
                
                # Get last check time from JSON
                last_check = await self.get_news_last_check_json()
                if last_check:
                    # Convert to timestamp for Discord formatting
                    timestamp = int(last_check.timestamp())
                    status_lines.append(f"🕐 Last Check: <t:{timestamp}:R>")
                    # Calculate next check (15 minutes after last check)
                    next_check_timestamp = timestamp + 900  # 15 minutes = 900 seconds
                    status_lines.append(f"📅 Next Check: <t:{next_check_timestamp}:R>")
                else:
                    status_lines.append("📅 Next check: <t:{int(time.time()) + 900}:R>")
            else:
                status_lines.append("⚠️ Background Task: Not running")
                if hasattr(self, 'check_tweets'):
                    if self.check_tweets.failed():
                        status_lines.append("❌ Task Status: Failed (use 'Restart Task' button)")
                    elif self.check_tweets.is_being_cancelled():
                        status_lines.append("⏸️ Task Status: Being cancelled")
                    else:
                        status_lines.append("⏹️ Task Status: Stopped (use 'Restart Task' button)")
                else:
                    status_lines.append("❌ Task Status: Not initialized")

            status_lines.append(f"📊 Tracked Accounts: {len(accounts)}")
            status_lines.append(f"✅ Total Whitelist Keywords: {total_whitelist_keywords} across {len(all_account_whitelists)} accounts")

            embed = build_info_embed(
                "📰 News Management System",
                "\n".join(status_lines)
            )
            
            # Add accounts field if any exist
            if accounts:
                account_list = "\n".join(
                    f"[@{acc['handle']}](https://twitter.com/{acc['handle']}) → <#{acc['channel_id']}>"
                    for acc in accounts[:10]  # Limit to 10 to avoid embed limits
                )
                if len(accounts) > 10:
                    account_list += f"\n... and {len(accounts) - 10} more"
                embed.add_field(name="📋 Monitored Accounts", value=account_list, inline=False)
        
            # Add account-specific whitelist field if any exist
            if all_account_whitelists:
                # Show a summary of account whitelists
                whitelist_summary = []
                for handle, keywords in list(all_account_whitelists.items())[:5]:  # Show up to 5 accounts
                    keyword_preview = ", ".join(keywords[:3])
                    if len(keywords) > 3:
                        keyword_preview += f" (+{len(keywords) - 3} more)"
                    whitelist_summary.append(f"@{handle}: {keyword_preview}")
                
                if len(all_account_whitelists) > 5:
                    whitelist_summary.append(f"... and {len(all_account_whitelists) - 5} more accounts")
                
                embed.add_field(name="✅ Account Whitelists", value="\n".join(whitelist_summary), inline=False)
            
            view = NewsManagementView(self)
            
            # Send followup response
            try:
                await interaction.followup.send(embed=embed, view=view)
            except discord.NotFound:
                logger.error("Interaction expired before sending followup message", exc_info=True)
            except Exception as e:
                logger.error(f"Failed to send followup message: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"Error in news_manage command: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    "An error occurred while loading the news management system."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass  # Interaction might be expired

    @app_commands.command(name="test-twitter-scrape", description="Test Twitter scraping for debugging")
    @command_meta(section="Media", name="Test Twitter Scrape")
    @app_commands.describe(username="Twitter username to test scraping")
    async def test_scrape(self, interaction: discord.Interaction, username: str):
        """Test command to debug Twitter scraping issues."""
        try:
            await interaction.response.defer()
        except discord.NotFound:
            logger.error("Interaction expired before deferring for test-scrape command", exc_info=True)
            return
        except Exception as e:
            logger.error(f"Failed to defer test-scrape interaction: {e}", exc_info=True)
            return
        
        username = username.replace("@", "").lower()
        
        embed = build_info_embed(
            "🔧 Twitter Scraping Test",
            f"Testing scraping for [@{username}](https://twitter.com/{username})"
        )
        
        # Test each method individually
        methods = [
            ("Nitter RSS", _fetch_with_nitter),
            ("Jina Reader", _fetch_with_jina),
            ("MXTTR", _fetch_with_mxttr)
        ]
        
        results = []
        for method_name, method_func in methods:
            try:
                tweets = await method_func(username, 3)
                if tweets:
                    results.append(f"✅ **{method_name}**: Found {len(tweets)} tweets")
                    for i, tweet in enumerate(tweets[:2], 1):
                        tweet_text = tweet['text'][:100] + "..." if len(tweet['text']) > 100 else tweet['text']
                        results.append(f"   {i}. {tweet_text}")
                else:
                    results.append(f"⚠️ **{method_name}**: No tweets found")
            except Exception as e:
                results.append(f"❌ **{method_name}**: Error - {str(e)}")
        
        embed.add_field(
            name="📊 Test Results",
            value="\n".join(results) if results else "No results",
            inline=False
        )
        
        # Overall test
        try:
            final_tweets = await fetch_tweets(username, 3)
            if final_tweets:
                embed.add_field(
                    name="🎯 Final Result",
                    value=f"✅ Successfully scraped {len(final_tweets)} tweets",
                    inline=False
                )
            else:
                embed.add_field(
                    name="🎯 Final Result",
                    value="❌ No tweets could be scraped",
                    inline=False
                )
        except Exception as e:
            embed.add_field(
                name="🎯 Final Result",
                value=f"❌ Error: {str(e)}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)

    async def _run_tweet_check(self):
        """Internal method to perform the actual tweet checking logic."""
        try:
            current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            print(f"\n🔄 Tweet check started at {current_time}")
            logger.info(f"Tweet check cycle started at {current_time}")
            
            accounts = await self.get_news_accounts_json()
            if not accounts:
                print("⚠️ No news accounts configured")
                logger.info("No news accounts configured - skipping check")
                return
                
            for account in accounts:
                handle = account['handle']
                channel_id = account['channel_id']
                last_tweet_id = account['last_tweet_id']
                print(f"\n🔍 Processing account: @{handle}")
                print(f"📺 Channel ID: {channel_id}")
                print(f"📝 Last tweet ID: {last_tweet_id}")
                
                try:
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        print(f"❌ Channel {channel_id} not found or not accessible")
                        continue
                        
                    print(f"✅ Found channel: #{channel.name} in {channel.guild.name}")
                    
                    tweets = await fetch_tweets(handle, 5)
                    if not tweets:
                        print(f"⚠️ No tweets returned for @{handle}")
                        continue
                        
                    print(f"📋 Got {len(tweets)} tweets for @{handle}")
                    
                    new_tweets = []
                    for i, t in enumerate(tweets):
                        tid = str(t["id"])
                        print(f"🆔 Tweet {i+1}: ID={tid}")
                        
                        if last_tweet_id and tid == last_tweet_id:
                            print(f"🛑 Found last known tweet ID {tid}, stopping here")
                            break
                        new_tweets.append(t)
                        
                    print(f"🆕 Found {len(new_tweets)} new tweets")
                    
                    if not new_tweets:
                        print(f"⚠️ No new tweets for @{handle}")
                        continue
                    
                    new_tweets.reverse()
                    tweets_to_post = new_tweets[-3:]  # Get last 3
                    print(f"📤 Will attempt to post {len(tweets_to_post)} tweets")
                    
                    posted_count = 0
                    last_posted_tweet_id = None  # Track the last successfully posted tweet
                    
                    for i, t in enumerate(tweets_to_post):
                        print(f"\n📝 Processing tweet {i+1}/{len(tweets_to_post)}")
                        print(f"🆔 Tweet ID: {t['id']}")
                        print(f"📄 Tweet text: {t['text'][:100]}...")
                        
                        should_post = True
                        account_whitelist = await self.get_account_whitelist_json(handle)
                        print(f"✅ Checking against {len(account_whitelist)} whitelist keywords for account @{handle}")
                        
                        if account_whitelist:  # If account-specific whitelist exists, tweet must contain at least one keyword
                            should_post = False
                            for keyword in account_whitelist:
                                if keyword.lower() in t["text"].lower():
                                    print(f"✅ Tweet approved by whitelist keyword: '{keyword}' for @{handle}")
                                    should_post = True
                                    break
                            if not should_post:
                                print(f"🚫 Tweet blocked: no whitelist keywords found for @{handle}")
                        else:
                            print(f"✅ No whitelist configured for @{handle}, allowing all tweets")
                                
                        if not should_post:
                            print(f"⏭️ Skipping tweet due to whitelist")
                            continue
                            
                        print(f"✅ Tweet passed all filters, posting...")
                        try:
                            # Include tweet text if available and not just a fallback
                            tweet_text = t.get('text', '').strip()
                            
                            # Validate tweet text - skip if it looks like bio/profile content
                            bio_keywords = ['bio', 'description', 'profile', 'follow', 'following', 'followers', 'joined', 'location', 'website']
                            if tweet_text and any(keyword in tweet_text.lower() for keyword in bio_keywords):
                                print(f"⚠️ Skipping tweet {t['id']} - appears to contain bio/profile content")
                                continue
                            
                            if tweet_text and tweet_text != f"Tweet {t['id']}" and len(tweet_text) > 10:
                                message = f"🐦 [@{handle}](https://twitter.com/{handle}) posted:\n\n{tweet_text}\n\n{t['url']}"
                            else:
                                message = f"🐦 [@{handle}](https://twitter.com/{handle}) has posted a new update:\n{t['url']}"
                            
                            await channel.send(message)
                            posted_count += 1
                            last_posted_tweet_id = str(t['id'])  # Track last successfully posted tweet
                            print(f"🎉 Successfully posted tweet {t['id']}")
                        except Exception as post_error:
                            print(f"❌ Failed to post tweet {t['id']}: {str(post_error)}")
                    
                    print(f"📊 Posted {posted_count}/{len(tweets_to_post)} tweets for @{handle}")
                    
                    # Update last_tweet_id to prevent duplicates
                    # Use the newest tweet ID from the fetch (even if not posted) to mark all as "seen"
                    # This prevents re-processing tweets that were filtered by whitelist
                    if new_tweets:
                        new_last_id = str(tweets[0]["id"])  # Newest tweet from API
                        update_success = await self.update_last_tweet_id_json(handle, new_last_id)
                        if update_success:
                            print(f"💾 Updated last tweet ID to: {new_last_id}")
                        else:
                            print(f"❌ WARNING: Failed to update last tweet ID! Duplicates may occur on next check.")
                            # Still continue - better to risk duplicates than stop processing other accounts
                        
                except Exception as e:
                    print(f"❌ Error checking tweets for {handle}: {e}")
                    logger.error(f"Error checking tweets for {handle}: {e}", exc_info=True)
                    import traceback
                    traceback.print_exc()
            
            # Save the check time at the END after all work is done
            check_time = datetime.utcnow()
            await self.set_news_last_check_json(check_time)
            completed_time = check_time.strftime('%Y-%m-%d %H:%M:%S UTC')
            print(f"✅ Tweet check completed at {completed_time}")
            logger.info(f"Tweet check completed at {completed_time} - checked {len(accounts)} accounts")
        
        except Exception as e:
            # Catch any uncaught exceptions to prevent the task from stopping
            print(f"💥 CRITICAL ERROR in check_tweets task: {e}")
            logger.critical(f"CRITICAL ERROR in check_tweets task: {e}")
            import traceback
            traceback.print_exc()
            # Task will continue and retry in 15 minutes

    @tasks.loop(minutes=15)
    async def check_tweets(self):
        """Check for new tweets every 15 minutes. This task is designed to recover from errors."""
        await self._run_tweet_check()

    @check_tweets.before_loop
    async def before_check_tweets(self):
        """Wait for the bot to be ready before starting the task, then run an immediate check."""
        print("⏳ Tweet checker task waiting for bot to be ready...")
        logger.info("Tweet checker task waiting for bot to be ready")
        await self.bot.wait_until_ready()

        # Small delay to ensure bot is fully initialized
        await asyncio.sleep(5)

        print("✅ Bot is ready - running immediate tweet check on startup")
        logger.info("Bot is ready - running immediate tweet check on startup")

        # Run the check immediately on startup instead of waiting 15 minutes
        try:
            await self._run_tweet_check()
        except Exception as e:
            print(f"❌ Error during initial startup check: {e}")
            logger.error(f"Error during initial startup check: {e}", exc_info=True)
            import traceback
            traceback.print_exc()

    @check_tweets.error
    async def check_tweets_error(self, error):
        """Handle errors in the check_tweets task to prevent it from stopping permanently."""
        print(f"💥 ERROR in check_tweets task: {error}")
        logger.error(f"ERROR in check_tweets task: {error}", exc_info=True)
        import traceback
        traceback.print_exc()
        print("⏰ Task will restart in 15 minutes...")
        logger.warning("Tweet checking task encountered error - will restart in 15 minutes")
        # The task will automatically restart after the interval

    @tasks.loop(minutes=5)
    async def task_watchdog(self):
        """Watchdog task that monitors and restarts the main task if it stops unexpectedly."""
        try:
            print(f"🐕 Watchdog check: Main task running = {self.check_tweets.is_running()}")
            
            if not self.check_tweets.is_running():
                print("⚠️ WATCHDOG ALERT: Main task is not running!")
                logger.warning("WATCHDOG ALERT: Main tweet checking task is not running - attempting restart")
                
                # Check if task failed
                if self.check_tweets.failed():
                    print("❌ Task failed - restarting...")
                    logger.error("Main task failed - watchdog restarting it", exc_info=True)
                elif self.check_tweets.is_being_cancelled():
                    print("⏸️ Task is being cancelled - waiting...")
                    logger.info("Task is being cancelled - watchdog will check again later")
                    return
                else:
                    print("⏹️ Task stopped - restarting...")
                    logger.warning("Main task stopped unexpectedly - watchdog restarting it")
                
                try:
                    # Attempt to restart the task
                    self.check_tweets.restart()
                    print("✅ Watchdog successfully restarted main task")
                    logger.info("Watchdog successfully restarted main task")
                except Exception as restart_error:
                    print(f"❌ Watchdog failed to restart task: {restart_error}")
                    logger.error(f"Watchdog failed to restart task: {restart_error}", exc_info=True)
                    
                    # If restart fails, try canceling and starting fresh
                    try:
                        self.check_tweets.cancel()
                        await asyncio.sleep(2)
                        self.check_tweets.start()
                        print("✅ Watchdog force-started main task after cancel")
                        logger.info("Watchdog force-started main task after cancel")
                    except Exception as force_start_error:
                        print(f"❌ Watchdog force-start also failed: {force_start_error}")
                        logger.critical(f"Watchdog unable to restart main task: {force_start_error}")
            else:
                print("✅ Watchdog check: Main task is running normally")
                
        except Exception as e:
            print(f"💥 ERROR in watchdog task: {e}")
            logger.error(f"ERROR in watchdog task: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            # Watchdog continues despite errors

    @task_watchdog.before_loop
    async def before_task_watchdog(self):
        """Wait for the bot to be ready before starting the watchdog."""
        print("⏳ Watchdog waiting for bot to be ready...")
        logger.info("Watchdog waiting for bot to be ready")
        await self.bot.wait_until_ready()
        print("✅ Bot is ready - watchdog starting")
        logger.info("Bot is ready - watchdog starting")

    @task_watchdog.error
    async def task_watchdog_error(self, error):
        """Handle errors in the watchdog task."""
        print(f"💥 ERROR in watchdog task: {error}")
        logger.error(f"ERROR in watchdog task: {error}", exc_info=True)
        import traceback
        traceback.print_exc()
        print("⏰ Watchdog will restart in 5 minutes...")
        logger.warning("Watchdog task encountered error - will restart in 5 minutes")


class NewsManagementView(discord.ui.View):
    """Interactive view for managing news system."""
    
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="Add Account", style=discord.ButtonStyle.green, emoji="➕")
    async def add_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add a new Twitter account to monitor."""
        try:
            modal = AddAccountModal(self.cog)
            await interaction.response.send_modal(modal)
        except discord.NotFound:
            logger.error("Interaction expired in add_account button", exc_info=True)
        except Exception as e:
            logger.error(f"Error in add_account button: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    "An error occurred. Please try again."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                pass
    
    @discord.ui.button(label="Remove Account", style=discord.ButtonStyle.red, emoji="➖")
    async def remove_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove a monitored Twitter account."""
        try:
            accounts = await self.cog.get_news_accounts_json()
            if not accounts:
                embed = build_error_embed(
                    "No Accounts",
                    "No accounts are currently being monitored."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        except discord.NotFound:
            logger.error("Interaction expired in remove_account button", exc_info=True)
            return
        except Exception as e:
            logger.error(f"Error in remove_account button: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    "An error occurred. Please try again."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                pass
            return
        
        # Create dropdown with accounts
        options = []
        for acc in accounts[:25]:  # Discord limit
            options.append(discord.SelectOption(
                label=f"@{acc['handle']}",
                value=acc['handle'],
                description=f"Channel: #{interaction.guild.get_channel(acc['channel_id']).name if interaction.guild.get_channel(acc['channel_id']) else 'Unknown'}"
            ))
        
        if len(accounts) > 25:
            embed = build_error_embed(
                "Too Many Accounts",
                f"Too many accounts ({len(accounts)}). Please use individual removal commands."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        select = AccountRemoveSelect(self.cog, options)
        view = discord.ui.View()
        view.add_item(select)
        embed = build_info_embed(
            "Remove Account",
            "🗑️ Select an account to remove:"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="Manage Whitelist", style=discord.ButtonStyle.blurple, emoji="✅", row=1)
    async def manage_whitelist(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manage whitelist keywords."""
        embed = build_info_embed(
            "Manage Whitelist",
            "✅ Choose whitelist action:"
        )
        await interaction.response.send_message(embed=embed, view=WhitelistManagementView(self.cog), ephemeral=True)
    
    @discord.ui.button(label="View Details", style=discord.ButtonStyle.gray, emoji="📋", row=1)
    async def view_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View detailed information about accounts and whitelist."""
        accounts = await self.cog.get_news_accounts_json()
        whitelist = await self.cog.get_news_filters_json()
        
        embed = build_info_embed(
            "📊 Detailed News System Information",
            ""
        )
        
        if accounts:
            account_details = []
            for acc in accounts:
                channel = interaction.guild.get_channel(acc['channel_id']) if interaction.guild else None
                channel_name = f"#{channel.name}" if channel else f"ID:{acc['channel_id']}"
                last_id = f" (Last: {acc['last_tweet_id'][:8]}...)" if acc['last_tweet_id'] else " (No tweets yet)"
                account_details.append(f"[@{acc['handle']}](https://twitter.com/{acc['handle']}) → {channel_name}{last_id}")
            
            # Split into multiple fields if needed
            chunk_size = 10
            for i in range(0, len(account_details), chunk_size):
                chunk = account_details[i:i + chunk_size]
                field_name = f"📋 Monitored Accounts ({i+1}-{min(i+chunk_size, len(account_details))})"
                embed.add_field(name=field_name, value="\n".join(chunk), inline=False)
        else:
            embed.add_field(name="📋 Monitored Accounts", value="None", inline=False)
        
        if whitelist:
            # Split whitelist into chunks if needed
            chunk_size = 20
            whitelist_chunks = [whitelist[i:i + chunk_size] for i in range(0, len(whitelist), chunk_size)]
            for i, chunk in enumerate(whitelist_chunks):
                field_name = f"✅ Whitelist Keywords {f'({i+1})' if len(whitelist_chunks) > 1 else ''}"
                embed.add_field(name=field_name, value=", ".join(chunk), inline=False)
        else:
            embed.add_field(name="✅ Whitelist Keywords", value="None (All tweets allowed)", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="Force Update", style=discord.ButtonStyle.secondary, emoji="⚡", row=2)
    async def force_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manually trigger tweet checking for all accounts."""
        await interaction.response.defer(ephemeral=True)
        
        accounts = await self.cog.get_news_accounts_json()
        if not accounts:
            embed = build_error_embed(
                "No Accounts",
                "No accounts are currently being monitored."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        embed = build_info_embed(
            "⚡ Force Update Started",
            f"Manually checking {len(accounts)} accounts for new tweets..."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Run the check_tweets logic manually
        try:
            await self.cog._run_tweet_check()
            
            success_embed = build_success_embed(
                "✅ Force Update Complete",
                f"Successfully checked all {len(accounts)} accounts for new tweets."
            )
            await interaction.edit_original_response(embed=success_embed)
            
        except Exception as e:
            logger.error(f"Error during force update: {e}", exc_info=True)
            error_embed = build_error_embed(
                "Force Update Failed",
                f"Error during manual update: {str(e)}"
            )
            await interaction.edit_original_response(embed=error_embed)
    
    @discord.ui.button(label="Restart Task", style=discord.ButtonStyle.danger, emoji="🔄", row=2)
    async def restart_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Restart the background tweet checking task."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Stop the task if it's running
            if hasattr(self.cog, 'check_tweets') and self.cog.check_tweets.is_running():
                self.cog.check_tweets.cancel()
                await asyncio.sleep(1)  # Give it time to stop
            
            # Start the task
            if not self.cog.check_tweets.is_running():
                self.cog.check_tweets.start()
                
                embed = build_success_embed(
                    "✅ Task Restarted",
                    "Background tweet checking task has been restarted successfully.\n\nIt will check for new tweets every 15 minutes."
                )
            else:
                embed = build_success_embed(
                    "✅ Task Already Running",
                    "The background task is already running."
                )
            
        except Exception as e:
            logger.error(f"Failed to restart background task: {e}", exc_info=True)
            embed = build_error_embed(
                "Restart Failed",
                f"Failed to restart background task: {str(e)}"
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)


class AddAccountModal(discord.ui.Modal):
    """Modal for adding a new Twitter account."""
    
    def __init__(self, cog):
        super().__init__(title="➕ Add Twitter Account")
        self.cog = cog
    
    username = discord.ui.TextInput(
        label="Twitter Username",
        placeholder="Enter username without @ (e.g., nasa, elonmusk)",
        required=True,
        max_length=50
    )
    
    channel_id = discord.ui.TextInput(
        label="Channel ID (optional)",
        placeholder="Leave blank to use current channel, or paste channel ID",
        required=False,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        username = self.username.value.replace("@", "").lower()
        
        # Determine which channel to use
        target_channel_id = interaction.channel.id  # Default to current channel
        
        if self.channel_id.value.strip():
            try:
                target_channel_id = int(self.channel_id.value.strip())
                # Verify the channel exists and is accessible
                target_channel = interaction.guild.get_channel(target_channel_id)
                if not target_channel:
                    embed = build_error_embed(
                        "Channel Not Found",
                        f"Channel with ID {target_channel_id} not found or not accessible."
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            except ValueError:
                embed = build_error_embed(
                    "Invalid Channel ID",
                    "Invalid channel ID. Please enter a valid number."
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        
        try:
            success = await self.cog.add_news_account_json(username, target_channel_id)
            if success:
                target_channel = interaction.guild.get_channel(target_channel_id)
                channel_mention = target_channel.mention if target_channel else f"<#{target_channel_id}>"
                
                # Auto-start background task if not running
                task_status = ""
                if hasattr(self.cog, 'check_tweets'):
                    if not self.cog.check_tweets.is_running():
                        try:
                            self.cog.check_tweets.start()
                            task_status = "\n\n🚀 Background task automatically started!"
                            print(f"✅ Auto-started background task after adding @{username}")
                        except Exception as task_error:
                            task_status = f"\n\n⚠️ Couldn't auto-start task: {str(task_error)}\nUse 'Restart Task' button to start manually."
                            print(f"❌ Failed to auto-start task: {task_error}")
                
                embed = build_success_embed(
                    "✅ Account Added",
                    f"Now monitoring [@{username}](https://twitter.com/{username}) in {channel_mention}{task_status}"
                )
            else:
                embed = build_error_embed(
                    "Error",
                    "Failed to add account (may already exist)"
                )
        except Exception as e:
            logger.error(f"Error adding account: {e}", exc_info=True)
            embed = build_error_embed(
                "Error",
                f"Error: {str(e)}"
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AccountRemoveSelect(discord.ui.Select):
    """Select dropdown for removing accounts."""
    
    def __init__(self, cog, options):
        super().__init__(placeholder="Choose an account to remove...", options=options)
        self.cog = cog
    
    async def callback(self, interaction: discord.Interaction):
        username = self.values[0]
        success = await self.cog.remove_news_account_json(username)
        
        if success:
            embed = build_info_embed(
                "🗑️ Account Removed",
                f"Stopped monitoring [@{username}](https://twitter.com/{username})"
            )
        else:
            embed = build_error_embed(
                "Error",
                f"Failed to remove [@{username}](https://twitter.com/{username})"
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class WhitelistManagementView(discord.ui.View):
    """View for managing account-specific whitelist keywords."""
    
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="➕ Add Keywords", style=discord.ButtonStyle.green)
    async def add_keyword(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get available accounts
        accounts = await self.cog.get_news_accounts_json()
        if not accounts:
            embed = build_error_embed(
                "No Accounts",
                "No Twitter accounts are being monitored. Add an account first."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        options = [discord.SelectOption(label=f"@{acc['handle']}", value=acc['handle']) for acc in accounts[:25]]
        
        if len(accounts) > 25:
            embed = build_error_embed(
                "Too Many Accounts",
                f"Too many accounts ({len(accounts)}). Contact administrator."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        select = AccountSelectForAdd(self.cog, options)
        view = discord.ui.View()
        view.add_item(select)
        embed = build_info_embed(
            "Add Keywords",
            "📋 Select an account to add keywords for:"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="➖ Remove Keywords", style=discord.ButtonStyle.red)
    async def remove_keyword(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get accounts that have whitelists
        all_whitelists = await self.cog.get_account_whitelists_json()
        if not all_whitelists:
            embed = build_error_embed(
                "No Whitelist Keywords",
                "No whitelist keywords are currently configured for any account."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        options = [discord.SelectOption(label=f"@{handle} ({len(keywords)} keywords)", value=handle) 
                  for handle, keywords in all_whitelists.items()]
        
        select = AccountSelectForRemove(self.cog, options, all_whitelists)
        view = discord.ui.View()
        view.add_item(select)
        embed = build_info_embed(
            "Remove Keywords",
            "🗑️ Select an account to remove keywords from:"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="📋 View All Keywords", style=discord.ButtonStyle.gray)
    async def list_keywords(self, interaction: discord.Interaction, button: discord.ui.Button):
        all_whitelists = await self.cog.get_account_whitelists_json()
        
        if not all_whitelists:
            embed = build_warning_embed(
                "✅ Account Whitelists", 
                "No account-specific whitelist keywords configured.\n\n**Current behavior:** All tweets from monitored accounts are allowed."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = build_info_embed(
            "✅ Account-Specific Whitelist Keywords", 
            "Keywords configured per account:"
        )
        embed.add_field(name="ℹ️ How it works", value="Each account's tweets must contain at least one of its whitelist keywords to be posted.", inline=False)
        
        # Add field for each account
        for handle, keywords in all_whitelists.items():
            # Limit keywords to avoid embed limits
            if len(keywords) <= 10:
                keyword_list = ", ".join(keywords)
            else:
                keyword_list = ", ".join(keywords[:10]) + f" ... (+{len(keywords) - 10} more)"
            
            embed.add_field(
                name=f"@{handle} ({len(keywords)} keywords)",
                value=keyword_list,
                inline=False
            )
        
        total_keywords = sum(len(keywords) for keywords in all_whitelists.values())
        embed.set_footer(text=f"Total: {total_keywords} keywords across {len(all_whitelists)} accounts")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AccountSelectForAdd(discord.ui.Select):
    """Select dropdown for choosing account to add keywords to."""
    
    def __init__(self, cog, options):
        super().__init__(placeholder="Choose an account to add keywords for...", options=options)
        self.cog = cog
    
    async def callback(self, interaction: discord.Interaction):
        handle = self.values[0]
        modal = AddAccountWhitelistModal(self.cog, handle)
        await interaction.response.send_modal(modal)


class AccountSelectForRemove(discord.ui.Select):
    """Select dropdown for choosing account to remove keywords from."""
    
    def __init__(self, cog, options, all_whitelists):
        super().__init__(placeholder="Choose an account to remove keywords from...", options=options)
        self.cog = cog
        self.all_whitelists = all_whitelists
    
    async def callback(self, interaction: discord.Interaction):
        handle = self.values[0]
        keywords = self.all_whitelists[handle]
        
        if len(keywords) > 25:
            embed = build_error_embed(
                "Too Many Keywords",
                f"Too many keywords for @{handle} ({len(keywords)}). Contact administrator."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        options = [discord.SelectOption(label=keyword, value=keyword) for keyword in keywords]
        
        select = KeywordRemoveSelect(self.cog, handle, options)
        view = discord.ui.View()
        view.add_item(select)
        embed = build_info_embed(
            "Remove Keyword",
            f"🗑️ Select a keyword to remove from @{handle}:"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class AddAccountWhitelistModal(discord.ui.Modal):
    """Modal for adding whitelist keywords to a specific account."""
    
    def __init__(self, cog, handle):
        super().__init__(title=f"➕ Add Keywords for @{handle}")
        self.cog = cog
        self.handle = handle
    
    keyword = discord.ui.TextInput(
        label="Keywords for Whitelist",
        placeholder="Enter keywords/phrases (separated by commas) that tweets must contain",
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        keywords_input = self.keyword.value.strip()
        keywords = [k.strip() for k in keywords_input.split(',') if k.strip()]
        
        if not keywords:
            embed = build_error_embed(
                "No Keywords",
                "No valid keywords provided."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        added_count = 0
        duplicate_count = 0
        
        for keyword in keywords:
            success = await self.cog.add_account_whitelist_json(self.handle, keyword)
            if success:
                added_count += 1
            else:
                duplicate_count += 1
        
        if added_count > 0:
            embed = build_success_embed(
                "✅ Keywords Added",
                f"Added {added_count} keyword(s) to @{self.handle}."
            )
            if duplicate_count > 0:
                embed.add_field(name="ℹ️ Note", value=f"{duplicate_count} keyword(s) already existed and were skipped.", inline=False)
        else:
            embed = build_warning_embed(
                "⚠️ No Keywords Added",
                f"All {duplicate_count} keyword(s) already exist for @{self.handle}."
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class KeywordRemoveSelect(discord.ui.Select):
    """Select dropdown for removing whitelist keywords from an account."""
    
    def __init__(self, cog, handle, options):
        super().__init__(placeholder=f"Choose a keyword to remove from @{handle}...", options=options)
        self.cog = cog
        self.handle = handle
    
    async def callback(self, interaction: discord.Interaction):
        keyword = self.values[0]
        success = await self.cog.remove_account_whitelist_json(self.handle, keyword)
        
        if success:
            embed = build_info_embed(
                "🗑️ Keyword Removed", 
                f"Removed keyword **{keyword}** from @{self.handle}"
            )
        else:
            embed = build_error_embed(
                "Error", 
                f"Failed to remove keyword **{keyword}** from @{self.handle}"
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    cog = NewsCog(bot)
    await bot.add_cog(cog)
    # Ensure tasks start immediately on bot startup
    await cog.initialize()
    print("✅ NewsCog setup complete - tasks should be starting")