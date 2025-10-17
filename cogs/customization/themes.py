"""
Enhanced Theme System for AniList Bot
Provides comprehensive theme customization with predefined themes, character themes, seasonal themes, and more.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Dict, List, Optional, Tuple, Union, Any
from enum import Enum
from datetime import datetime, timezone
import json
import logging
import asyncio
from dataclasses import dataclass, asdict
import random
from pathlib import Path

# Set up dedicated logging for theme system
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "themes.log"

logger = logging.getLogger("ThemeSystem")
logger.setLevel(logging.DEBUG)

if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == str(LOG_FILE)
           for h in logger.handlers):
    try:
        file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
                                                      datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(stream_handler)

logger.info("Theme system logging initialized")

# Database imports for bot moderator checks
from database import is_user_bot_moderator

def bot_moderator_only():
    """App command check that allows only bot moderators.
    Used for bot-wide administrative actions.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            return await is_user_bot_moderator(interaction.user)
        except Exception:
            return False

    return app_commands.check(predicate)


class ThemeCategory(Enum):
    """Categories for theme organization"""
    CLASSIC = "classic"
    ANIME_CHARACTER = "anime_character"
    SEASONAL = "seasonal"
    MOOD = "mood"
    GRADIENT = "gradient"
    MONOCHROME = "monochrome"
    NEON = "neon"
    CUSTOM = "custom"

class SeasonType(Enum):
    """Seasonal theme types"""
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"
    CHRISTMAS = "christmas"
    HALLOWEEN = "halloween"
    NEW_YEAR = "new_year"

@dataclass
class ThemeColors:
    """Color scheme for a theme"""
    primary: int          # Main embed color
    secondary: int        # Secondary elements
    accent: int          # Accent color for highlights
    text_primary: str    # Primary text color (hex)
    text_secondary: str  # Secondary text color (hex)
    background: str      # Background color hint (hex)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ThemeColors':
        return cls(**data)

@dataclass
class Theme:
    """Complete theme definition"""
    id: str
    name: str
    description: str
    category: ThemeCategory
    colors: ThemeColors
    emoji: str
    author: Optional[str] = None
    character_source: Optional[str] = None
    seasonal_period: Optional[Tuple[int, int]] = None  # (start_month, end_month)
    popularity_score: int = 0
    is_premium: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['category'] = self.category.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Theme':
        data['category'] = ThemeCategory(data['category'])
        data['colors'] = ThemeColors.from_dict(data['colors'])
        return cls(**data)

