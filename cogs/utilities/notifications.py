import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select
import logging
from pathlib import Path
from typing import Dict, List, Optional
import config
from cogs_test.general_commands.dashboard import command_meta

# ------------------------------------------------------
# Logging Setup
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "notifications.log"

# Setup logger
logger = logging.getLogger("notifications")
logger.setLevel(logging.INFO)

# Only add handler if not already present
if not logger.handlers:
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging for notifications: {e}")


# ------------------------------------------------------
# Notification Type Configuration
# ------------------------------------------------------
NOTIFICATION_TYPES = {
    "bot-updates": {
        "name": "Bot Updates",
        "role_name": "bot-updates",
        "emoji": "🤖",
        "color": discord.Color.blue(),
        "description": "New features, important updates, bug fixes"
    },
    "maintenance": {
        "name": "Maintenance Alerts",
        "role_name": "maintenance-alerts",
        "emoji": "🔧",
        "color": discord.Color.orange(),
        "description": "Scheduled downtime, maintenance windows"
    },
    "features": {
        "name": "Feature Releases",
        "role_name": "feature-releases",
        "emoji": "✨",
        "color": discord.Color.purple(),
        "description": "Major new features and capabilities"
    },
    "events": {
        "name": "Community Events",
        "role_name": "community-events",
        "emoji": "🎉",
        "color": discord.Color.green(),
        "description": "Server events, contests, activities"
    },
    "challenges": {
        "name": "Challenge Notifications",
        "role_name": "challenge-notifications",
        "emoji": "🏆",
        "color": discord.Color.gold(),
        "description": "Reading challenges, leaderboard updates"
    },
    "news": {
        "name": "Anime News",
        "role_name": "anime-news",
        "emoji": "📰",
        "color": discord.Color.red(),
        "description": "Anime/manga news from monitored sources"
    }
}


