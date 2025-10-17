"""
Free Games Checker Cog
Monitors Epic Games, GOG, and Steam for free game deals.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp

from helpers.command_logger import log_command
import database

# Set up logging
logger = logging.getLogger("FreeGames")

# View timeout constant
VIEW_TIMEOUT = 180  # 3 minutes


# ---------------------- API Endpoints and Parsers ----------------------

EPIC_FREE_GAMES_API = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
STEAM_FREE_GAMES_URL = "https://store.steampowered.com/search/?maxprice=free&specials=1"


async def fetch_epic_free_games() -> List[Dict]:
    """Fetch current free games from Epic Games Store."""
    games = []
    
    try:
        async with aiohttp.ClientSession() as session:
            params = {
                'locale': 'en-US',
                'country': 'US',
                'allowCountries': 'US'
            }
            
            async with session.get(EPIC_FREE_GAMES_API, params=params, timeout=15) as resp:
                if resp.status != 200:
                    logger.error(f"Epic API returned status {resp.status}")
                    return []
                
                data = await resp.json()
                
                # Navigate the Epic API response structure safely
                catalog = data.get('data')
                if not catalog:
                    logger.warning("Epic API response missing 'data' field")
                    return []
                
                search_store = catalog.get('Catalog', {}).get('searchStore', {})
                elements = search_store.get('elements', [])
                
                if not elements:
                    logger.info("No elements found in Epic API response")
                    return []
                
                for game in elements:
                    try:
                        # Check if game is currently free
                        promotions = game.get('promotions')
                        if not promotions:
                            continue
                        
                        promotional_offers = promotions.get('promotionalOffers', [])
                        
                        if promotional_offers:
                            # Check if game is actually 100% free (discount of 0 means free in Epic's API)
                            # Note: discountPercentage of 0 = free, anything else = paid discount
                            discount_percentage = None
                            end_date = None
                            
                            if promotional_offers and promotional_offers[0].get('promotionalOffers'):
                                first_offer = promotional_offers[0]['promotionalOffers'][0]
                                discount_setting = first_offer.get('discountSetting', {})
                                discount_percentage = discount_setting.get('discountPercentage', None)
                                
                                end_date_str = first_offer.get('endDate')
                                if end_date_str:
                                    try:
                                        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                                    except Exception as date_err:
                                        logger.debug(f"Could not parse date '{end_date_str}': {date_err}")
                            
                            # Only include if it's 100% free (discountPercentage == 0)
                            if discount_percentage != 0:
                                logger.debug(f"Skipping '{game.get('title')}' - discount is {discount_percentage}%, not 100% free")
                                continue
                            
                            # Game is currently free
                            title = game.get('title', 'Unknown Game')
                            description = game.get('description', '')
                            
                            # Get image
                            images = game.get('keyImages', [])
                            image_url = None
                            if images:
                                for img in images:
                                    if img and img.get('type') in ['DieselStoreFrontWide', 'OfferImageWide']:
                                        image_url = img.get('url')
                                        break
                            
                            # Get store URL - handle None values safely
                            slug = None
                            catalog_ns = game.get('catalogNs')
                            if catalog_ns and isinstance(catalog_ns, dict):
                                mappings = catalog_ns.get('mappings', [])
                                if mappings and len(mappings) > 0 and mappings[0]:
                                    slug = mappings[0].get('pageSlug')
                            
                            if not slug:
                                slug = game.get('productSlug')
                            
                            url = f"https://store.epicgames.com/en-US/p/{slug}" if slug else "https://store.epicgames.com/en-US/free-games"
                            
                            games.append({
                                'title': title,
                                'description': description[:200] + '...' if len(description) > 200 else description,
                                'url': url,
                                'image': image_url,
                                'end_date': end_date,
                                'store': 'Epic Games'
                            })
                    
                    except Exception as game_err:
                        logger.warning(f"Error processing Epic game entry: {game_err}")
                        continue
                
                logger.info(f"Found {len(games)} free games on Epic Games Store")
                
    except asyncio.TimeoutError:
        logger.error("Epic Games API request timed out")
    except Exception as e:
        logger.error(f"Error fetching Epic free games: {e}", exc_info=True)
    
    return games


async def fetch_gog_free_games() -> List[Dict]:
    """Fetch current free games from GOG."""
    games = []
    
    try:
        async with aiohttp.ClientSession() as session:
            # GOG API - search for games and filter for 100% discount
            url = "https://catalog.gog.com/v1/catalog"
            params = {
                'limit': '48',
                'order': 'desc:trending',
                'productType': 'game',
                'page': '1',
                'discounted': 'true'  # Only discounted games
            }
            
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    logger.error(f"GOG API returned status {resp.status}")
                    return []
                
                data = await resp.json()
                products = data.get('products', [])
                
                for game in products:
                    # Check if game is 100% off (free)
                    price_data = game.get('price')
                    if not price_data:
                        continue
                    
                    # GOG API structure: discount is string like "-50%" or "-100%"
                    discount_str = price_data.get('discount', '0%')
                    final_money = price_data.get('finalMoney', {})
                    base_money = price_data.get('baseMoney', {})
                    
                    # Parse discount percentage (remove '-' and '%')
                    try:
                        discount_value = abs(int(discount_str.replace('%', '').replace('-', '')))
                    except (ValueError, AttributeError):
                        continue
                    
                    # Parse final price
                    try:
                        final_amount = float(final_money.get('amount', '999'))
                    except (ValueError, TypeError):
                        final_amount = 999
                    
                    # Only include if it's actually free (100% discount AND final price is 0)
                    if discount_value == 100 and final_amount == 0:
                        title = game.get('title', 'Unknown Game')
                        game_id = game.get('id', '')
                        slug = game.get('slug', game_id)
                        
                        games.append({
                            'title': title,
                            'description': f"100% off - Free on GOG",
                            'url': f"https://www.gog.com/game/{slug}",
                            'image': None,
                            'end_date': None,
                            'store': 'GOG'
                        })
                
                logger.info(f"Found {len(games)} free games (100% off) on GOG")
                
    except asyncio.TimeoutError:
        logger.error("GOG API request timed out")
    except Exception as e:
        logger.error(f"Error fetching GOG free games: {e}")
    
    return games


async def fetch_steam_free_games() -> List[Dict]:
    """Fetch current free games from Steam.
    
    Note: Steam rarely has temporary free games like Epic does.
    This function checks the specials section for 100% discounts,
    but Steam's API doesn't reliably expose temporary free games.
    """
    games = []
    
    try:
        async with aiohttp.ClientSession() as session:
            # Method 1: Check featuredcategories specials for 100% discount
            url = "https://store.steampowered.com/api/featuredcategories/"
            
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.error(f"Steam featuredcategories API returned status {resp.status}")
                else:
                    data = await resp.json()
                    
                    # Check specials section for 100% discount games
                    specials = data.get('specials', {}).get('items', [])
                    
                    for item in specials:
                        discount = item.get('discount_percent', 0)
                        
                        # Only include if it's 100% off (free)
                        if discount == 100:
                            app_id = item.get('id')
                            title = item.get('name', 'Unknown Game')
                            final_price = item.get('final_price', 0)
                            original_price = item.get('original_price', 0)
                            
                            # Create description with original price info
                            if original_price > 0:
                                original_str = f"${original_price / 100:.2f}"
                                description = f"100% OFF (Was {original_str}) - Free on Steam!"
                            else:
                                description = "Currently free on Steam"
                            
                            games.append({
                                'title': title,
                                'description': description,
                                'url': f"https://store.steampowered.com/app/{app_id}",
                                'image': item.get('header_image'),
                                'end_date': None,
                                'store': 'Steam'
                            })
            
            # Method 2: Check featured API for 100% discounts (backup method)
            url = "https://store.steampowered.com/api/featured/"
            
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Check all featured categories
                    for category in ['large_capsules', 'featured_win', 'featured_mac', 'featured_linux']:
                        items = data.get(category, [])
                        for item in items:
                            discount = item.get('discount_percent', 0)
                            
                            if discount == 100:
                                app_id = item.get('id')
                                title = item.get('name', 'Unknown Game')
                                
                                # Check if we already have this game
                                if not any(g.get('url', '').endswith(str(app_id)) for g in games):
                                    games.append({
                                        'title': title,
                                        'description': 'Currently free on Steam',
                                        'url': f"https://store.steampowered.com/app/{app_id}",
                                        'image': item.get('header_image'),
                                        'end_date': None,
                                        'store': 'Steam'
                                    })
            
            logger.info(f"Found {len(games)} free games on Steam")
                
    except asyncio.TimeoutError:
        logger.error("Steam API request timed out")
    except Exception as e:
        logger.error(f"Error fetching Steam free games: {e}")
    
    return games


# ---------------------- Views and Modals ----------------------

class FreeGamesManagementView(discord.ui.View):
    """Interactive view for managing free games notifications."""
    
    def __init__(self, guild_id: int, channel_id: Optional[int] = None):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.guild_id = guild_id
        self.channel_id = channel_id
        logger.debug(f"Created FreeGamesManagementView for guild {guild_id}, channel: {channel_id}")
    
    @discord.ui.button(label="Check Free Games", style=discord.ButtonStyle.primary, emoji="🎮")
    async def check_games_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Check currently free games."""
        logger.info(f"Check games button clicked by {interaction.user.display_name}")
        
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to defer check games interaction: {e}")
            return
        
        try:
            # Fetch from all sources
            logger.info("Fetching free games from all platforms")
            
            epic_games = await fetch_epic_free_games()
            gog_games = await fetch_gog_free_games()
            steam_games = await fetch_steam_free_games()
            
            # Combine all games with platform tags
            all_games = []
            for game in epic_games:
                all_games.append({**game, 'platform': 'Epic Games Store', 'emoji': '🛒'})
            for game in gog_games:
                all_games.append({**game, 'platform': 'GOG', 'emoji': '🐻'})
            for game in steam_games:
                all_games.append({**game, 'platform': 'Steam', 'emoji': '🎮'})
            
            if not all_games:
                embed = discord.Embed(
                    title="🎮 Currently Free Games",
                    description="😢 No free games available right now. Check back later!",
                    color=0xffaa00,
                    timestamp=datetime.utcnow()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Send header message
            now = datetime.utcnow()
            header_embed = discord.Embed(
                title="🎮 Currently Free Games",
                description=f"**{len(all_games)}** free game{'s' if len(all_games) != 1 else ''} available now!",
                color=0x00ff00,
                timestamp=now
            )
            await interaction.followup.send(embed=header_embed, ephemeral=True)
            
            # Send individual game embeds with claim buttons
            for i, game in enumerate(all_games, 1):
                # Create detailed embed for each game
                embed = discord.Embed(
                    title=game['title'],
                    description=game.get('description', 'No description available')[:4096],
                    color=0x00ff00,
                    timestamp=now
                )
                
                # Add platform field
                embed.add_field(
                    name="🛒 Platform",
                    value=f"{game['emoji']} {game['platform']}",
                    inline=True
                )
                
                # Add end date if available
                if game.get('end_date'):
                    timestamp_val = int(game['end_date'].timestamp())
                    embed.add_field(
                        name="⏰ Available Until",
                        value=f"<t:{timestamp_val}:F> (<t:{timestamp_val}:R>)",
                        inline=True
                    )
                
                # Add price field
                embed.add_field(
                    name="💰 Price",
                    value="**FREE** 🎉",
                    inline=True
                )
                
                # Set image
                if game.get('image'):
                    embed.set_image(url=game['image'])
                
                # Set footer with game counter
                embed.set_footer(text=f"Game {i}/{len(all_games)}")
                
                # Create claim button
                claim_button = discord.ui.Button(
                    label="🎁 Claim Game",
                    style=discord.ButtonStyle.link,
                    url=game['url']
                )
                
                # Create view with just the claim button
                view = discord.ui.View()
                view.add_item(claim_button)
                
                # Send game embed with claim button
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
            logger.info(f"Sent {len(all_games)} free game embeds to {interaction.user.display_name}")
            
        except Exception as e:
            logger.error(f"Error checking free games: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while fetching free games. Please try again later.",
                    ephemeral=True
                )
            except:
                pass
    
    @discord.ui.button(label="Setup Notifications", style=discord.ButtonStyle.success, emoji="🔔")
    async def setup_notifications_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Setup automatic notifications."""
        logger.info(f"Setup notifications button clicked by {interaction.user.display_name}")
        
        # Check admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to setup free game notifications.",
                ephemeral=True
            )
            return
        
        # Show channel select modal
        modal = ChannelSetupModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Disable Notifications", style=discord.ButtonStyle.danger, emoji="❌")
    async def disable_notifications_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Disable automatic notifications."""
        logger.info(f"Disable notifications button clicked by {interaction.user.display_name}")
        
        # Check admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to disable free game notifications.",
                ephemeral=True
            )
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to defer disable interaction: {e}")
            return
        
        try:
            guild_id = interaction.guild_id
            
            # Check if notifications are enabled
            current_channel = await database.get_free_games_channel(guild_id)
            
            if not current_channel:
                await interaction.followup.send(
                    "ℹ️ Free games notifications are not enabled for this server.",
                    ephemeral=True
                )
                return
            
            # Remove from database
            success = await database.remove_free_games_channel(guild_id)
            
            if success:
                embed = discord.Embed(
                    title="✅ Notifications Disabled",
                    description="Free games notifications have been disabled for this server.",
                    color=0xffaa00
                )
                embed.add_field(
                    name="ℹ️ Note",
                    value="You can still use the 'Check Free Games' button to check manually anytime.",
                    inline=False
                )
            else:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Failed to disable notifications. Please try again.",
                    color=0xff0000
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Disabled free games notifications for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error disabling notifications: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while disabling notifications.",
                    ephemeral=True
                )
            except:
                pass
    
    @discord.ui.button(label="ℹStatus", style=discord.ButtonStyle.secondary, emoji="ℹ️")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show current notification status."""
        logger.info(f"Status button clicked by {interaction.user.display_name}")
        
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to defer status interaction: {e}")
            return
        
        try:
            guild_id = interaction.guild_id
            channel_id = await database.get_free_games_channel(guild_id)
            
            embed = discord.Embed(
                title="📊 Free Games Notification Status",
                color=0x1DA1F2
            )
            
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    embed.description = f"✅ **Notifications Enabled**\n\nDaily notifications are sent to {channel.mention} at 12:00 PM UTC."
                    embed.color = 0x00ff00
                else:
                    embed.description = f"⚠️ **Channel Not Found**\n\nNotifications are configured but the channel (ID: {channel_id}) no longer exists.\n\nPlease setup notifications again."
                    embed.color = 0xffaa00
            else:
                embed.description = "❌ **Notifications Disabled**\n\nAutomatic notifications are not enabled for this server.\n\nUse the 'Setup Notifications' button to enable them."
                embed.color = 0xff0000
            
            embed.add_field(
                name="🔔 Notification Schedule",
                value="• Checks daily at 12:00 PM UTC\n• Posts when new free games are found\n• Includes Epic, GOG, and Steam",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while getting status.",
                    ephemeral=True
                )
            except:
                pass
    
    async def on_timeout(self):
        """Handle view timeout."""
        try:
            self.clear_items()
            logger.debug(f"FreeGamesManagementView timed out for guild {self.guild_id}")
        except Exception as e:
            logger.error(f"Error handling view timeout: {e}")


class ChannelSetupModal(discord.ui.Modal, title="Setup Free Games Notifications"):
    """Modal for selecting notification channel."""
    
    channel_id_input = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Right-click channel → Copy ID (enable Developer Mode)",
        required=True,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to defer modal submission: {e}")
            return
        
        try:
            # Validate channel ID
            channel_id_str = self.channel_id_input.value.strip()
            
            try:
                channel_id = int(channel_id_str)
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid channel ID. Please enter a valid number.",
                    ephemeral=True
                )
                return
            
            # Verify channel exists and bot can access it
            channel = interaction.guild.get_channel(channel_id)
            
            if not channel:
                await interaction.followup.send(
                    "❌ Channel not found. Make sure the channel exists and the bot has access to it.",
                    ephemeral=True
                )
                return
            
            if not isinstance(channel, discord.TextChannel):
                await interaction.followup.send(
                    "❌ The specified channel must be a text channel.",
                    ephemeral=True
                )
                return
            
            # Check bot permissions
            permissions = channel.permissions_for(interaction.guild.me)
            if not permissions.send_messages or not permissions.embed_links:
                await interaction.followup.send(
                    f"❌ I don't have permission to send messages in {channel.mention}. Please grant me the necessary permissions.",
                    ephemeral=True
                )
                return
            
            # Save to database
            guild_id = interaction.guild_id
            success = await database.set_free_games_channel(guild_id, channel_id)
            
            if success:
                embed = discord.Embed(
                    title="✅ Notifications Enabled",
                    description=f"I'll post new free games in {channel.mention} every day at 12:00 PM UTC.",
                    color=0x00ff00
                )
                embed.add_field(
                    name="🔔 What You'll Get",
                    value="• Daily check for new free games\n• Epic Games Store deals\n• GOG free games\n• Steam promotions",
                    inline=False
                )
                embed.set_footer(text="Use 'Check Free Games' button to check manually anytime")
                
                logger.info(f"Set free games channel for guild {guild_id} to {channel_id}")
            else:
                embed = discord.Embed(
                    title="❌ Setup Failed",
                    description="Failed to save notification settings. Please try again.",
                    color=0xff0000
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in channel setup modal: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while setting up notifications.",
                    ephemeral=True
                )
            except:
                pass


# ---------------------- Cog ----------------------

class FreeGamesCog(commands.Cog):
    """Cog for monitoring free game deals."""
    
    def __init__(self, bot):
        self.bot = bot
        self._task_started = False
        logger.info("FreeGamesCog: __init__ called")
    
    async def initialize(self):
        """Initialize the free games cog and start background task."""
        try:
            logger.info("Free Games cog initialized")
            
            # Ensure task starts
            await self._ensure_task_running()
            
        except Exception as e:
            logger.error(f"Failed to initialize free games cog: {e}")
            import traceback
            traceback.print_exc()
    
    async def _ensure_task_running(self):
        """Ensure the background task is running."""
        try:
            if not self.check_free_games.is_running():
                logger.info("Starting free games checking task")
                self.check_free_games.start()
                self._task_started = True
                logger.info("Free games checking task started successfully")
            else:
                logger.info("Free games checking task is already running")
                self._task_started = True
        except RuntimeError as e:
            if "already running" in str(e).lower() or "already started" in str(e).lower():
                logger.info("Free games task already running (caught RuntimeError)")
                self._task_started = True
            else:
                logger.error(f"Failed to start free games task: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error starting free games task: {e}")
            raise
    
    async def cog_load(self):
        """Called when the cog is loaded."""
        logger.info("FreeGamesCog: cog_load called")
        await self.initialize()
    
    async def cog_unload(self):
        """Called when the cog is unloaded."""
        logger.info("FreeGamesCog: cog_unload called")
        if self.check_free_games.is_running():
            logger.info("Stopping free games checking task")
            self.check_free_games.cancel()
            self._task_started = False
    
    @app_commands.command(name="free-games", description="Manage free games notifications and check current deals")
    @log_command
    async def free_games(self, interaction: discord.Interaction):
        """Main free games management interface with all functionality."""
        try:
            await interaction.response.defer()
        except discord.NotFound:
            logger.error("Interaction expired before deferring for free-games command")
            return
        except Exception as e:
            logger.error(f"Failed to defer free-games interaction: {e}")
            return
        
        try:
            guild_id = interaction.guild_id
            channel_id = await database.get_free_games_channel(guild_id)
            
            # Create status embed
            embed = discord.Embed(
                title="🎮 Free Games Management",
                description="Manage automatic notifications for free games from Epic, GOG, and Steam.",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            
            # Add notification status
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    status_text = f"✅ **Notifications Enabled**\n\nDaily posts to {channel.mention} at 12:00 PM UTC"
                    embed.color = 0x00ff00
                else:
                    status_text = f"⚠️ **Channel Not Found**\n\nConfigured channel (ID: {channel_id}) no longer exists"
                    embed.color = 0xffaa00
            else:
                status_text = "❌ **Notifications Disabled**\n\nNo automatic notifications configured"
                embed.color = 0x1DA1F2
            
            embed.add_field(
                name="📊 Current Status",
                value=status_text,
                inline=False
            )
            
            embed.add_field(
                name="🎯 Available Actions",
                value=(
                    "🎮 **Check Free Games** - See current free games\n"
                    "🔔 **Setup Notifications** - Configure automatic posts (Admin)\n"
                    "❌ **Disable Notifications** - Stop automatic posts (Admin)\n"
                    "ℹ️ **Status** - View detailed notification status"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🛒 Supported Platforms",
                value="• Epic Games Store\n• GOG (Good Old Games)\n• Steam",
                inline=False
            )
            
            embed.set_footer(text="Use the buttons below to manage free games notifications")
            
            view = FreeGamesManagementView(guild_id, channel_id)
            
            await interaction.followup.send(embed=embed, view=view)
            logger.info(f"Sent free games management interface to {interaction.user.display_name}")
            
        except Exception as e:
            logger.error(f"Error in free_games command: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while loading the free games management system.",
                    ephemeral=True
                )
            except:
                pass
    
    @tasks.loop(hours=6)
    async def check_free_games(self):
        """Check for free games every 6 hours and post to configured channels."""
        try:
            now = datetime.utcnow()
            logger.info(f"Free games check (every 6 hours) started at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            # Check if we already ran today
            last_check = await database.get_free_games_last_check()
            if last_check:
                # Compare dates (not exact time) - skip if already ran today
                if last_check.date() == now.date():
                    logger.info(f"Free games check already completed today ({last_check.strftime('%Y-%m-%d %H:%M:%S UTC')}), skipping")
                    return
            
            # Get all guilds with free games notifications enabled
            channels = await database.get_all_free_games_channels()
            
            if not channels:
                logger.info("No guilds configured for free games notifications")
                return
            
            # Fetch games from all platforms
            epic_games = await fetch_epic_free_games()
            gog_games = await fetch_gog_free_games()
            steam_games = await fetch_steam_free_games()
            
            # Combine all games into one list with platform tags
            all_games = []
            for game in epic_games:
                all_games.append({**game, 'platform': 'Epic Games Store', 'emoji': '🛒'})
            for game in gog_games:
                all_games.append({**game, 'platform': 'GOG', 'emoji': '🐻'})
            for game in steam_games:
                all_games.append({**game, 'platform': 'Steam', 'emoji': '🎮'})
            
            # Filter out games that have already been posted
            new_games = []
            for game in all_games:
                already_posted = await database.is_game_already_posted(game['url'], game['store'])
                if not already_posted:
                    new_games.append(game)
                else:
                    logger.debug(f"Skipping already posted game: {game['title']} ({game['store']})")
            
            total_games = len(new_games)
            
            if total_games == 0:
                logger.info("No new free games found (all games have been posted before)")
                # Still update last check time
                await database.set_free_games_last_check(now)
                return
            
            logger.info(f"Found {total_games} NEW free games (filtered out {len(all_games) - total_games} already posted)")
            
            # Post to all configured channels
            posted_count = 0
            for guild_id, channel_id in channels:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        logger.warning(f"Channel {channel_id} not found for guild {guild_id}")
                        continue
                    
                    # Send header message
                    header_embed = discord.Embed(
                        title="🎮 Free Games Alert!",
                        description=f"**{total_games}** new free game{'s' if total_games != 1 else ''} available today!",
                        color=0x00ff00,
                        timestamp=now
                    )
                    header_embed.set_footer(text="Use /free-games to check free games anytime")
                    await channel.send(embed=header_embed)
                    
                    # Send individual game embeds with claim buttons
                    for i, game in enumerate(new_games, 1):
                        # Create detailed embed for each game (matching manual check format)
                        embed = discord.Embed(
                            title=game['title'],
                            description=game.get('description', 'No description available')[:4096],
                            color=0x00ff00,
                            timestamp=now
                        )
                        
                        # Add platform field
                        embed.add_field(
                            name="🛒 Platform",
                            value=f"{game['emoji']} {game['platform']}",
                            inline=True
                        )
                        
                        # Add end date if available
                        if game.get('end_date'):
                            timestamp = int(game['end_date'].timestamp())
                            embed.add_field(
                                name="⏰ Available Until",
                                value=f"<t:{timestamp}:F> (<t:{timestamp}:R>)",
                                inline=True
                            )
                        
                        # Add price field
                        embed.add_field(
                            name="💰 Price",
                            value="**FREE** 🎉",
                            inline=True
                        )
                        
                        # Set image
                        if game.get('image'):
                            embed.set_image(url=game['image'])
                        
                        # Set footer with game counter
                        embed.set_footer(text=f"Game {i}/{total_games}")
                        
                        # Create claim button
                        claim_button = discord.ui.Button(
                            label="🎁 Claim Game",
                            style=discord.ButtonStyle.link,
                            url=game['url']
                        )
                        
                        # Create view with just the claim button
                        view = discord.ui.View()
                        view.add_item(claim_button)
                        
                        # Send game embed with claim button
                        await channel.send(embed=embed, view=view)
                    
                    posted_count += 1
                    logger.info(f"Posted {total_games} free games to channel {channel_id} in guild {guild_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to post to channel {channel_id}: {e}")
            
            # Mark all new games as posted (only if we successfully posted to at least one channel)
            if posted_count > 0:
                for game in new_games:
                    await database.add_posted_game(game['title'], game['url'], game['store'])
                logger.info(f"Marked {total_games} games as posted")
            
            logger.info(f"Free games check completed - posted to {posted_count}/{len(channels)} channels")
            
            # Cleanup old posted game entries (older than 30 days)
            cleanup_count = await database.cleanup_old_posted_games(days=30)
            if cleanup_count > 0:
                logger.info(f"Cleaned up {cleanup_count} old posted game entries")
            
            # Update last check timestamp AFTER successful posting
            await database.set_free_games_last_check(now)
            logger.info(f"Updated last check time to {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
        except Exception as e:
            logger.critical(f"CRITICAL ERROR in check_free_games task: {e}")
            import traceback
            traceback.print_exc()
    
    @check_free_games.before_loop
    async def before_check_free_games(self):
        """Wait for the bot to be ready before starting the task."""
        logger.info("Free games checker task waiting for bot to be ready")
        await self.bot.wait_until_ready()
        logger.info("Bot is ready - free games checker task starting")
    
    @check_free_games.error
    async def check_free_games_error(self, error):
        """Handle errors in the check_free_games task."""
        logger.error(f"ERROR in check_free_games task: {error}")
        import traceback
        traceback.print_exc()
        logger.warning("Free games checking task encountered error - will restart in 24 hours")


async def setup(bot):
    cog = FreeGamesCog(bot)
    await bot.add_cog(cog)