class ThemeManager:
    """Manages all theme operations and storage"""
    
    def __init__(self):
        self.themes: Dict[str, Theme] = {}
        self.user_themes: Dict[int, str] = {}  # user_id -> theme_id
        self.guild_themes: Dict[int, str] = {}  # guild_id -> theme_id
        self._initialize_predefined_themes()
    
    def _initialize_predefined_themes(self):
        """Initialize all predefined themes"""
        # Classic themes
        classic_themes = [
            Theme(
                id="default",
                name="Default Blue",
                description="The classic AniList blue theme",
                category=ThemeCategory.CLASSIC,
                colors=ThemeColors(0x02A9FF, 0x0080CC, 0x0066AA, "#FFFFFF", "#E1E8ED", "#F7F9FA"),
                emoji="🔵"
            ),
            Theme(
                id="dark_purple",
                name="Dark Purple",
                description="Elegant dark purple theme",
                category=ThemeCategory.CLASSIC,
                colors=ThemeColors(0x9D4EDD, 0x7B2CBF, 0x5A189A, "#FFFFFF", "#E9C46A", "#10002B"),
                emoji="🟣"
            ),
            Theme(
                id="crimson_red",
                name="Crimson Red",
                description="Bold crimson red theme",
                category=ThemeCategory.CLASSIC,
                colors=ThemeColors(0xDC143C, 0xB91C1C, 0x991B1B, "#FFFFFF", "#FED7D7", "#1A0000"),
                emoji="🔴"
            ),
            Theme(
                id="forest_green",
                name="Forest Green",
                description="Natural forest green theme",
                category=ThemeCategory.CLASSIC,
                colors=ThemeColors(0x22C55E, 0x16A34A, 0x15803D, "#FFFFFF", "#DCFCE7", "#0A0A0A"),
                emoji="🟢"
            ),
            Theme(
                id="sunset_orange",
                name="Sunset Orange",
                description="Warm sunset orange theme",
                category=ThemeCategory.CLASSIC,
                colors=ThemeColors(0xFF6B35, 0xE55100, 0xBF360C, "#FFFFFF", "#FFF3E0", "#1A0A00"),
                emoji="🟠"
            )
        ]
        
        # Character-based themes
        character_themes = [
            Theme(
                id="naruto",
                name="Naruto Uzumaki",
                description="Bright orange and blue like the Hokage",
                category=ThemeCategory.ANIME_CHARACTER,
                colors=ThemeColors(0xFF6600, 0x0066CC, 0xFFCC00, "#FFFFFF", "#FFF3E0", "#001122"),
                emoji="🍥",
                character_source="Naruto"
            ),
            Theme(
                id="goku",
                name="Son Goku",
                description="Orange and blue like Goku's gi",
                category=ThemeCategory.ANIME_CHARACTER,
                colors=ThemeColors(0xFF4500, 0x1E90FF, 0xFFD700, "#FFFFFF", "#FFF8DC", "#000033"),
                emoji="🔥",
                character_source="Dragon Ball"
            ),
            Theme(
                id="luffy",
                name="Monkey D. Luffy",
                description="Red and straw hat yellow",
                category=ThemeCategory.ANIME_CHARACTER,
                colors=ThemeColors(0xDC143C, 0xFFD700, 0x8B0000, "#FFFFFF", "#FFFACD", "#2F1B14"),
                emoji="👒",
                character_source="One Piece"
            ),
            Theme(
                id="tanjiro",
                name="Tanjiro Kamado",
                description="Green and black checkered pattern vibes",
                category=ThemeCategory.ANIME_CHARACTER,
                colors=ThemeColors(0x2D5A27, 0x000000, 0x4A7C59, "#FFFFFF", "#F0FFF0", "#0D1B0D"),
                emoji="⚔️",
                character_source="Demon Slayer"
            ),
            Theme(
                id="edward_elric",
                name="Edward Elric",
                description="Golden alchemy and red coat",
                category=ThemeCategory.ANIME_CHARACTER,
                colors=ThemeColors(0xDAA520, 0xB22222, 0xFFD700, "#FFFFFF", "#FFFACD", "#2B1810"),
                emoji="⚗️",
                character_source="Fullmetal Alchemist"
            ),
            Theme(
                id="violet_evergarden",
                name="Violet Evergarden",
                description="Elegant violet and gold",
                category=ThemeCategory.ANIME_CHARACTER,
                colors=ThemeColors(0x9370DB, 0xDAA520, 0xE6E6FA, "#FFFFFF", "#F5F5F5", "#2E1A47"),
                emoji="💌",
                character_source="Violet Evergarden"
            )
        ]
        
        # Seasonal themes
        seasonal_themes = [
            Theme(
                id="spring_sakura",
                name="Spring Sakura",
                description="Cherry blossom pink and fresh green",
                category=ThemeCategory.SEASONAL,
                colors=ThemeColors(0xFFB7C5, 0x90EE90, 0xFF69B4, "#2F4F2F", "#F0FFF0", "#FFF8F5"),
                emoji="🌸",
                seasonal_period=(3, 5)  # March to May
            ),
            Theme(
                id="summer_ocean",
                name="Summer Ocean",
                description="Ocean blue and sunny yellow",
                category=ThemeCategory.SEASONAL,
                colors=ThemeColors(0x00CED1, 0xFFD700, 0x87CEEB, "#FFFFFF", "#F0F8FF", "#001830"),
                emoji="🏖️",
                seasonal_period=(6, 8)  # June to August
            ),
            Theme(
                id="autumn_leaves",
                name="Autumn Leaves",
                description="Warm autumn colors",
                category=ThemeCategory.SEASONAL,
                colors=ThemeColors(0xD2691E, 0xCD853F, 0xDC143C, "#FFFFFF", "#FFF8DC", "#2F1B14"),
                emoji="🍂",
                seasonal_period=(9, 11)  # September to November
            ),
            Theme(
                id="winter_snow",
                name="Winter Snow",
                description="Cool winter whites and blues",
                category=ThemeCategory.SEASONAL,
                colors=ThemeColors(0x4682B4, 0xB0C4DE, 0x87CEEB, "#2F4F4F", "#F0F8FF", "#F8F8FF"),
                emoji="❄️",
                seasonal_period=(12, 2)  # December to February
            ),
            Theme(
                id="christmas_festive",
                name="Christmas Festive",
                description="Festive red and green",
                category=ThemeCategory.SEASONAL,
                colors=ThemeColors(0xDC143C, 0x228B22, 0xFFD700, "#FFFFFF", "#F0FFF0", "#0D2818"),
                emoji="🎄",
                seasonal_period=(12, 12)  # December only
            ),
            Theme(
                id="halloween_spooky",
                name="Halloween Spooky",
                description="Spooky orange and black",
                category=ThemeCategory.SEASONAL,
                colors=ThemeColors(0xFF4500, 0x000000, 0x8B0000, "#FFFFFF", "#FFF8DC", "#1A0A00"),
                emoji="🎃",
                seasonal_period=(10, 10)  # October only
            )
        ]
        
        # Mood-based themes
        mood_themes = [
            Theme(
                id="energetic",
                name="Energetic Burst",
                description="High-energy bright colors",
                category=ThemeCategory.MOOD,
                colors=ThemeColors(0xFF1493, 0x00FF7F, 0xFFD700, "#FFFFFF", "#FFFACD", "#1A001A"),
                emoji="⚡"
            ),
            Theme(
                id="calm_zen",
                name="Calm Zen",
                description="Peaceful and relaxing colors",
                category=ThemeCategory.MOOD,
                colors=ThemeColors(0x87CEEB, 0x98FB98, 0xE6E6FA, "#2F4F4F", "#F0F8FF", "#F5F5F5"),
                emoji="🧘"
            ),
            Theme(
                id="mysterious",
                name="Mysterious",
                description="Dark and mysterious atmosphere",
                category=ThemeCategory.MOOD,
                colors=ThemeColors(0x4B0082, 0x2F2F2F, 0x8A2BE2, "#E6E6FA", "#D8BFD8", "#0A0A0A"),
                emoji="🌙"
            ),
            Theme(
                id="romantic",
                name="Romantic",
                description="Soft romantic colors",
                category=ThemeCategory.MOOD,
                colors=ThemeColors(0xFFB6C1, 0xFFC0CB, 0xFF69B4, "#8B008B", "#FFF0F5", "#FFF8F8"),
                emoji="💕"
            )
        ]
        
        # Gradient themes
        gradient_themes = [
            Theme(
                id="sunset_gradient",
                name="Sunset Gradient",
                description="Beautiful sunset color transition",
                category=ThemeCategory.GRADIENT,
                colors=ThemeColors(0xFF4500, 0xFF6347, 0xFFD700, "#FFFFFF", "#FFF8DC", "#1A0A00"),
                emoji="🌅"
            ),
            Theme(
                id="ocean_gradient",
                name="Ocean Gradient",
                description="Deep ocean to surface transition",
                category=ThemeCategory.GRADIENT,
                colors=ThemeColors(0x000080, 0x4169E1, 0x87CEEB, "#FFFFFF", "#F0F8FF", "#000033"),
                emoji="🌊"
            ),
            Theme(
                id="aurora_gradient",
                name="Aurora Gradient",
                description="Northern lights inspired",
                category=ThemeCategory.GRADIENT,
                colors=ThemeColors(0x00FF7F, 0x00CED1, 0x9370DB, "#FFFFFF", "#F0FFF0", "#0A1A0A"),
                emoji="🌌"
            )
        ]
        
        # Neon themes
        neon_themes = [
            Theme(
                id="neon_cyberpunk",
                name="Neon Cyberpunk",
                description="Futuristic neon cyberpunk style",
                category=ThemeCategory.NEON,
                colors=ThemeColors(0x00FFFF, 0xFF00FF, 0x39FF14, "#FFFFFF", "#E0FFFF", "#000020"),
                emoji="🤖"
            ),
            Theme(
                id="neon_pink",
                name="Neon Pink",
                description="Electric hot pink theme",
                category=ThemeCategory.NEON,
                colors=ThemeColors(0xFF1493, 0xFF69B4, 0xFFB6C1, "#FFFFFF", "#FFF0F5", "#2A0A1A"),
                emoji="💖"
            )
        ]
        
        # Store all themes
        all_themes = classic_themes + character_themes + seasonal_themes + mood_themes + gradient_themes + neon_themes
        for theme in all_themes:
            self.themes[theme.id] = theme
        
        logger.info(f"Initialized {len(all_themes)} predefined themes")
    
    def get_theme(self, theme_id: str) -> Optional[Theme]:
        """Get a theme by ID"""
        return self.themes.get(theme_id)
    
    def get_themes_by_category(self, category: ThemeCategory) -> List[Theme]:
        """Get all themes in a category"""
        return [theme for theme in self.themes.values() if theme.category == category]
    
    def get_seasonal_theme(self) -> Optional[Theme]:
        """Get the appropriate seasonal theme for current date"""
        now = datetime.now()
        current_month = now.month
        
        # Check for special seasonal themes first
        if current_month == 12 and now.day >= 20:  # Christmas period
            return self.get_theme("christmas_festive")
        elif current_month == 10:  # Halloween
            return self.get_theme("halloween_spooky")
        
        # Regular seasonal themes
        for theme in self.themes.values():
            if theme.category == ThemeCategory.SEASONAL and theme.seasonal_period:
                start_month, end_month = theme.seasonal_period
                if start_month <= end_month:
                    if start_month <= current_month <= end_month:
                        return theme
                else:  # Winter case (Dec-Feb)
                    if current_month >= start_month or current_month <= end_month:
                        return theme
        
        return None
    
    def get_popular_themes(self, limit: int = 10) -> List[Theme]:
        """Get most popular themes"""
        return sorted(self.themes.values(), key=lambda t: t.popularity_score, reverse=True)[:limit]
    
    def search_themes(self, query: str) -> List[Theme]:
        """Search themes by name or description"""
        query_lower = query.lower()
        results = []
        
        for theme in self.themes.values():
            if (query_lower in theme.name.lower() or 
                query_lower in theme.description.lower() or 
                (theme.character_source and query_lower in theme.character_source.lower())):
                results.append(theme)
        
        return results
    
    def set_user_theme(self, user_id: int, theme_id: str) -> bool:
        """Set a user's theme"""
        if theme_id in self.themes:
            self.user_themes[user_id] = theme_id
            return True
        return False
    
    def get_user_theme(self, user_id: int) -> Optional[Theme]:
        """Get a user's current theme"""
        theme_id = self.user_themes.get(user_id)
        if theme_id:
            return self.get_theme(theme_id)
        return None
    
    def set_guild_theme(self, guild_id: int, theme_id: str) -> bool:
        """Set a guild's default theme"""
        if theme_id in self.themes:
            self.guild_themes[guild_id] = theme_id
            return True
        return False
    
    def get_effective_theme(self, user_id: int, guild_id: Optional[int] = None) -> Theme:
        """Get the effective theme for a user (user > guild > seasonal > default)"""
        # User preference first
        user_theme = self.get_user_theme(user_id)
        if user_theme:
            return user_theme
        
        # Guild theme second
        if guild_id and guild_id in self.guild_themes:
            guild_theme = self.get_theme(self.guild_themes[guild_id])
            if guild_theme:
                return guild_theme
        
        # Seasonal theme third
        seasonal_theme = self.get_seasonal_theme()
        if seasonal_theme:
            return seasonal_theme
        
        # Default theme last
        return self.get_theme("default")


