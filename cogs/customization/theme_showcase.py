"""
Theme Showcase and Testing System
Interactive views for theme preview and advanced theme management.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional, Dict, Any
import asyncio
import logging
from pathlib import Path
from helpers.embed_helper import build_error_embed, build_info_embed

# Set up dedicated logging for theme showcase
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "theme_showcase.log"

logger = logging.getLogger("ThemeShowcase")
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

logger.info("Theme showcase logging initialized")

class ThemePreviewView(discord.ui.View):
    """Interactive view for previewing themes"""
    
    def __init__(self, theme_manager, user_id: int, themes: List, current_index: int = 0):
        super().__init__(timeout=300.0)
        self.theme_manager = theme_manager
        self.user_id = user_id
        self.themes = themes
        self.current_index = current_index
        self.max_index = len(themes) - 1
        
        # Update button states
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current position"""
        # Previous button
        prev_button = self.children[0]
        prev_button.disabled = self.current_index == 0
        
        # Next button  
        next_button = self.children[1]
        next_button.disabled = self.current_index >= self.max_index
        
        # Apply button
        apply_button = self.children[2]
        apply_button.disabled = False
    
    def _get_preview_embed(self) -> discord.Embed:
        """Create preview embed for current theme"""
        if not self.themes:
            return build_error_embed("No Themes", "No themes available for preview.")
        
        theme = self.themes[self.current_index]
        
        embed = discord.Embed(
            title=f"🎨 Theme Preview: {theme.name}",
            description=f"**Description:** {theme.description}\n"
                       f"**Category:** {theme.category.value.replace('_', ' ').title()}\n"
                       f"**Emoji:** {theme.emoji}",
            color=theme.colors.primary
        )
        
        if theme.character_source:
            embed.add_field(
                name="📺 Character Source",
                value=theme.character_source,
                inline=True
            )
        
        # Color showcase
        color_info = f"**Primary:** #{theme.colors.primary:06X}\n"
        color_info += f"**Secondary:** #{theme.colors.secondary:06X}\n"
        color_info += f"**Accent:** #{theme.colors.accent:06X}"
        
        embed.add_field(
            name="🎨 Colors",
            value=color_info,
            inline=True
        )
        
        embed.add_field(
            name="📍 Navigation",
            value=f"Theme {self.current_index + 1} of {len(self.themes)}",
            inline=False
        )
        
        # Sample content to show theme in action
        embed.add_field(
            name="📖 Sample Content",
            value="**Title:** Attack on Titan\n"
                  "**Status:** Completed\n"
                  "**Score:** 9/10\n"
                  "**Progress:** 139/139 chapters",
            inline=False
        )
        
        embed.set_footer(text=f"Theme: {theme.name} {theme.emoji}")
        
        return embed
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary)
    async def previous_theme(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous theme"""
        if self.current_index > 0:
            self.current_index -= 1
            self._update_buttons()
            
            embed = self._get_preview_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next_theme(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next theme"""
        if self.current_index < self.max_index:
            self.current_index += 1
            self._update_buttons()
            
            embed = self._get_preview_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="✅ Apply Theme", style=discord.ButtonStyle.primary)
    async def apply_theme(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Apply the current theme"""
        if not self.themes:
            await interaction.response.defer()
            return
        
        theme = self.themes[self.current_index]
        guild_id = interaction.guild.id if interaction.guild else None
        logger.info(f"User {interaction.user.id} applying theme '{theme.name}' from preview in guild {guild_id}")
        
        success = self.theme_manager.set_user_theme(self.user_id, theme.id)
        
        if success:
            embed = discord.Embed(
                title=f"✅ Theme Applied: {theme.name}",
                description=f"🎉 Your theme has been set to **{theme.name}**!\n"
                           f"All your embeds will now use this beautiful theme.",
                color=theme.colors.primary
            )
            
            # Add guild context to footer
            if interaction.guild:
                embed.set_footer(text=f"Theme: {theme.name} {theme.emoji} | Applied in {interaction.guild.name}")
            else:
                embed.set_footer(text=f"Theme: {theme.name} {theme.emoji} | Applied globally")
            
            # Disable all buttons
            for child in self.children:
                child.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=self)
            logger.info(f"Successfully applied theme '{theme.name}' for user {interaction.user.id}")
        else:
            logger.error(f"Failed to apply theme '{theme.name}' for user {interaction.user.id}")
            embed = build_error_embed("Failed to Apply Theme", "An error occurred while applying the theme.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🎲 Random", style=discord.ButtonStyle.secondary)
    async def random_theme(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Jump to a random theme"""
        import random
        new_index = random.randint(0, self.max_index)
        
        if new_index != self.current_index:
            self.current_index = new_index
            self._update_buttons()
            
            embed = self._get_preview_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the preview"""
        embed = build_info_embed(
            "🎨 Theme Preview Closed",
            "Theme preview session ended."
        )
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)

class ThemeCategorySelect(discord.ui.Select):
    """Dropdown for selecting theme categories"""
    
    def __init__(self, theme_manager):
        self.theme_manager = theme_manager
        
        options = [
            discord.SelectOption(
                label="All Themes",
                description="Browse all available themes",
                emoji="🎨",
                value="all"
            ),
            discord.SelectOption(
                label="Classic",
                description="Traditional color themes",
                emoji="🔵",
                value="classic"
            ),
            discord.SelectOption(
                label="Anime Characters",
                description="Themes inspired by anime characters",
                emoji="👤",
                value="anime_character"
            ),
            discord.SelectOption(
                label="Seasonal",
                description="Themes that change with the seasons",
                emoji="🌸",
                value="seasonal"
            ),
            discord.SelectOption(
                label="Mood-based",
                description="Themes that match your mood",
                emoji="😊",
                value="mood"
            ),
            discord.SelectOption(
                label="Gradient",
                description="Beautiful gradient color schemes",
                emoji="🌈",
                value="gradient"
            ),
            discord.SelectOption(
                label="Neon",
                description="Bright neon themes",
                emoji="💫",
                value="neon"
            )
        ]
        
        super().__init__(
            placeholder="Choose a theme category to preview...",
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle category selection"""
        try:
            from .themes import ThemeCategory
            
            if self.values[0] == "all":
                themes = list(self.theme_manager.themes.values())
            else:
                category = ThemeCategory(self.values[0])
                themes = self.theme_manager.get_themes_by_category(category)
            
            if not themes:
                embed = build_error_embed(
                    "No Themes Found",
                    f"No themes available in category: {self.values[0]}"
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Create preview view
            view = ThemePreviewView(self.theme_manager, interaction.user.id, themes)
            embed = view._get_preview_embed()
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in theme category callback: {e}", exc_info=True)
            embed = build_error_embed(
                "Error",
                "An error occurred while loading themes."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class ThemeCategoryView(discord.ui.View):
    """View for theme category selection"""
    
    def __init__(self, theme_manager):
        super().__init__(timeout=300.0)
        self.add_item(ThemeCategorySelect(theme_manager))


# Legacy standalone commands removed - all theme functionality now accessible through unified /theme command
# This file now only provides the views/classes (ThemePreviewView, ThemeCategorySelect, etc.) 
# used by the main theme system in themes.py


async def setup(bot):
    """Setup function for the cog"""
    # Note: No cog to register - this file now only provides view classes
    logger.info("Theme showcase views loaded (commands integrated into unified /theme interface)")