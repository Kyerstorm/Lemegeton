import discord
from discord.ext import commands
from discord.ui import View, Button
import re
import aiohttp
from pathlib import Path

# Import Steam helpers
try:
    from helpers.steam_helper import logger, EnhancedGameView
except ModuleNotFoundError:
    import sys
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from helpers.steam_helper import logger, EnhancedGameView

# ------------------------------
# Platforms (rewrites)
# ------------------------------

PLATFORM_MAP = {
    "x.com": "xeezz.com",
    "tiktok.com": "tiktokez.com",
    "ifunny.co": "ifunnyez.co",
    "reddit.com": "redditez.com",
    "snapchat.com": "snapchatez.com",
    "bilibili.com": "bilibiliez.com",
    "imgur.com": "imgurez.com",
    "weibo.com": "weiboez.com",
}


def rewrite_url(url: str):
    if "vm.tiktok.com" in url:
        # Normalize TikTok short links
        return re.sub(r"vm\.tiktok\.com", "tiktokez.com", url)
    for base, new in PLATFORM_MAP.items():
        if base in url:
            return url.replace(base, new)
    return url


# ------------------------------
# Buttons
# ------------------------------

class SimpleView(View):
    def __init__(self, url: str, author_id: int):
        super().__init__(timeout=7200)  # 2 hours
        self.add_item(Button(label="View", url=url, style=discord.ButtonStyle.link))
        self.author_id = author_id
        self.message = None

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(":x: You can’t delete this.", ephemeral=True)
            return
        if self.message:
            await self.message.delete()
        else:
            await interaction.message.delete()

    async def on_timeout(self):
        self.clear_items()
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass


# ------------------------------
# Cog
# ------------------------------

class EmbedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.url_pattern = re.compile(r"(https?://[^\s]+)")
        # Steam app URL pattern: https://store.steampowered.com/app/{appid}/Name/
        self.steam_app_pattern = re.compile(r"https?://store\.steampowered\.com/app/(\d+)")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        urls = self.url_pattern.findall(message.content)
        for url in urls:
            # Check for Steam links first
            steam_match = self.steam_app_pattern.search(url)
            if steam_match:
                await self._process_steam(message, url, steam_match.group(1))
                continue
            
            # Check for social platform links
            for base in PLATFORM_MAP.keys():
                if base in url or "vm.tiktok.com" in url:
                    await self._process(message, url)
                    break

    async def _process(self, message, url):
        rewritten = rewrite_url(url)
        view = SimpleView(rewritten, message.author.id)

        try:
            sent = await message.channel.send(content=rewritten, view=view)
            view.message = sent
            await message.delete()
        except Exception as e:
            print(f"Error reposting link: {e}")
    
    async def _get_app_details(self, session, appid):
        """Get detailed app information from Steam API"""
        try:
            url = "https://store.steampowered.com/api/appdetails"
            params = {"appids": appid, "cc": "us", "l": "en"}
            headers = {"User-Agent": "Mozilla/5.0 (compatible; LemegetonBot/1.0)", "Accept-Language": "en-US,en;q=0.9"}
            
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    entry = data.get(str(appid))
                    
                    if entry and entry.get("success", False):
                        return entry.get("data")
                    
                    # Retry without country code for region-locked apps
                    params2 = {"appids": appid, "l": "en"}
                    async with session.get(url, params=params2, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp2:
                        if resp2.status == 200:
                            data2 = await resp2.json()
                            entry2 = data2.get(str(appid))
                            if entry2 and entry2.get("success", False):
                                return entry2.get("data")
        except Exception as e:
            logger.error(f"Error getting Steam app details for {appid}: {e}")
        return None
    
    async def _process_steam(self, message, url, appid):
        """Process Steam store link and create rich embed"""
        try:
            async with aiohttp.ClientSession() as session:
                app_data = await self._get_app_details(session, appid)
                
                if not app_data:
                    logger.warning(f"Failed to load app data for Steam appid {appid}")
                    return
                
                # Create enhanced game view with the Steam game data
                game_view = EnhancedGameView(app_data, appid, session, message.author)
                embed = await game_view.create_main_embed()
                
                # Send the embed with interactive view
                sent = await message.channel.send(embed=embed, view=game_view)
                
                # Optionally delete the original message to keep chat clean
                # await message.delete()
                
        except Exception as e:
            logger.error(f"Error processing Steam link {url}: {e}")
            # Don't fail silently - the original message stays if embed fails


async def setup(bot):
    await bot.add_cog(EmbedCog(bot))