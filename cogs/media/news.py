import asyncio
import os
import time
import re
import html
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
        x_url = f"https://x.com/{path}"
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
                    "text": _clean_text(desc),
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
                
                # Look for X.com URLs too (Twitter rebrand)
                patterns = [
                    r"https?://(?:www\.)?twitter\.com/[^/]+/status/(\d+)",
                    r"https?://(?:www\.)?x\.com/[^/]+/status/(\d+)"
                ]
                
                entries = []
                for pattern in patterns:
                    for m in re.finditer(pattern, text):
                        full = m.group(0)
                        tid = m.group(1)
                        entries.append((m.start(), full, tid))
                
                print(f"🔍 Found {len(entries)} tweet URLs in Jina response")
                
                seen = set()
                ordered = []
                for pos, full, tid in entries:
                    if tid in seen:
                        continue
                    seen.add(tid)
                    ordered.append((pos, full, tid))

                for pos, full, tid in ordered[:limit]:
                    start = max(0, pos - 300)
                    snippet = text[start:pos + 400]
                    snippet = re.sub(r"https?://\S+", "", snippet)
                    snippet = _clean_text(snippet)
                    tweets.append({
                        "id": tid,
                        "url": full,
                        "text": snippet or f"Tweet {tid}",
                        "date": datetime.utcnow()
                    })
                    
                print(f"✅ Jina extracted {len(tweets)} tweets")
                    
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
                        "text": _clean_text(desc),
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

class NewsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def initialize(self):
        if not _AIOSQLITE_AVAILABLE:
            print("❌ aiosqlite not available - news cog disabled")
            return
        try:
            print("✅ News cog initialized using main database")
            if not self.check_tweets.is_running():
                self.check_tweets.start()
                print("✅ Background tweet checking started")
        except Exception as e:
            print(f"❌ Failed to initialize news cog: {e}")

    async def cog_load(self):
        await self.initialize()

    async def cog_unload(self):
        if self.check_tweets.is_running():
            self.check_tweets.cancel()

    # Replace individual commands with single admin interface
    @app_commands.command(name="news-manage", description="Manage Twitter news monitoring system")
    @log_command
    async def news_manage(self, interaction: discord.Interaction):
        """Main news management interface with all functionality."""
        await interaction.response.defer()
        
        # Get current system status
        accounts = await database.get_news_accounts()
        all_account_whitelists = await database.get_all_account_whitelists()
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

        if hasattr(self, 'check_tweets') and self.check_tweets.is_running():
            status_lines.append("✅ Background Task: Running")
            
            # Get last check time from database
            last_check = await database.get_news_last_check()
            if last_check:
                # Convert to timestamp for Discord formatting
                timestamp = int(last_check.timestamp())
                status_lines.append(f"🕐 Last Check: <t:{timestamp}:R>")
                # Calculate next check (5 minutes after last check)
                next_check_timestamp = timestamp + 300
                status_lines.append(f"📅 Next Check: <t:{next_check_timestamp}:R>")
            else:
                status_lines.append("📅 Next check: <t:{int(time.time()) + 300}:R>")
        else:
            status_lines.append("⚠️ Background Task: Not running")

        status_lines.append(f"📊 Tracked Accounts: {len(accounts)}")
        status_lines.append(f"✅ Total Whitelist Keywords: {total_whitelist_keywords} across {len(all_account_whitelists)} accounts")

        embed = discord.Embed(
            title="📰 News Management System",
            description="\n".join(status_lines),
            color=0x1DA1F2
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
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="test-twitter-scrape", description="Test Twitter scraping for debugging")
    @app_commands.describe(username="Twitter username to test scraping")
    async def test_scrape(self, interaction: discord.Interaction, username: str):
        """Test command to debug Twitter scraping issues."""
        await interaction.response.defer()
        
        username = username.replace("@", "").lower()
        
        embed = discord.Embed(
            title="🔧 Twitter Scraping Test",
            description=f"Testing scraping for [@{username}](https://twitter.com/{username})",
            color=0x1DA1F2
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

    @tasks.loop(minutes=5)
    async def check_tweets(self):
        # Save the current check time at the start
        check_time = datetime.utcnow()
        await database.set_news_last_check(check_time)
        
        accounts = await database.get_news_accounts()
        if not accounts:
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
                for i, t in enumerate(tweets_to_post):
                    print(f"\n📝 Processing tweet {i+1}/{len(tweets_to_post)}")
                    print(f"🆔 Tweet ID: {t['id']}")
                    print(f"📄 Tweet text: {t['text'][:100]}...")
                    
                    should_post = True
                    account_whitelist = await database.get_account_whitelist(handle)
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
                        await channel.send(f"🐦 [@{handle}](https://twitter.com/{handle}) has posted a new update:\n{t['url']}")
                        posted_count += 1
                        print(f"🎉 Successfully posted tweet {t['id']}")
                    except Exception as post_error:
                        print(f"❌ Failed to post tweet {t['id']}: {str(post_error)}")
                
                print(f"📊 Posted {posted_count}/{len(tweets_to_post)} tweets for @{handle}")
                
                if new_tweets:
                    new_last_id = str(tweets[0]["id"])
                    await database.update_last_tweet_id(handle, new_last_id)
                    print(f"💾 Updated last tweet ID to: {new_last_id}")
                    
            except Exception as e:
                print(f"❌ Error checking tweets for {handle}: {e}")

    @check_tweets.before_loop
    async def before_check_tweets(self):
        await self.bot.wait_until_ready()


class NewsManagementView(discord.ui.View):
    """Interactive view for managing news system."""
    
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="Add Account", style=discord.ButtonStyle.green, emoji="➕")
    async def add_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add a new Twitter account to monitor."""
        modal = AddAccountModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Remove Account", style=discord.ButtonStyle.red, emoji="➖")
    async def remove_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove a monitored Twitter account."""
        accounts = await database.get_news_accounts()
        if not accounts:
            await interaction.response.send_message("❌ No accounts are currently being monitored.", ephemeral=True)
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
            await interaction.response.send_message(f"❌ Too many accounts ({len(accounts)}). Please use individual removal commands.", ephemeral=True)
            return
        
        select = AccountRemoveSelect(self.cog, options)
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("🗑️ Select an account to remove:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Manage Whitelist", style=discord.ButtonStyle.blurple, emoji="✅", row=1)
    async def manage_whitelist(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manage whitelist keywords."""
        await interaction.response.send_message("✅ Choose whitelist action:", view=WhitelistManagementView(self.cog), ephemeral=True)
    
    @discord.ui.button(label="View Details", style=discord.ButtonStyle.gray, emoji="📋", row=1)
    async def view_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View detailed information about accounts and whitelist."""
        accounts = await database.get_news_accounts()
        whitelist = await database.get_news_whitelist()
        
        embed = discord.Embed(title="📊 Detailed News System Information", color=0x1DA1F2)
        
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
        
        accounts = await database.get_news_accounts()
        if not accounts:
            await interaction.followup.send("❌ No accounts are currently being monitored.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="⚡ Force Update Started",
            description=f"Manually checking {len(accounts)} accounts for new tweets...",
            color=0xffaa00
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Run the check_tweets logic manually
        try:
            await self.cog.check_tweets()
            
            success_embed = discord.Embed(
                title="✅ Force Update Complete",
                description=f"Successfully checked all {len(accounts)} accounts for new tweets.",
                color=0x00ff00
            )
            await interaction.edit_original_response(embed=success_embed)
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Force Update Failed",
                description=f"Error during manual update: {str(e)}",
                color=0xff0000
            )
            await interaction.edit_original_response(embed=error_embed)


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
                    await interaction.response.send_message(
                        f"❌ Channel with ID {target_channel_id} not found or not accessible.",
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid channel ID. Please enter a valid number.",
                    ephemeral=True
                )
                return
        
        try:
            success = await database.add_news_account(username, target_channel_id)
            if success:
                target_channel = interaction.guild.get_channel(target_channel_id)
                channel_mention = target_channel.mention if target_channel else f"<#{target_channel_id}>"
                embed = discord.Embed(
                    title="✅ Account Added",
                    description=f"Now monitoring [@{username}](https://twitter.com/{username}) in {channel_mention}",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Failed to add account (may already exist)",
                    color=0xff0000
                )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error: {str(e)}",
                color=0xff0000
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AccountRemoveSelect(discord.ui.Select):
    """Select dropdown for removing accounts."""
    
    def __init__(self, cog, options):
        super().__init__(placeholder="Choose an account to remove...", options=options)
        self.cog = cog
    
    async def callback(self, interaction: discord.Interaction):
        username = self.values[0]
        success = await database.remove_news_account(username)
        
        if success:
            embed = discord.Embed(
                title="🗑️ Account Removed",
                description=f"Stopped monitoring [@{username}](https://twitter.com/{username})",
                color=0xff5555
            )
        else:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to remove [@{username}](https://twitter.com/{username})",
                color=0xff0000
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
        accounts = await database.get_news_accounts()
        if not accounts:
            await interaction.response.send_message("❌ No Twitter accounts are being monitored. Add an account first.", ephemeral=True)
            return
        
        options = [discord.SelectOption(label=f"@{acc['handle']}", value=acc['handle']) for acc in accounts[:25]]
        
        if len(accounts) > 25:
            await interaction.response.send_message(f"❌ Too many accounts ({len(accounts)}). Contact administrator.", ephemeral=True)
            return
        
        select = AccountSelectForAdd(self.cog, options)
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("📋 Select an account to add keywords for:", view=view, ephemeral=True)
    
    @discord.ui.button(label="➖ Remove Keywords", style=discord.ButtonStyle.red)
    async def remove_keyword(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get accounts that have whitelists
        all_whitelists = await database.get_all_account_whitelists()
        if not all_whitelists:
            await interaction.response.send_message("❌ No whitelist keywords are currently configured for any account.", ephemeral=True)
            return
        
        options = [discord.SelectOption(label=f"@{handle} ({len(keywords)} keywords)", value=handle) 
                  for handle, keywords in all_whitelists.items()]
        
        select = AccountSelectForRemove(self.cog, options, all_whitelists)
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("🗑️ Select an account to remove keywords from:", view=view, ephemeral=True)
    
    @discord.ui.button(label="📋 View All Keywords", style=discord.ButtonStyle.gray)
    async def list_keywords(self, interaction: discord.Interaction, button: discord.ui.Button):
        all_whitelists = await database.get_all_account_whitelists()
        
        if not all_whitelists:
            embed = discord.Embed(
                title="✅ Account Whitelists", 
                description="No account-specific whitelist keywords configured.\n\n**Current behavior:** All tweets from monitored accounts are allowed.", 
                color=0xffaa00
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="✅ Account-Specific Whitelist Keywords", 
            description="Keywords configured per account:",
            color=0x1DA1F2
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
            await interaction.followup.send(f"❌ Too many keywords for @{handle} ({len(keywords)}). Contact administrator.", ephemeral=True)
            return
        
        options = [discord.SelectOption(label=keyword, value=keyword) for keyword in keywords]
        
        select = KeywordRemoveSelect(self.cog, handle, options)
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message(f"🗑️ Select a keyword to remove from @{handle}:", view=view, ephemeral=True)


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
            await interaction.response.send_message("❌ No valid keywords provided.", ephemeral=True)
            return
        
        added_count = 0
        duplicate_count = 0
        
        for keyword in keywords:
            success = await database.add_account_whitelist(self.handle, keyword)
            if success:
                added_count += 1
            else:
                duplicate_count += 1
        
        if added_count > 0:
            embed = discord.Embed(
                title="✅ Keywords Added",
                description=f"Added {added_count} keyword(s) to @{self.handle}.",
                color=0x00ff00
            )
            if duplicate_count > 0:
                embed.add_field(name="ℹ️ Note", value=f"{duplicate_count} keyword(s) already existed and were skipped.", inline=False)
        else:
            embed = discord.Embed(
                title="⚠️ No Keywords Added",
                description=f"All {duplicate_count} keyword(s) already exist for @{self.handle}.",
                color=0xffaa00
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
        success = await database.remove_account_whitelist(self.handle, keyword)
        
        if success:
            embed = discord.Embed(
                title="🗑️ Keyword Removed", 
                description=f"Removed keyword **{keyword}** from @{self.handle}", 
                color=0xff5555
            )
        else:
            embed = discord.Embed(
                title="❌ Error", 
                description=f"Failed to remove keyword **{keyword}** from @{self.handle}", 
                color=0xff0000
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    cog = NewsCog(bot)
    await bot.add_cog(cog)
