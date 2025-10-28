import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import logging
from typing import Optional, List, Dict
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
import re

logger = logging.getLogger("SteamSearch")

class GameSelectDropdown(discord.ui.Select):
    """Dropdown menu for selecting a game from search results."""
    
    def __init__(self, games: List[Dict], user_id: int):
        """
        Initialize the dropdown with game options.
        
        Args:
            games: List of game dictionaries with 'appid', 'name', and optional 'price'
            user_id: Discord user ID to verify ownership
        """
        self.games = games
        self.user_id = user_id
        
        # Create select options (max 25, but we're using top 3)
        options = []
        for i, game in enumerate(games[:3], 1):
            # Truncate name to fit Discord limits
            name = game['name'][:100] if len(game['name']) > 100 else game['name']
            
            # Create description with price if available
            description = f"App ID: {game['appid']}"
            if 'price' in game and game['price']:
                description = f"{game['price']} • {description}"
            
            options.append(discord.SelectOption(
                label=f"{i}. {name}",
                description=description[:100],  # Discord limit
                value=str(game['appid']),
                emoji="🎮"
            ))
        
        super().__init__(
            placeholder="Choose a game to view details...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle game selection."""
        # Verify user ownership
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ This isn't your search menu!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        # Get selected game
        selected_appid = self.values[0]
        selected_game = next(
            (g for g in self.games if str(g['appid']) == selected_appid),
            None
        )
        
        if not selected_game:
            await interaction.followup.send(
                "❌ Could not find the selected game.",
                ephemeral=True
            )
            return
        
        # Fetch detailed game information
        try:
            embed = await fetch_game_details(selected_appid, selected_game['name'])
            
            # Send public embed (not ephemeral)
            await interaction.followup.send(embed=embed)
            
            # Disable the dropdown after selection
            self.disabled = True
            await interaction.message.edit(view=self.view)
            
        except Exception as e:
            logger.error(f"Error fetching game details for {selected_appid}: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching game details. Please try again.",
                ephemeral=True
            )


class GameSelectView(discord.ui.View):
    """View containing the game selection dropdown."""
    
    def __init__(self, games: List[Dict], user_id: int):
        super().__init__(timeout=120)  # 2-minute timeout
        self.add_item(GameSelectDropdown(games, user_id))
    
    async def on_timeout(self):
        """Disable dropdown when view times out."""
        for item in self.children:
            item.disabled = True


async def search_steam_store(session: aiohttp.ClientSession, query: str) -> List[Dict]:
    """
    Search Steam store for games matching the query.
    
    Args:
        session: aiohttp session
        query: Search query string
    
    Returns:
        List of game dictionaries with appid, name, and price
    """
    search_url = "https://store.steampowered.com/search/"
    params = {
        'term': query,
        'category1': 998  # Games only
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        async with session.get(
            search_url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as response:
            if response.status != 200:
                logger.error(f"Steam search returned status {response.status}")
                return []
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            games = []
            search_results = soup.find_all('a', class_='search_result_row', limit=10)
            
            for result in search_results:
                try:
                    # Extract app ID from data-ds-appid attribute
                    appid = result.get('data-ds-appid')
                    if not appid:
                        continue
                    
                    # Extract game name
                    title_elem = result.find('span', class_='title')
                    if not title_elem:
                        continue
                    name = title_elem.text.strip()
                    
                    # Extract price
                    price_elem = result.find('div', class_='discount_final_price')
                    price = price_elem.text.strip() if price_elem else "Price not available"
                    
                    games.append({
                        'appid': appid,
                        'name': name,
                        'price': price
                    })
                    
                except Exception as e:
                    logger.warning(f"Error parsing search result: {e}")
                    continue
            
            logger.info(f"Found {len(games)} games for query: {query}")
            return games
            
    except asyncio.TimeoutError:
        logger.error("Steam search timed out")
        return []
    except Exception as e:
        logger.error(f"Error searching Steam: {e}", exc_info=True)
        return []


def fuzzy_match_games(query: str, games: List[Dict], threshold: float = 0.6) -> List[Dict]:
    """
    Filter and sort games by similarity to query using fuzzy matching.
    
    Args:
        query: Search query string
        games: List of game dictionaries with 'name' field
        threshold: Minimum similarity score (0.0-1.0) to include
    
    Returns:
        Sorted list of games by relevance
    """
    query_lower = query.lower()
    scored_games = []
    
    for game in games:
        name = game.get('name', '').lower()
        
        # Base similarity score
        similarity = SequenceMatcher(None, query_lower, name).ratio()
        
        # Boost exact substring matches
        if query_lower in name:
            similarity = min(1.0, similarity + 0.3)
        
        # Boost word-level matches (all query words in name)
        query_words = set(query_lower.split())
        name_words = set(name.split())
        if query_words.issubset(name_words):
            similarity = min(1.0, similarity + 0.2)
        
        # Boost if query is at start of name
        if name.startswith(query_lower):
            similarity = min(1.0, similarity + 0.25)
        
        # Only include games above threshold
        if similarity >= threshold:
            scored_games.append((similarity, game))
    
    # Sort by similarity (highest first)
    scored_games.sort(key=lambda x: x[0], reverse=True)
    
    return [game for score, game in scored_games]


async def fetch_game_details(appid: str, game_name: str) -> discord.Embed:
    """
    Fetch detailed game information from Steam and create an embed.
    
    Args:
        appid: Steam app ID
        game_name: Name of the game
    
    Returns:
        Discord embed with game details
    """
    details_url = f"https://store.steampowered.com/api/appdetails"
    params = {'appids': appid}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                details_url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status != 200:
                    raise Exception(f"API returned status {response.status}")
                
                data = await response.json()
                
                # Check if app data exists and is successful
                if appid not in data or not data[appid].get('success'):
                    raise Exception("Game data not found")
                
                game_data = data[appid]['data']
                
                # Create embed
                embed = discord.Embed(
                    title=game_data.get('name', game_name),
                    url=f"https://store.steampowered.com/app/{appid}",
                    description=clean_html(game_data.get('short_description', 'No description available.')),
                    color=discord.Color.blue()
                )
                
                # Add header image
                if 'header_image' in game_data:
                    embed.set_image(url=game_data['header_image'])
                
                # Price information
                price_info = game_data.get('price_overview', {})
                if price_info:
                    price_text = price_info.get('final_formatted', 'N/A')
                    if price_info.get('discount_percent', 0) > 0:
                        original = price_info.get('initial_formatted', '')
                        discount = price_info.get('discount_percent', 0)
                        price_text = f"~~{original}~~ **{price_text}** (-{discount}% OFF)"
                else:
                    price_text = "Free to Play" if game_data.get('is_free') else "Price not available"
                
                embed.add_field(name="💰 Price", value=price_text, inline=True)
                
                # Release date
                release_date = game_data.get('release_date', {})
                if release_date.get('date'):
                    coming_soon = "Coming Soon" if release_date.get('coming_soon') else release_date['date']
                    embed.add_field(name="📅 Release Date", value=coming_soon, inline=True)
                
                # Developers
                developers = game_data.get('developers', [])
                if developers:
                    embed.add_field(
                        name="👨‍💻 Developer",
                        value=', '.join(developers[:3]),  # Limit to 3
                        inline=True
                    )
                
                # Publishers
                publishers = game_data.get('publishers', [])
                if publishers:
                    embed.add_field(
                        name="🏢 Publisher",
                        value=', '.join(publishers[:3]),  # Limit to 3
                        inline=True
                    )
                
                # Genres
                genres = game_data.get('genres', [])
                if genres:
                    genre_names = [g.get('description', '') for g in genres[:5]]
                    embed.add_field(
                        name="🎮 Genres",
                        value=', '.join(genre_names),
                        inline=True
                    )
                
                # Platforms
                platforms = game_data.get('platforms', {})
                platform_icons = []
                if platforms.get('windows'):
                    platform_icons.append('🪟 Windows')
                if platforms.get('mac'):
                    platform_icons.append('🍎 Mac')
                if platforms.get('linux'):
                    platform_icons.append('🐧 Linux')
                
                if platform_icons:
                    embed.add_field(
                        name="💻 Platforms",
                        value=' • '.join(platform_icons),
                        inline=True
                    )
                
                # Metacritic score
                metacritic = game_data.get('metacritic', {})
                if metacritic.get('score'):
                    score = metacritic['score']
                    color_emoji = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"
                    embed.add_field(
                        name="📊 Metacritic",
                        value=f"{color_emoji} {score}/100",
                        inline=True
                    )
                
                # Recommendations (player count)
                recommendations = game_data.get('recommendations', {})
                if recommendations.get('total'):
                    total = recommendations['total']
                    formatted = f"{total:,}" if total < 1000000 else f"{total/1000000:.1f}M"
                    embed.add_field(
                        name="👍 Recommendations",
                        value=formatted,
                        inline=True
                    )
                
                # Requirements (PC minimum)
                pc_requirements = game_data.get('pc_requirements', {})
                if pc_requirements.get('minimum'):
                    # Truncate requirements to fit embed limits
                    min_req = clean_html(pc_requirements['minimum'])
                    if len(min_req) > 1024:
                        min_req = min_req[:1021] + "..."
                    embed.add_field(
                        name="⚙️ Minimum Requirements",
                        value=min_req,
                        inline=False
                    )
                
                # Footer
                embed.set_footer(text=f"Steam App ID: {appid} • Powered by Steam")
                
                return embed
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching details for {appid}")
            raise Exception("Request timed out")
        except Exception as e:
            logger.error(f"Error fetching game details: {e}", exc_info=True)
            raise


def clean_html(html_text: str) -> str:
    """
    Remove HTML tags and clean up text.
    
    Args:
        html_text: HTML string to clean
    
    Returns:
        Cleaned plain text
    """
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', html_text)
    
    # Replace common HTML entities
    clean = clean.replace('&quot;', '"')
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&lt;', '<')
    clean = clean.replace('&gt;', '>')
    clean = clean.replace('&nbsp;', ' ')
    clean = clean.replace('<br>', '\n')
    
    # Remove multiple spaces and newlines
    clean = re.sub(r'\s+', ' ', clean)
    clean = clean.strip()
    
    return clean


class SteamSearchCog(commands.Cog):
    """Steam game search with fuzzy matching and detailed information."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("SteamSearchCog initialized")
    
    @app_commands.command(
        name="steam-search",
        description="Search for a game on Steam and view detailed information"
    )
    @app_commands.describe(
        game_name="Name of the game to search for"
    )
    async def steam_search(self, interaction: discord.Interaction, game_name: str):
        """
        Search Steam store for games and display detailed information.
        
        Args:
            interaction: Discord interaction
            game_name: Name of the game to search for
        """
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Search Steam store
            async with aiohttp.ClientSession() as session:
                games = await search_steam_store(session, game_name)
            
            if not games:
                await interaction.followup.send(
                    f"❌ No games found for **{game_name}**. Try a different search term.",
                    ephemeral=True
                )
                return
            
            # Apply fuzzy matching to improve results
            matched_games = fuzzy_match_games(game_name, games, threshold=0.4)
            
            if not matched_games:
                await interaction.followup.send(
                    f"❌ No relevant games found for **{game_name}**. Try a different search term.",
                    ephemeral=True
                )
                return
            
            # Create dropdown with top 3 results
            top_games = matched_games[:3]
            view = GameSelectView(top_games, interaction.user.id)
            
            # Create result message
            result_text = f"🔍 **Search Results for:** {game_name}\n\n"
            result_text += "Select a game from the dropdown below to view detailed information:"
            
            await interaction.followup.send(
                result_text,
                view=view,
                ephemeral=True
            )
            
            logger.info(f"User {interaction.user.id} searched for '{game_name}' - {len(top_games)} results")
            
        except Exception as e:
            logger.error(f"Error in steam_search command: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ An error occurred while searching Steam. Please try again later.",
                    ephemeral=True
                )
            except:
                pass  # Interaction might be expired
    
    async def cog_load(self):
        """Called when cog loads."""
        logger.info("SteamSearchCog loaded successfully")
    
    async def cog_unload(self):
        """Called when cog unloads."""
        logger.info("SteamSearchCog unloaded")


async def setup(bot: commands.Bot):
    """Setup function required for cog loading."""


