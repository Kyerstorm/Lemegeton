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
from helpers.embed_helper import build_error_embed, build_success_embed, build_info_embed, build_warning_embed
import database
from cogs_test.general_commands.dashboard import command_meta

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

    Searches for games with 100% discount using multiple methods:
    1. Parse HTML search results for maxprice=free&specials=1
    2. Check featured APIs for 100% discounts
    """
    games = []
    seen_app_ids = set()

    try:
        async with aiohttp.ClientSession() as session:
            # Method 1: Parse HTML search results for 100% off games
            # This is the most comprehensive method as it includes ALL discounted games
            search_url = "https://store.steampowered.com/search/results/"
            params = {
                'query': '',
                'start': '0',
                'count': '50',  # Get first 50 results
                'dynamic_data': '',
                'sort_by': '_ASC',
                'specials': '1',  # Only games on special
                'filter': 'topsellers',
                'snr': '1_7_7_2300_7',
                'infinite': '1'
            }

            try:
                async with session.get(search_url, params=params, timeout=20) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            results_html = data.get('results_html', '')

                            if results_html:
                                # Parse HTML to extract game info
                                import re
                                from bs4 import BeautifulSoup

                                soup = BeautifulSoup(results_html, 'html.parser')
                                search_results = soup.find_all('a', class_='search_result_row')

                                for result in search_results:
                                    try:
                                        # Extract app ID
                                        app_id_str = result.get('data-ds-appid')
                                        if not app_id_str:
                                            continue

                                        app_id = int(app_id_str)

                                        # Skip if already processed
                                        if app_id in seen_app_ids:
                                            continue

                                        # Extract discount percentage
                                        discount_pct = result.find('div', class_='discount_pct')
                                        if not discount_pct:
                                            continue

                                        discount_text = discount_pct.get_text(strip=True)

                                        # Check if it's 100% off
                                        if '-100%' in discount_text:
                                            # Extract title
                                            title_elem = result.find('span', class_='title')
                                            title = title_elem.get_text(strip=True) if title_elem else f"App {app_id}"

                                            # Extract original price
                                            original_price_elem = result.find('div', class_='discount_original_price')
                                            original_price = original_price_elem.get_text(strip=True) if original_price_elem else "Unknown"

                                            # Extract image
                                            img_elem = result.find('img')
                                            image_url = img_elem.get('src') if img_elem else None

                                            description = f"100% OFF (Was {original_price}) - Free on Steam!"

                                            games.append({
                                                'title': title,
                                                'description': description,
                                                'url': f"https://store.steampowered.com/app/{app_id}",
                                                'image': image_url,
                                                'end_date': None,
                                                'store': 'Steam'
                                            })

                                            seen_app_ids.add(app_id)
                                            logger.debug(f"Found 100% off game via search: {title} (App {app_id})")

                                    except Exception as parse_err:
                                        logger.debug(f"Error parsing search result: {parse_err}")
                                        continue

                        except Exception as json_err:
                            logger.warning(f"Error parsing Steam search JSON: {json_err}")
                    else:
                        logger.warning(f"Steam search returned status {resp.status}")

            except Exception as search_err:
                logger.warning(f"Steam search method failed: {search_err}")

            # Method 2: Check featuredcategories specials for 100% discount
            try:
                url = "https://store.steampowered.com/api/featuredcategories/"

                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        specials = data.get('specials', {}).get('items', [])

                        for item in specials:
                            discount = item.get('discount_percent', 0)

                            if discount == 100:
                                app_id = item.get('id')

                                if app_id not in seen_app_ids:
                                    title = item.get('name', 'Unknown Game')
                                    final_price = item.get('final_price', 0)
                                    original_price = item.get('original_price', 0)

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

                                    seen_app_ids.add(app_id)
                                    logger.debug(f"Found 100% off game via featured: {title} (App {app_id})")

            except Exception as featured_err:
                logger.warning(f"Featured API method failed: {featured_err}")

            # Method 3: Check featured API for 100% discounts
            try:
                url = "https://store.steampowered.com/api/featured/"

                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        for category in ['large_capsules', 'featured_win', 'featured_mac', 'featured_linux']:
                            items = data.get(category, [])
                            for item in items:
                                discount = item.get('discount_percent', 0)

                                if discount == 100:
                                    app_id = item.get('id')

                                    if app_id not in seen_app_ids:
                                        title = item.get('name', 'Unknown Game')

                                        games.append({
                                            'title': title,
                                            'description': '100% OFF - Currently free on Steam',
                                            'url': f"https://store.steampowered.com/app/{app_id}",
                                            'image': item.get('header_image'),
                                            'end_date': None,
                                            'store': 'Steam'
                                        })

                                        seen_app_ids.add(app_id)
                                        logger.debug(f"Found 100% off game via featured2: {title} (App {app_id})")

            except Exception as featured2_err:
                logger.warning(f"Featured2 API method failed: {featured2_err}")

            # Method 4: Check for "Free to Keep" promotions using undocumented endpoint
            # This finds games like Death Fungeon that are temporarily 100% off
            try:
                # Try to get current free promotions
                url = "https://store.steampowered.com/search/results/"
                params = {
                    'query': '',
                    'start': '0',
                    'count': '100',  # Get more results
                    'maxprice': 'free',
                    'specials': '1',
                    'infinite': '1'
                }

                async with session.get(url, params=params, timeout=20) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            results_html = data.get('results_html', '')

                            if results_html:
                                from bs4 import BeautifulSoup

                                soup = BeautifulSoup(results_html, 'html.parser')
                                search_results = soup.find_all('a', class_='search_result_row')

                                for result in search_results:
                                    try:
                                        app_id_str = result.get('data-ds-appid')
                                        if not app_id_str:
                                            continue

                                        app_id = int(app_id_str)

                                        if app_id in seen_app_ids:
                                            continue

                                        # Check for free price
                                        final_price_elem = result.find('div', class_='discount_final_price')
                                        if not final_price_elem:
                                            continue

                                        final_price_text = final_price_elem.get_text(strip=True)

                                        # Check if it shows "Free" or price of 0
                                        if 'Free' in final_price_text or '£0.00' in final_price_text or '$0.00' in final_price_text or '€0.00' in final_price_text:
                                            # Check if there's a discount (meaning it was paid before)
                                            discount_pct = result.find('div', class_='discount_pct')
                                            original_price_elem = result.find('div', class_='discount_original_price')

                                            if discount_pct and original_price_elem:
                                                # This is a paid game that's now free
                                                title_elem = result.find('span', class_='title')
                                                title = title_elem.get_text(strip=True) if title_elem else f"App {app_id}"

                                                # Filter out DLC, soundtracks, and other non-game content
                                                title_lower = title.lower()
                                                dlc_keywords = ['dlc', 'soundtrack', 'ost', 'skin pack', 'skins pack',
                                                              'cosmetic', 'expansion pack', 'season pass', 'content pack',
                                                              'outfit pack', 'weapon pack', 'character pack']

                                                is_dlc = any(keyword in title_lower for keyword in dlc_keywords)

                                                # Also check for common DLC patterns like " - " followed by DLC name
                                                if ' - ' in title and not is_dlc:
                                                    # Games like "Game Name - DLC Name" are likely DLC
                                                    # But "Game Name - Deluxe Edition" might be a full game
                                                    parts = title.split(' - ')
                                                    if len(parts) > 1:
                                                        second_part_lower = parts[1].lower()
                                                        if any(kw in second_part_lower for kw in ['pack', 'bundle', 'edition'] + dlc_keywords):
                                                            is_dlc = True

                                                if is_dlc:
                                                    logger.debug(f"Skipping DLC/add-on: {title} (App {app_id})")
                                                    continue

                                                original_price = original_price_elem.get_text(strip=True)

                                                img_elem = result.find('img')
                                                image_url = img_elem.get('src') if img_elem else None

                                                description = f"100% OFF (Was {original_price}) - Free to keep on Steam!"

                                                games.append({
                                                    'title': title,
                                                    'description': description,
                                                    'url': f"https://store.steampowered.com/app/{app_id}",
                                                    'image': image_url,
                                                    'end_date': None,
                                                    'store': 'Steam'
                                                })

                                                seen_app_ids.add(app_id)
                                                logger.debug(f"Found free promotion: {title} (App {app_id})")

                                    except Exception as parse_err:
                                        logger.debug(f"Error parsing free promotion result: {parse_err}")
                                        continue

                        except Exception as json_err:
                            logger.warning(f"Error parsing maxprice=free search: {json_err}")

            except Exception as free_promo_err:
                logger.warning(f"Free promotions search failed: {free_promo_err}")

            logger.info(f"Found {len(games)} free games on Steam (checked {len(seen_app_ids)} unique apps)")

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
                embed = build_info_embed(
                    "Currently Free Games",
                    "No free games available right now. Check back later!"
                )
                embed.timestamp = datetime.utcnow()
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Send header message
            now = datetime.utcnow()
            header_embed = build_success_embed(
                "Currently Free Games",
                f"**{len(all_games)}** free game{'s' if len(all_games) != 1 else ''} available now!"
            )
            header_embed.timestamp = now
            await interaction.followup.send(embed=header_embed, ephemeral=True)
            
            # Send individual game embeds with claim buttons
            for i, game in enumerate(all_games, 1):
                # Create detailed embed for each game
                embed = build_success_embed(
                    game['title'],
                    game.get('description', 'No description available')[:4096]
                )
                embed.timestamp = now
                
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
            logger.error(f"Error checking free games: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error Fetching Games",
                    "An error occurred while fetching free games. Please try again later."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass
    
    @discord.ui.button(label="Setup Notifications", style=discord.ButtonStyle.success, emoji="🔔")
    async def setup_notifications_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Setup automatic notifications."""
        logger.info(f"Setup notifications button clicked by {interaction.user.display_name}")
        
        # Check admin permissions
        if not interaction.user.guild_permissions.administrator:
            embed = build_error_embed(
                "Permission Denied",
                "You need administrator permissions to setup free game notifications."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
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
            embed = build_error_embed(
                "Permission Denied",
                "You need administrator permissions to disable free game notifications."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
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
                embed = build_warning_embed(
                    "Notifications Disabled",
                    "Free games notifications have been disabled for this server."
                )
                embed.add_field(
                    name="ℹ️ Note",
                    value="You can still use the 'Check Free Games' button to check manually anytime.",
                    inline=False
                )
            else:
                embed = build_error_embed(
                    "Error",
                    "Failed to disable notifications. Please try again."
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Disabled free games notifications for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Error disabling notifications: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    "An error occurred while disabling notifications."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
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
            
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    embed = build_success_embed(
                        "Free Games Notification Status",
                        f"**Notifications Enabled**\n\nDaily notifications are sent to {channel.mention} at 12:00 PM UTC."
                    )
                else:
                    embed = build_warning_embed(
                        "Free Games Notification Status",
                        f"**Channel Not Found**\n\nNotifications are configured but the channel (ID: {channel_id}) no longer exists.\n\nPlease setup notifications again."
                    )
            else:
                embed = build_error_embed(
                    "Free Games Notification Status",
                    "**Notifications Disabled**\n\nAutomatic notifications are not enabled for this server.\n\nUse the 'Setup Notifications' button to enable them."
                )
            
            embed.add_field(
                name="🔔 Notification Schedule",
                value="• Checks daily at 12:00 PM UTC\n• Posts when new free games are found\n• Includes Epic, GOG, and Steam",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error getting status: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    "An error occurred while getting status."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
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
                embed = build_error_embed(
                    "Invalid Input",
                    "Invalid channel ID. Please enter a valid number."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Verify channel exists and bot can access it
            channel = interaction.guild.get_channel(channel_id)
            
            if not channel:
                embed = build_error_embed(
                    "Channel Not Found",
                    "Channel not found. Make sure the channel exists and the bot has access to it."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            if not isinstance(channel, discord.TextChannel):
                embed = build_error_embed(
                    "Invalid Channel Type",
                    "The specified channel must be a text channel."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Check bot permissions
            permissions = channel.permissions_for(interaction.guild.me)
            if not permissions.send_messages or not permissions.embed_links:
                embed = build_error_embed(
                    "Missing Permissions",
                    f"I don't have permission to send messages in {channel.mention}. Please grant me the necessary permissions."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Save to database
            guild_id = interaction.guild_id
            success = await database.set_free_games_channel(guild_id, channel_id)
            
            if success:
                embed = build_success_embed(
                    "Notifications Enabled",
                    f"I'll post new free games in {channel.mention} every day at 12:00 PM UTC."
                )
                embed.add_field(
                    name="🔔 What You'll Get",
                    value="• Daily check for new free games\n• Epic Games Store deals\n• GOG free games\n• Steam promotions",
                    inline=False
                )
                embed.set_footer(text="Use 'Check Free Games' button to check manually anytime")
                
                logger.info(f"Set free games channel for guild {guild_id} to {channel_id}")
            else:
                embed = build_error_embed(
                    "Setup Failed",
                    "Failed to save notification settings. Please try again."
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in channel setup modal: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    "An error occurred while setting up notifications."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
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
    @command_meta(section="Gaming", name="Free Games")
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
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    embed = build_success_embed(
                        "Free Games Management",
                        "Manage automatic notifications for free games from Epic, GOG, and Steam."
                    )
                    status_text = f"**Notifications Enabled**\n\nDaily posts to {channel.mention} at 12:00 PM UTC"
                else:
                    embed = build_warning_embed(
                        "Free Games Management",
                        "Manage automatic notifications for free games from Epic, GOG, and Steam."
                    )
                    status_text = f"**Channel Not Found**\n\nConfigured channel (ID: {channel_id}) no longer exists"
            else:
                embed = build_info_embed(
                    "Free Games Management",
                    "Manage automatic notifications for free games from Epic, GOG, and Steam."
                )
                status_text = "**Notifications Disabled**\n\nNo automatic notifications configured"
            embed.timestamp = datetime.utcnow()
            
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
                    "**Disable Notifications** - Stop automatic posts (Admin)\n"
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
            logger.error(f"Error in free_games command: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error",
                    "An error occurred while loading the free games management system."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

    @app_commands.command(name="check-free-games", description="🎮 Test command: Check current free games from all platforms")
    @command_meta(section="Gaming", name="Check Free Games")
    @log_command
    async def check_free_games_now(self, interaction: discord.Interaction):
        """Test command to immediately check and display current free games."""
        try:
            await interaction.response.defer()
        except discord.NotFound:
            logger.error("Interaction expired before deferring")
            return
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}")
            return

        try:
            logger.info(f"Manual free games check triggered by {interaction.user} ({interaction.user.id})")

            # Send status message
            await interaction.followup.send("🔍 Checking for free games on all platforms... This may take a moment.")

            # Fetch games from all platforms
            epic_games = await fetch_epic_free_games()
            gog_games = await fetch_gog_free_games()
            steam_games = await fetch_steam_free_games()

            # Combine all games
            all_games = []
            for game in epic_games:
                all_games.append({**game, 'platform': 'Epic Games Store', 'emoji': '🛒'})
            for game in gog_games:
                all_games.append({**game, 'platform': 'GOG', 'emoji': '🐻'})
            for game in steam_games:
                all_games.append({**game, 'platform': 'Steam', 'emoji': '🎮'})

            if not all_games:
                embed = build_info_embed(
                    "No Free Games Found",
                    "No temporarily free games found on any platform at the moment.\n\nNote: This only checks for games that were paid but are now free (like Epic's weekly free games)."
                )
                embed.timestamp = datetime.utcnow()
                embed.add_field(
                    name="📊 Checked Platforms",
                    value="• Epic Games Store ✓\n• GOG ✓\n• Steam ✓",
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                logger.info("No free games found during manual check")
                return

            # Send header
            header_embed = build_success_embed(
                "Current Free Games",
                f"Found **{len(all_games)}** free game{'s' if len(all_games) != 1 else ''} currently available!"
            )
            header_embed.timestamp = datetime.utcnow()
            header_embed.add_field(
                name="📊 Results",
                value=(
                    f"• Epic Games: {len(epic_games)} game{'s' if len(epic_games) != 1 else ''}\n"
                    f"• GOG: {len(gog_games)} game{'s' if len(gog_games) != 1 else ''}\n"
                    f"• Steam: {len(steam_games)} game{'s' if len(steam_games) != 1 else ''}"
                ),
                inline=False
            )
            header_embed.set_footer(text="Showing games that were paid but are now free")
            await interaction.followup.send(embed=header_embed)

            # Send individual game embeds
            for i, game in enumerate(all_games, 1):
                embed = build_success_embed(
                    game['title'],
                    game.get('description', 'No description available')[:4096]
                )
                embed.timestamp = datetime.utcnow()

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
                        value=f"<t:{timestamp}:F>\n(<t:{timestamp}:R>)",
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

                view = discord.ui.View()
                view.add_item(claim_button)

                # Send game embed
                await interaction.followup.send(embed=embed, view=view)

                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)

            logger.info(f"Manual free games check completed - displayed {len(all_games)} games")

        except Exception as e:
            logger.error(f"Error in check_free_games_now command: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ An error occurred while checking for free games. Please try again later.",
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
                    header_embed = build_success_embed(
                        "Free Games Alert!",
                        f"**{total_games}** new free game{'s' if total_games != 1 else ''} available today!"
                    )
                    header_embed.timestamp = now
                    header_embed.set_footer(text="Use /free-games to check free games anytime")
                    await channel.send(embed=header_embed)
                    
                    # Send individual game embeds with claim buttons
                    for i, game in enumerate(new_games, 1):
                        # Create detailed embed for each game (matching manual check format)
                        embed = build_success_embed(
                            game['title'],
                            game.get('description', 'No description available')[:4096]
                        )
                        embed.timestamp = now
                        
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