class NotificationTypeSelect(Select):
    """Dropdown select for choosing notification types to subscribe to"""

    def __init__(self, cog: 'NotificationsCog', current_subscriptions: List[str]):
        self.cog = cog
        self.current_subscriptions = current_subscriptions

        # Create options for each notification type
        options = []
        for type_key, type_info in NOTIFICATION_TYPES.items():
            is_subscribed = type_key in current_subscriptions
            options.append(
                discord.SelectOption(
                    label=type_info["name"],
                    value=type_key,
                    description=type_info["description"],
                    emoji=type_info["emoji"],
                    default=is_subscribed
                )
            )

        super().__init__(
            placeholder="Select notification types to subscribe to...",
            min_values=0,
            max_values=len(NOTIFICATION_TYPES),
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle notification type selection"""
        await interaction.response.defer()

        selected_types = self.values  # List of selected type keys

        # Determine which to add and which to remove
        to_add = set(selected_types) - set(self.current_subscriptions)
        to_remove = set(self.current_subscriptions) - set(selected_types)

        added_count = 0
        removed_count = 0
        errors = []

        # Add new subscriptions
        for type_key in to_add:
            try:
                role = await self.cog.get_or_create_notification_role(interaction.guild, type_key)
                await interaction.user.add_roles(role, reason=f"Subscribed to {NOTIFICATION_TYPES[type_key]['name']}")
                added_count += 1
                logger.info(f"User {interaction.user.id} subscribed to {type_key}")
            except Exception as e:
                logger.error(f"Error adding {type_key} role to user {interaction.user.id}: {e}")
                errors.append(f"Failed to subscribe to {NOTIFICATION_TYPES[type_key]['name']}")

        # Remove old subscriptions
        for type_key in to_remove:
            try:
                role = await self.cog.get_or_create_notification_role(interaction.guild, type_key)
                await interaction.user.remove_roles(role, reason=f"Unsubscribed from {NOTIFICATION_TYPES[type_key]['name']}")
                removed_count += 1
                logger.info(f"User {interaction.user.id} unsubscribed from {type_key}")
            except Exception as e:
                logger.error(f"Error removing {type_key} role from user {interaction.user.id}: {e}")
                errors.append(f"Failed to unsubscribe from {NOTIFICATION_TYPES[type_key]['name']}")

        # Update current subscriptions
        self.current_subscriptions = selected_types

        # Create result embed
        embed = discord.Embed(
            title="✅ Notification Preferences Updated",
            color=discord.Color.green()
        )

        if added_count > 0:
            embed.add_field(
                name=f"➕ Subscribed ({added_count})",
                value="\n".join([f"{NOTIFICATION_TYPES[t]['emoji']} {NOTIFICATION_TYPES[t]['name']}" for t in to_add]),
                inline=True
            )

        if removed_count > 0:
            embed.add_field(
                name=f"➖ Unsubscribed ({removed_count})",
                value="\n".join([f"{NOTIFICATION_TYPES[t]['emoji']} {NOTIFICATION_TYPES[t]['name']}" for t in to_remove]),
                inline=True
            )

        if not added_count and not removed_count:
            embed.description = "No changes made to your notification preferences."

        if errors:
            embed.add_field(
                name="⚠️ Errors",
                value="\n".join(errors),
                inline=False
            )

        # Show current subscriptions
        if selected_types:
            embed.add_field(
                name="📋 Current Subscriptions",
                value="\n".join([f"{NOTIFICATION_TYPES[t]['emoji']} {NOTIFICATION_TYPES[t]['name']}" for t in selected_types]),
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Current Subscriptions",
                value="None (you will not receive any notifications)",
                inline=False
            )

        # Update the view with new current subscriptions
        view = NotificationTypeView(self.cog, selected_types, interaction.user.id)
        await interaction.edit_original_response(embed=embed, view=view)


class NotificationTypeView(View):
    """View for managing multiple notification type subscriptions"""

    def __init__(self, cog: 'NotificationsCog', current_subscriptions: List[str], owner_id: int):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.cog = cog
        self.current_subscriptions = current_subscriptions
        self.owner_id = owner_id

        # Add the select menu
        self.add_item(NotificationTypeSelect(cog, current_subscriptions))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the command user to interact"""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ This notification menu belongs to someone else. Use `/notifications` to manage your own preferences!",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Subscribe to All", style=discord.ButtonStyle.primary, emoji="📢", row=1)
    async def subscribe_all(self, interaction: discord.Interaction, button: Button):
        """Subscribe to all notification types"""
        await interaction.response.defer()

        all_types = list(NOTIFICATION_TYPES.keys())
        to_add = set(all_types) - set(self.current_subscriptions)

        if not to_add:
            embed = discord.Embed(
                title="ℹ️ Already Subscribed",
                description="You're already subscribed to all notification types!",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        added_count = 0
        errors = []

        for type_key in to_add:
            try:
                role = await self.cog.get_or_create_notification_role(interaction.guild, type_key)
                await interaction.user.add_roles(role, reason="Subscribed to all notifications")
                added_count += 1
                logger.info(f"User {interaction.user.id} subscribed to {type_key} (subscribe all)")
            except Exception as e:
                logger.error(f"Error adding {type_key} role: {e}")
                errors.append(NOTIFICATION_TYPES[type_key]['name'])

        embed = discord.Embed(
            title="✅ Subscribed to All Notifications",
            description=f"Successfully subscribed to **{added_count}** notification type(s)!",
            color=discord.Color.green()
        )

        if errors:
            embed.add_field(
                name="⚠️ Failed to subscribe to:",
                value="\n".join(errors),
                inline=False
            )

        # Update current subscriptions and view
        self.current_subscriptions = all_types
        view = NotificationTypeView(self.cog, all_types, self.owner_id)
        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="Unsubscribe from All", style=discord.ButtonStyle.danger, emoji="🔕", row=1)
    async def unsubscribe_all(self, interaction: discord.Interaction, button: Button):
        """Unsubscribe from all notification types"""
        await interaction.response.defer()

        if not self.current_subscriptions:
            embed = discord.Embed(
                title="ℹ️ No Subscriptions",
                description="You're not subscribed to any notification types!",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        removed_count = 0
        errors = []

        for type_key in self.current_subscriptions:
            try:
                role = await self.cog.get_or_create_notification_role(interaction.guild, type_key)
                await interaction.user.remove_roles(role, reason="Unsubscribed from all notifications")
                removed_count += 1
                logger.info(f"User {interaction.user.id} unsubscribed from {type_key} (unsubscribe all)")
            except Exception as e:
                logger.error(f"Error removing {type_key} role: {e}")
                errors.append(NOTIFICATION_TYPES[type_key]['name'])

        embed = discord.Embed(
            title="✅ Unsubscribed from All Notifications",
            description=f"Successfully unsubscribed from **{removed_count}** notification type(s).",
            color=discord.Color.green()
        )

        embed.add_field(
            name="📭 Status",
            value="You will no longer receive any bot notifications.",
            inline=False
        )

        if errors:
            embed.add_field(
                name="⚠️ Failed to unsubscribe from:",
                value="\n".join(errors),
                inline=False
            )

        # Update current subscriptions and view
        self.current_subscriptions = []
        view = NotificationTypeView(self.cog, [], self.owner_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def on_timeout(self):
        """Handle view timeout"""
        for item in self.children:
            item.disabled = True


class NotificationsCog(commands.Cog):
    """Cog for managing multiple types of bot notifications and subscriptions"""

    def __init__(self, bot):
        self.bot = bot
        logger.info("NotificationsCog initialized with multi-type support")

    async def get_or_create_notification_role(self, guild: discord.Guild, notification_type: str) -> discord.Role:
        """Get or create a notification role for a specific type

        Args:
            guild: The Discord guild
            notification_type: Key from NOTIFICATION_TYPES dict

        Returns:
            The role for this notification type
        """
        if notification_type not in NOTIFICATION_TYPES:
            raise ValueError(f"Invalid notification type: {notification_type}")

        type_info = NOTIFICATION_TYPES[notification_type]
        role_name = type_info["role_name"]

        # Try to find role by name
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            logger.debug(f"Found existing {notification_type} role '{role.name}' in guild {guild.id}")
            return role

        # Create the role if it doesn't exist
        try:
            role = await guild.create_role(
                name=role_name,
                mentionable=True,
                reason=f"Auto-created for {type_info['name']} notifications",
                color=type_info["color"]
            )
            logger.info(f"Created new {notification_type} role '{role.name}' (ID: {role.id}) in guild {guild.id}")
            return role
        except discord.Forbidden:
            logger.error(f"Insufficient permissions to create {notification_type} role in guild {guild.id}")
            raise
        except Exception as e:
            logger.error(f"Error creating {notification_type} role in guild {guild.id}: {e}")
            raise

    async def get_user_subscriptions(self, user: discord.Member) -> List[str]:
        """Get list of notification types the user is subscribed to

        Args:
            user: Discord member to check

        Returns:
            List of notification type keys the user is subscribed to
        """
        subscriptions = []

        for type_key, type_info in NOTIFICATION_TYPES.items():
            role = discord.utils.get(user.guild.roles, name=type_info["role_name"])
            if role and role in user.roles:
                subscriptions.append(type_key)

        return subscriptions

    @app_commands.command(name="notifications", description="Manage your notification preferences for bot updates, events, and more")
    @command_meta(section="Utilities", name="Notifications")
    async def notifications(self, interaction: discord.Interaction):
        """Main command to manage notification subscriptions with multi-select interface"""
        try:
            # Get current subscriptions
            current_subscriptions = await self.get_user_subscriptions(interaction.user)

            # Create embed showing current status
            embed = discord.Embed(
                title="📢 Notification Preferences",
                description="Choose which types of notifications you want to receive using the dropdown menu below.",
                color=discord.Color.blue()
            )

            # Show available notification types
            types_text = ""
            for type_key, type_info in NOTIFICATION_TYPES.items():
                is_subscribed = type_key in current_subscriptions
                status = "✅" if is_subscribed else "⬜"
                types_text += f"{status} {type_info['emoji']} **{type_info['name']}**\n   _{type_info['description']}_\n"

            embed.add_field(
                name="📋 Available Notification Types",
                value=types_text,
                inline=False
            )

            # Show subscription count
            subscription_count = len(current_subscriptions)
            total_count = len(NOTIFICATION_TYPES)

            embed.add_field(
                name="📊 Current Status",
                value=f"You're subscribed to **{subscription_count}/{total_count}** notification types.",
                inline=False
            )

            embed.set_footer(text="Use the dropdown to select/deselect notification types • Changes are applied immediately")

            # Create view with dropdown and buttons
            view = NotificationTypeView(self, current_subscriptions, interaction.user.id)

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.info(f"User {interaction.user.id} opened notifications interface - {subscription_count}/{total_count} subscribed")

        except Exception as e:
            embed = discord.Embed(
                title="❌ An Error Occurred",
                description="Something went wrong while loading the notifications interface. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.error(f"Error in notifications command for user {interaction.user.id}: {e}", exc_info=True)


async def setup(bot):
    """Setup function for the notifications cog"""
    await bot.add_cog(NotificationsCog(bot))
    logger.info("NotificationsCog successfully loaded with multi-type support")