class ThemeMainMenuView(discord.ui.View):
    """Main menu view for unified theme system"""
    
    def __init__(self, theme_cog):
        super().__init__(timeout=300.0)
        self.theme_cog = theme_cog
    
    @discord.ui.button(label="🔍 Browse & Preview", style=discord.ButtonStyle.primary, row=0)
    async def browse_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open interactive theme browser with live preview"""
        try:
            from .theme_showcase import ThemeCategoryView
            
            embed = discord.Embed(
                title="🎨 Theme Preview & Browser",
                description=(
                    "Choose a category below to preview and test themes!\n\n"
                    "🖱️ **How to use:**\n"
                    "• Select a category from the dropdown\n"
                    "• Navigate through themes with buttons\n"
                    "• Preview how embeds look with each theme\n"
                    "• Apply themes you like instantly"
                ),
                color=0x02A9FF
            )
            
            embed.add_field(
                name="🌟 Features",
                value="• Live theme preview\n• Interactive navigation\n• Instant application\n• Random discovery",
                inline=True
            )
            
            embed.add_field(
                name="📊 Available",
                value=f"• {len(self.theme_cog.theme_manager.themes)} total themes\n• 7 categories\n• Character themes\n• Seasonal themes",
                inline=True
            )
            
            view = ThemeCategoryView(self.theme_cog.theme_manager)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.info(f"Theme browser opened for user {interaction.user.id}")
        except Exception as e:
            logger.error(f"Error opening theme browser: {e}")
            await interaction.response.send_message("❌ Error opening theme browser.", ephemeral=True)
    
    @discord.ui.button(label="📋 View All Themes", style=discord.ButtonStyle.secondary, row=0)
    async def showcase_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show comprehensive theme showcase"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            themes = list(self.theme_cog.theme_manager.themes.values())
            
            # Group themes by category
            category_themes = {}
            for theme in themes:
                cat = theme.category.value
                if cat not in category_themes:
                    category_themes[cat] = []
                category_themes[cat].append(theme)
            
            embed = discord.Embed(
                title="🎨 Complete Theme Showcase",
                description=f"Browse all **{len(themes)}** available themes organized by category:",
                color=0x02A9FF
            )
            
            for category_name, cat_themes in sorted(category_themes.items()):
                theme_list = "\n".join([f"{t.emoji} **{t.name}** - {t.description[:50]}..." for t in cat_themes[:5]])
                if len(cat_themes) > 5:
                    theme_list += f"\n*... and {len(cat_themes) - 5} more*"
                
                embed.add_field(
                    name=f"{category_name.replace('_', ' ').title()} ({len(cat_themes)} themes)",
                    value=theme_list,
                    inline=False
                )
            
            embed.set_footer(text="Use 'Browse & Preview' to see themes in action!")
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Theme showcase sent to user {interaction.user.id}")
        except Exception as e:
            logger.error(f"Error in theme showcase: {e}")
            await interaction.followup.send("❌ Error loading theme showcase.", ephemeral=True)
    
    @discord.ui.button(label="⚙️ My Current Theme", style=discord.ButtonStyle.secondary, row=1)
    async def current_theme(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show current theme details"""
        guild_id = interaction.guild.id if interaction.guild else None
        theme = self.theme_cog.theme_manager.get_effective_theme(interaction.user.id, guild_id)
        
        embed = discord.Embed(
            title=f"{theme.emoji} {theme.name}",
            description=theme.description,
            color=theme.colors.primary
        )
        
        embed.add_field(
            name="📁 Category",
            value=theme.category.value.replace('_', ' ').title(),
            inline=True
        )
        
        if theme.character_source:
            embed.add_field(name="📺 Source", value=theme.character_source, inline=True)
        
        color_info = f"**Primary:** #{theme.colors.primary:06X}\n**Secondary:** #{theme.colors.secondary:06X}\n**Accent:** #{theme.colors.accent:06X}"
        embed.add_field(name="🎨 Colors", value=color_info, inline=False)
        
        embed.add_field(
            name="📖 Sample",
            value="**Title:** Attack on Titan\n**Status:** Completed\n**Score:** 9/10\n**Progress:** 139/139",
            inline=False
        )
        
        embed.set_footer(text=f"Theme: {theme.name} {theme.emoji}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Current theme details sent to user {interaction.user.id}")
    
    @discord.ui.button(label="🎲 Random Theme", style=discord.ButtonStyle.secondary, row=1)
    async def random_theme(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Apply a random theme"""
        import random
        themes = list(self.theme_cog.theme_manager.themes.values())
        theme = random.choice(themes)
        
        guild_id = interaction.guild.id if interaction.guild else None
        self.theme_cog.theme_manager.set_user_theme(interaction.user.id, theme.id)
        
        embed = discord.Embed(
            title=f"🎲 Random Theme Applied: {theme.name}",
            description=f"Your theme has been randomly set to **{theme.name}**!\n\n*{theme.description}*",
            color=theme.colors.primary
        )
        embed.set_footer(text=f"Feeling lucky? Theme: {theme.name} {theme.emoji}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Random theme '{theme.name}' applied for user {interaction.user.id}")
    
    @discord.ui.button(label="🌸 Seasonal Theme", style=discord.ButtonStyle.secondary, row=2)
    async def seasonal_theme(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Apply current seasonal theme"""
        theme = self.theme_cog.theme_manager.get_seasonal_theme()
        
        if not theme:
            await interaction.response.send_message("❌ No seasonal theme available for current month.", ephemeral=True)
            return
        
        guild_id = interaction.guild.id if interaction.guild else None
        self.theme_cog.theme_manager.set_user_theme(interaction.user.id, theme.id)
        
        embed = discord.Embed(
            title=f"🌸 Seasonal Theme Applied: {theme.name}",
            description=f"Your theme has been set to the current seasonal theme **{theme.name}**!\n\n*{theme.description}*",
            color=theme.colors.primary
        )
        embed.set_footer(text=f"Perfect for the season! Theme: {theme.name} {theme.emoji}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Seasonal theme '{theme.name}' applied for user {interaction.user.id}")
    
    @discord.ui.button(label="🔄 Reset to Default", style=discord.ButtonStyle.danger, row=2)
    async def reset_theme(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Reset to default theme"""
        self.theme_cog.theme_manager.set_user_theme(interaction.user.id, "default")
        theme = self.theme_cog.theme_manager.get_theme("default")
        
        embed = discord.Embed(
            title="🔄 Theme Reset",
            description=f"Your theme has been reset to the default **{theme.name}** theme.",
            color=theme.colors.primary
        )
        embed.set_footer(text=f"Back to basics! Theme: {theme.name} {theme.emoji}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Theme reset to default for user {interaction.user.id}")


class CustomThemeSystem(commands.Cog):
    """Custom Theme System for the AniList bot"""
    
    def __init__(self, bot):
        self.bot = bot
        self.theme_manager = ThemeManager()
        logger.info("Custom Theme System initialized")
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        logger.info("Custom Theme System loaded successfully")
    
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        logger.info("Custom Theme System unloaded")
    
    def apply_theme_to_embed(self, embed: discord.Embed, theme: Theme, user_id: int) -> discord.Embed:
        """Apply a theme to a Discord embed"""
        embed.color = theme.colors.primary
        
        # Add theme footer
        if embed.footer.text:
            embed.set_footer(text=f"{embed.footer.text} • Theme: {theme.name} {theme.emoji}")
        else:
            embed.set_footer(text=f"Theme: {theme.name} {theme.emoji}")
        
        return embed
    
    @app_commands.command(name="theme", description="🎨 Complete theme customization system - Browse, preview, and apply themes")
    async def theme_command(self, interaction: discord.Interaction):
        """Unified theme management command with interactive interface"""
        try:
            guild_id = interaction.guild.id if interaction.guild else None
            logger.info(f"Theme command invoked by {interaction.user.display_name} ({interaction.user.id}) in guild {guild_id}")
            
            # Get current theme info
            current_theme = self.theme_manager.get_effective_theme(interaction.user.id, guild_id)
            total_themes = len(self.theme_manager.themes)
            
            embed = discord.Embed(
                title="🎨 Theme Management System",
                description=(
                    "Welcome to the complete theme customization system!\n\n"
                    "**Your Current Theme:**\n"
                    f"{current_theme.emoji} **{current_theme.name}**\n"
                    f"*{current_theme.description}*\n\n"
                    "Choose an option below to get started:"
                ),
                color=current_theme.colors.primary
            )
            
            embed.add_field(
                name="📊 System Info",
                value=f"• **{total_themes}** total themes\n• **7** categories\n• Character themes\n• Seasonal themes",
                inline=True
            )
            
            embed.add_field(
                name="🌟 Features",
                value="• Live preview\n• Interactive browser\n• Quick apply\n• Random selection",
                inline=True
            )
            
            if interaction.guild:
                embed.set_footer(text=f"Guild: {interaction.guild.name} | Theme: {current_theme.name} {current_theme.emoji}")
            else:
                embed.set_footer(text=f"DM | Theme: {current_theme.name} {current_theme.emoji}")
            
            view = ThemeMainMenuView(self)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.info(f"Theme main menu sent to user {interaction.user.id} in guild {guild_id}")
        
        except Exception as e:
            guild_id = interaction.guild.id if interaction.guild else None
            logger.error(f"Error in theme command for user {interaction.user.id} in guild {guild_id}: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while opening theme system. Please try again.",
                color=0xFF0000
            )
            
            try:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as follow_e:
                logger.error(f"Failed to send error message: {follow_e}")
    
    async def _handle_browse_themes(self, interaction: discord.Interaction, category: str):
        """Handle browsing available themes"""
        if category == "all":
            themes = list(self.theme_manager.themes.values())
        else:
            try:
                cat_enum = ThemeCategory(category)
                themes = self.theme_manager.get_themes_by_category(cat_enum)
            except ValueError:
                themes = list(self.theme_manager.themes.values())
        
        if not themes:
            embed = discord.Embed(
                title="📋 No Themes Found",
                description=f"No themes found in category: {category}",
                color=0xFFA500
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Create theme browser embed
        embed = discord.Embed(
            title=f"🎨 Available Themes ({len(themes)})",
            description=f"**Category:** {category.title() if category != 'all' else 'All Categories'}\n\n",
            color=0x02A9FF
        )
        
        # Group themes by category for better display
        by_category = {}
        for theme in themes[:15]:  # Limit to 15 for embed space
            cat = theme.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(theme)
        
        for cat, cat_themes in by_category.items():
            theme_list = []
            for theme in cat_themes:
                theme_list.append(f"{theme.emoji} **{theme.name}**")
                if theme.character_source:
                    theme_list.append(f"   └ *from {theme.character_source}*")
                else:
                    theme_list.append(f"   └ *{theme.description}*")
            
            embed.add_field(
                name=f"📁 {cat.replace('_', ' ').title()}",
                value="\n".join(theme_list[:8]) + (f"\n*...and {len(theme_list)-8} more*" if len(theme_list) > 8 else ""),
                inline=False
            )
        
        embed.add_field(
            name="💡 How to Use",
            value="`/theme set <theme_name>` - Apply a theme\n`/theme current` - View your current theme\n`/theme seasonal` - Auto seasonal theme",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    async def _handle_set_theme(self, interaction: discord.Interaction, theme_name: Optional[str]):
        """Handle setting a user's theme"""
        if not theme_name:
            embed = discord.Embed(
                title="❌ Missing Theme Name",
                description="Please specify a theme name to apply.\nUse `/theme browse` to see available themes.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Search for theme by name (fuzzy matching)
        found_theme = None
        theme_name_lower = theme_name.lower()
        
        # Exact match first
        for theme in self.theme_manager.themes.values():
            if theme.name.lower() == theme_name_lower:
                found_theme = theme
                break
        
        # Partial match if no exact match
        if not found_theme:
            for theme in self.theme_manager.themes.values():
                if theme_name_lower in theme.name.lower():
                    found_theme = theme
                    break
        
        # ID match as fallback
        if not found_theme:
            found_theme = self.theme_manager.get_theme(theme_name_lower)
        
        if not found_theme:
            embed = discord.Embed(
                title="❌ Theme Not Found",
                description=f"Could not find theme: `{theme_name}`\nUse `/theme browse` to see available themes.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Apply the theme
        success = self.theme_manager.set_user_theme(interaction.user.id, found_theme.id)
        
        if success:
            # Create themed embed to show the new theme
            embed = discord.Embed(
                title=f"✅ Theme Applied: {found_theme.name}",
                description=found_theme.description,
                color=found_theme.colors.primary
            )
            
            embed.add_field(
                name="🎨 Theme Details",
                value=f"**Category:** {found_theme.category.value.replace('_', ' ').title()}\n"
                      f"**Colors:** Primary theme applied\n"
                      f"**Emoji:** {found_theme.emoji}",
                inline=False
            )
            
            if found_theme.character_source:
                embed.add_field(
                    name="📺 Character Source",
                    value=found_theme.character_source,
                    inline=True
                )
            
            embed.set_footer(text=f"Theme: {found_theme.name} {found_theme.emoji}")
            
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Failed to Apply Theme",
                description="An error occurred while applying the theme.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)
    
    async def _handle_current_theme(self, interaction: discord.Interaction):
        """Show user's current theme"""
        current_theme = self.theme_manager.get_effective_theme(
            interaction.user.id, 
            interaction.guild.id if interaction.guild else None
        )
        
        embed = discord.Embed(
            title=f"🎨 Your Current Theme: {current_theme.name}",
            description=current_theme.description,
            color=current_theme.colors.primary
        )
        
        user_theme = self.theme_manager.get_user_theme(interaction.user.id)
        theme_source = "Personal choice" if user_theme else "Auto-selected"
        
        embed.add_field(
            name="📋 Theme Info",
            value=f"**Source:** {theme_source}\n"
                  f"**Category:** {current_theme.category.value.replace('_', ' ').title()}\n"
                  f"**Emoji:** {current_theme.emoji}",
            inline=True
        )
        
        if current_theme.character_source:
            embed.add_field(
                name="📺 Character Source",
                value=current_theme.character_source,
                inline=True
            )
        
        # Color preview
        color_preview = f"**Primary:** #{current_theme.colors.primary:06X}\n"
        color_preview += f"**Secondary:** #{current_theme.colors.secondary:06X}\n"
        color_preview += f"**Accent:** #{current_theme.colors.accent:06X}"
        
        embed.add_field(
            name="🎨 Color Scheme",
            value=color_preview,
            inline=False
        )
        
        embed.set_footer(text=f"Theme: {current_theme.name} {current_theme.emoji}")
        
        await interaction.followup.send(embed=embed)
    
    async def _handle_random_theme(self, interaction: discord.Interaction):
        """Apply a random theme"""
        themes = list(self.theme_manager.themes.values())
        random_theme = random.choice(themes)
        
        self.theme_manager.set_user_theme(interaction.user.id, random_theme.id)
        
        embed = discord.Embed(
            title=f"🎲 Random Theme: {random_theme.name}",
            description=f"🎉 Surprise! {random_theme.description}",
            color=random_theme.colors.primary
        )
        
        embed.add_field(
            name="🎨 Theme Details",
            value=f"**Category:** {random_theme.category.value.replace('_', ' ').title()}\n"
                  f"**Emoji:** {random_theme.emoji}",
            inline=False
        )
        
        if random_theme.character_source:
            embed.add_field(
                name="📺 From",
                value=random_theme.character_source,
                inline=True
            )
        
        embed.set_footer(text=f"Theme: {random_theme.name} {random_theme.emoji}")
        
        await interaction.followup.send(embed=embed)
    
    async def _handle_seasonal_theme(self, interaction: discord.Interaction):
        """Apply the current seasonal theme"""
        seasonal_theme = self.theme_manager.get_seasonal_theme()
        
        if not seasonal_theme:
            embed = discord.Embed(
                title="🌟 No Seasonal Theme",
                description="There's no special seasonal theme available right now.\nTry again during special seasons!",
                color=0xFFA500
            )
            await interaction.followup.send(embed=embed)
            return
        
        self.theme_manager.set_user_theme(interaction.user.id, seasonal_theme.id)
        
        embed = discord.Embed(
            title=f"🌸 Seasonal Theme: {seasonal_theme.name}",
            description=f"Perfect for this time of year! {seasonal_theme.description}",
            color=seasonal_theme.colors.primary
        )
        
        embed.add_field(
            name="📅 Season Info",
            value=f"**Current Season:** {seasonal_theme.name}\n"
                  f"**Emoji:** {seasonal_theme.emoji}",
            inline=False
        )
        
        embed.set_footer(text=f"Theme: {seasonal_theme.name} {seasonal_theme.emoji}")
        
        await interaction.followup.send(embed=embed)
    
    async def _handle_reset_theme(self, interaction: discord.Interaction):
        """Reset user's theme to default"""
        if interaction.user.id in self.theme_manager.user_themes:
            del self.theme_manager.user_themes[interaction.user.id]
        
        default_theme = self.theme_manager.get_theme("default")
        
        embed = discord.Embed(
            title="🔄 Theme Reset",
            description="Your theme has been reset to default. Seasonal themes will be applied automatically!",
            color=default_theme.colors.primary
        )
        
        embed.set_footer(text=f"Theme: {default_theme.name} {default_theme.emoji}")
        
        await interaction.followup.send(embed=embed)
    
    @bot_moderator_only()
    @app_commands.command(name="admin-guild-theme", description="Manage guild-wide theme settings (Bot Moderator only)")
    @app_commands.describe(
        action="What would you like to do?",
        theme="Theme to set as guild default"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Set Guild Theme", value="set"),
        app_commands.Choice(name="View Current", value="current"),
        app_commands.Choice(name="Reset to Default", value="reset")
    ])
    async def admin_guild_theme_command(
        self,
        interaction: discord.Interaction,
        action: str,
        theme: Optional[str] = None
    ):
        """Guild theme management (bot moderator only)"""
        try:
            guild_id = interaction.guild.id if interaction.guild else None
            logger.info(f"Admin guild theme command invoked by {interaction.user.display_name} ({interaction.user.id}) in guild {guild_id} ({interaction.guild.name if interaction.guild else 'DM'}): action={action}, theme={theme}")
            
            await interaction.response.defer()
            
            if action == "set":
                await self._handle_set_guild_theme(interaction, theme)
            elif action == "current":
                await self._handle_current_guild_theme(interaction)
            elif action == "reset":
                await self._handle_reset_guild_theme(interaction)
        
        except Exception as e:
            logger.error(f"Error in admin-guild-theme command: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while processing the guild theme request.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)
    
    async def _handle_set_guild_theme(self, interaction: discord.Interaction, theme_name: Optional[str]):
        """Set guild default theme"""
        if not theme_name:
            embed = discord.Embed(
                title="❌ Missing Theme Name",
                description="Please specify a theme name for the guild.\nUse `/theme browse` to see available themes.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Find theme (same logic as personal themes)
        found_theme = None
        theme_name_lower = theme_name.lower()
        
        for theme in self.theme_manager.themes.values():
            if theme.name.lower() == theme_name_lower or theme_name_lower in theme.name.lower():
                found_theme = theme
                break
        
        if not found_theme:
            found_theme = self.theme_manager.get_theme(theme_name_lower)
        
        if not found_theme:
            embed = discord.Embed(
                title="❌ Theme Not Found",
                description=f"Could not find theme: `{theme_name}`",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Apply guild theme
        success = self.theme_manager.set_guild_theme(interaction.guild.id, found_theme.id)
        
        if success:
            embed = discord.Embed(
                title=f"✅ Guild Theme Set: {found_theme.name}",
                description=f"Guild default theme is now: {found_theme.description}",
                color=found_theme.colors.primary
            )
            
            embed.add_field(
                name="📋 Note",
                value="This theme applies to users who haven't set a personal theme.",
                inline=False
            )
            
            embed.set_footer(text=f"Theme: {found_theme.name} {found_theme.emoji}")
            
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Failed to Set Guild Theme",
                description="An error occurred while setting the guild theme.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed)
    
    async def _handle_current_guild_theme(self, interaction: discord.Interaction):
        """Show current guild theme"""
        guild_theme_id = self.theme_manager.guild_themes.get(interaction.guild.id)
        
        if guild_theme_id:
            guild_theme = self.theme_manager.get_theme(guild_theme_id)
            embed = discord.Embed(
                title=f"🏰 Guild Theme: {guild_theme.name}",
                description=guild_theme.description,
                color=guild_theme.colors.primary
            )
            embed.set_footer(text=f"Theme: {guild_theme.name} {guild_theme.emoji}")
        else:
            embed = discord.Embed(
                title="🏰 Guild Theme",
                description="No guild theme is set. Using default/seasonal themes.",
                color=0x02A9FF
            )
        
        await interaction.followup.send(embed=embed)
    
    async def _handle_reset_guild_theme(self, interaction: discord.Interaction):
        """Reset guild theme"""
        if interaction.guild.id in self.theme_manager.guild_themes:
            del self.theme_manager.guild_themes[interaction.guild.id]
        
        embed = discord.Embed(
            title="🔄 Guild Theme Reset",
            description="Guild theme has been reset. Default and seasonal themes will be used.",
            color=0x02A9FF
        )
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(CustomThemeSystem(bot))
    logger.info("Custom Theme System cog loaded successfully")