import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List
import logging
from datetime import datetime
from database import (
    get_planned_features,
    add_planned_feature,
    update_planned_feature,
    delete_planned_feature
)

# Set up logging
logger = logging.getLogger('planned_features')

class PlannedFeatures(commands.Cog):
    """Planned features management system"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def has_mod_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if user has moderator permissions"""
        try:
            from database import is_user_moderator
            
            if not interaction.guild:
                return False
                
            # Check if user is guild owner
            if interaction.user.id == interaction.guild.owner_id:
                return True
            
            # Check using the database mod role system
            return await is_user_moderator(interaction.user, interaction.guild.id)
                
        except Exception as e:
            logger.error(f"Error checking mod permissions: {e}")
            return False
    
    async def create_features_embed(self, page: int = 1) -> discord.Embed:
        """Create an embed displaying planned features"""
        features = await get_planned_features('planned')
        
        # Pagination settings
        features_per_page = 1
        total_pages = max(1, (len(features) + features_per_page - 1) // features_per_page)
        start_idx = (page - 1) * features_per_page
        end_idx = start_idx + features_per_page
        page_features = features[start_idx:end_idx]
        
        # Create embed
        embed = discord.Embed(
            title="🚀 Planned Features",
            description=f"Page {page}/{total_pages} • Total: {len(features)} features",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Add features to embed
        if page_features:
            for i, feature in enumerate(page_features, start=start_idx + 1):
                name = feature.get('name', 'Unknown Feature')
                description = feature.get('description', 'No description available')
                added_date = feature.get('added_date', 'Unknown')
                
                # Discord embed field name limit is 256 characters
                # Reserve space for number prefix (e.g., "99. ")
                field_name = f"{i}. {name}"
                if len(field_name) > 256:
                    # Truncate name to fit: number + ". " + name + "..."
                    prefix = f"{i}. "
                    max_name_length = 256 - len(prefix) - 3  # 3 for "..."
                    field_name = prefix + name[:max_name_length] + "..."
                
                # Format the date part
                date_text = f"\n*Added: {added_date[:10] if len(added_date) >= 10 else added_date}*"
                
                # Discord embed field value limit is 1024 characters
                # Reserve space for date text
                max_desc_length = 1024 - len(date_text)
                
                # Truncate description if needed
                if len(description) > max_desc_length:
                    description = description[:max_desc_length - 3] + "..."
                
                embed.add_field(
                    name=field_name,
                    value=f"{description}{date_text}",
                    inline=False
                )
        else:
            embed.add_field(
                name="No Features",
                value="No planned features have been added yet.",
                inline=False
            )
        
        # Add footer
        embed.set_footer(text=f"Use /planned to view all features")
        
        return embed

    class FeatureView(discord.ui.View):
        """View for navigating between feature pages"""
        
        def __init__(self, cog, current_page: int = 1):
            super().__init__(timeout=300)
            self.cog = cog
            self.current_page = current_page
        
        async def update_buttons(self):
            """Update button states based on current page"""
            features = await get_planned_features('planned')
            features_per_page = 1
            total_pages = max(1, (len(features) + features_per_page - 1) // features_per_page)
            
            # Update button states
            self.previous_page.disabled = self.current_page <= 1
            self.next_page.disabled = self.current_page >= total_pages
            
            # Update button labels
            self.page_info.label = f"Page {self.current_page}/{total_pages}"
        
        @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
        async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.current_page > 1:
                self.current_page -= 1
                await self.update_buttons()
                embed = await self.cog.create_features_embed(self.current_page)
                await interaction.response.edit_message(embed=embed, view=self)
        
        @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.primary, disabled=True)
        async def page_info(self, interaction: discord.Interaction, button: discord.ui.Button):
            # This button is just for display
            await interaction.response.defer()
        
        @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            features = await get_planned_features('planned')
            features_per_page = 1
            total_pages = max(1, (len(features) + features_per_page - 1) // features_per_page)
            
            if self.current_page < total_pages:
                self.current_page += 1
                await self.update_buttons()
                embed = await self.cog.create_features_embed(self.current_page)
                await interaction.response.edit_message(embed=embed, view=self)
        
        @discord.ui.button(label="➕ Add Feature", style=discord.ButtonStyle.green, row=1)
        async def add_feature(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Check permissions
            if not await self.cog.has_mod_permissions(interaction):
                await interaction.response.send_message(
                    "❌ **Permission Denied**\n\nYou need moderator permissions to add features.",
                    ephemeral=True
                )
                return
            
            # Show add feature modal
            modal = PlannedFeatures.AddFeatureModal(self.cog)
            await interaction.response.send_modal(modal)
        
        @discord.ui.button(label="✏️ Edit Feature", style=discord.ButtonStyle.blurple, row=1)
        async def edit_feature(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Check permissions
            if not await self.cog.has_mod_permissions(interaction):
                await interaction.response.send_message(
                    "❌ **Permission Denied**\n\nYou need moderator permissions to edit features.",
                    ephemeral=True
                )
                return
            
            features = await get_planned_features('planned')
            if not features:
                await interaction.response.send_message(
                    "❌ **No Features to Edit**\n\nThere are no planned features to edit.",
                    ephemeral=True
                )
                return
            
            # Show edit feature selection
            view = PlannedFeatures.EditFeatureView(self.cog, self.current_page)
            await interaction.response.send_message(
                "✏️ **Edit Planned Feature**\n\nSelect a feature to edit:",
                view=view,
                ephemeral=True
            )

        @discord.ui.button(label="🗑️ Remove Feature", style=discord.ButtonStyle.red, row=1)
        async def remove_feature(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Check permissions
            if not await self.cog.has_mod_permissions(interaction):
                await interaction.response.send_message(
                    "❌ **Permission Denied**\n\nYou need moderator permissions to remove features.",
                    ephemeral=True
                )
                return
            
            features = await get_planned_features('planned')
            if not features:
                await interaction.response.send_message(
                    "❌ **No Features to Remove**\n\nThere are no planned features to remove.",
                    ephemeral=True
                )
                return
            
            # Show remove feature selection
            view = PlannedFeatures.RemoveFeatureView(self.cog, self.current_page)
            await interaction.response.send_message(
                "🗑️ **Remove Planned Feature**\n\nSelect a feature to remove:",
                view=view,
                ephemeral=True
            )

    class AddFeatureModal(discord.ui.Modal):
        """Modal for adding a new planned feature"""
        
        def __init__(self, cog):
            super().__init__(title="Add Planned Feature")
            self.cog = cog
        
        name = discord.ui.TextInput(
            label="Feature Name",
            placeholder="Enter the name of the planned feature...",
            max_length=100,
            required=True
        )
        
        description = discord.ui.TextInput(
            label="Feature Description",
            placeholder="Describe what this planned feature will do...",
            style=discord.TextStyle.paragraph,
            required=True
        )
        
        async def on_submit(self, interaction: discord.Interaction):
            # Validate inputs
            if len(self.name.value.strip()) == 0:
                await interaction.response.send_message(
                    "❌ **Invalid Name**\n\nFeature name cannot be empty.",
                    ephemeral=True
                )
                return
            
            if len(self.description.value.strip()) == 0:
                await interaction.response.send_message(
                    "❌ **Invalid Description**\n\nFeature description cannot be empty.",
                    ephemeral=True
                )
                return
            
            # Add to database
            feature_id = await add_planned_feature(
                name=self.name.value.strip(),
                description=self.description.value.strip(),
                added_by=str(interaction.user.id),
                added_date=datetime.now().isoformat(),
                status='planned'
            )
            
            if feature_id:
                # Create success embed
                embed = discord.Embed(
                    title="✅ Planned Feature Added Successfully",
                    description="Added to **Planned Features**",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(
                    name="Feature Name",
                    value=self.name.value,
                    inline=False
                )
                
                embed.add_field(
                    name="Description",
                    value=self.description.value,
                    inline=False
                )
                
                embed.add_field(
                    name="Added By",
                    value=interaction.user.mention,
                    inline=True
                )
                
                features = await get_planned_features('planned')
                embed.set_footer(text=f"Total planned features: {len(features)}")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info(f"User {interaction.user.id} ({interaction.user.display_name}) added feature: {self.name.value}")
            else:
                await interaction.response.send_message(
                    "❌ **Error Adding Feature**\n\nFailed to save the feature to the database. Please try again.",
                    ephemeral=True
                )
    
    class EditFeatureView(discord.ui.View):
        """View for selecting a feature to edit"""
        
        def __init__(self, cog, current_page: int = 1):
            super().__init__(timeout=300)
            self.cog = cog
            self.current_page = current_page
            
        async def create_select_menu(self) -> discord.ui.Select:
            """Create select menu with features"""
            features = await get_planned_features('planned')
            
            # Limit to 25 options (Discord limit)
            features = features[:25]
            
            options = []
            for i, feature in enumerate(features, 1):
                options.append(
                    discord.SelectOption(
                        label=f"{i}. {feature.get('name', 'Unknown')[:90]}",
                        description=feature.get('description', '')[:100],
                        value=str(feature.get('id'))
                    )
                )
            
            if not options:
                options.append(
                    discord.SelectOption(
                        label="No features available",
                        value="none"
                    )
                )
            
            select = discord.ui.Select(
                placeholder="Select a feature to edit...",
                min_values=1,
                max_values=1,
                options=options
            )
            select.callback = self.feature_selected
            return select
        
        async def feature_selected(self, interaction: discord.Interaction):
            """Handle feature selection"""
            feature_id = int(interaction.data['values'][0])
            
            # Get feature details
            features = await get_planned_features('planned')
            feature = next((f for f in features if f.get('id') == feature_id), None)
            
            if not feature:
                await interaction.response.send_message(
                    "❌ **Feature Not Found**\n\nThe selected feature could not be found.",
                    ephemeral=True
                )
                return
            
            # Show edit modal
            modal = PlannedFeatures.EditFeatureModal(self.cog, feature)
            await interaction.response.send_modal(modal)
    
    class EditFeatureModal(discord.ui.Modal):
        """Modal for editing an existing planned feature"""
        
        def __init__(self, cog, feature: dict):
            super().__init__(title="Edit Planned Feature")
            self.cog = cog
            self.feature_id = feature.get('id')
            
            # Pre-fill with existing values
            self.name = discord.ui.TextInput(
                label="Feature Name",
                placeholder="Enter the name of the planned feature...",
                default=feature.get('name', ''),
                max_length=100,
                required=True
            )
            self.add_item(self.name)
            
            self.description = discord.ui.TextInput(
                label="Feature Description",
                placeholder="Describe what this planned feature will do...",
                style=discord.TextStyle.paragraph,
                default=feature.get('description', ''),
                required=True
            )
            self.add_item(self.description)
        
        async def on_submit(self, interaction: discord.Interaction):
            # Update in database
            success = await update_planned_feature(
                feature_id=self.feature_id,
                name=self.name.value.strip(),
                description=self.description.value.strip(),
                last_edited=datetime.now().isoformat(),
                last_edited_by=str(interaction.user.id)
            )
            
            if success:
                # Create success embed
                embed = discord.Embed(
                    title="✅ Planned Feature Updated Successfully",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(
                    name="Feature Name",
                    value=self.name.value,
                    inline=False
                )
                
                embed.add_field(
                    name="Description",
                    value=self.description.value,
                    inline=False
                )
                
                embed.add_field(
                    name="Edited By",
                    value=interaction.user.mention,
                    inline=True
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info(f"User {interaction.user.id} ({interaction.user.display_name}) edited feature ID {self.feature_id}")
            else:
                await interaction.response.send_message(
                    "❌ **Error Updating Feature**\n\nFailed to update the feature in the database. Please try again.",
                    ephemeral=True
                )
    
    class RemoveFeatureView(discord.ui.View):
        """View for selecting a feature to remove"""
        
        def __init__(self, cog, current_page: int = 1):
            super().__init__(timeout=300)
            self.cog = cog
            self.current_page = current_page
            
        async def create_select_menu(self) -> discord.ui.Select:
            """Create select menu with features"""
            features = await get_planned_features('planned')
            
            # Limit to 25 options (Discord limit)
            features = features[:25]
            
            options = []
            for i, feature in enumerate(features, 1):
                options.append(
                    discord.SelectOption(
                        label=f"{i}. {feature.get('name', 'Unknown')[:90]}",
                        description=feature.get('description', '')[:100],
                        value=str(feature.get('id'))
                    )
                )
            
            if not options:
                options.append(
                    discord.SelectOption(
                        label="No features available",
                        value="none"
                    )
                )
            
            select = discord.ui.Select(
                placeholder="Select a feature to remove...",
                min_values=1,
                max_values=1,
                options=options
            )
            select.callback = self.feature_selected
            return select
        
        async def feature_selected(self, interaction: discord.Interaction):
            """Handle feature selection"""
            feature_id = int(interaction.data['values'][0])
            
            # Get feature details for confirmation
            features = await get_planned_features('planned')
            feature = next((f for f in features if f.get('id') == feature_id), None)
            
            if not feature:
                await interaction.response.send_message(
                    "❌ **Feature Not Found**\n\nThe selected feature could not be found.",
                    ephemeral=True
                )
                return
            
            # Show confirmation
            view = PlannedFeatures.ConfirmRemoveView(self.cog, feature_id, feature.get('name', 'Unknown'))
            
            embed = discord.Embed(
                title="⚠️ Confirm Feature Removal",
                description=f"Are you sure you want to remove this feature?",
                color=discord.Color.orange()
            )
            
            embed.add_field(
                name="Feature Name",
                value=feature.get('name', 'Unknown'),
                inline=False
            )
            
            embed.add_field(
                name="Description",
                value=feature.get('description', 'No description')[:200],
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    class ConfirmRemoveView(discord.ui.View):
        """Confirmation view for removing a feature"""
        
        def __init__(self, cog, feature_id: int, feature_name: str):
            super().__init__(timeout=60)
            self.cog = cog
            self.feature_id = feature_id
            self.feature_name = feature_name
        
        @discord.ui.button(label="✅ Confirm Removal", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Remove from database
            success = await delete_planned_feature(self.feature_id)
            
            if success:
                embed = discord.Embed(
                    title="✅ Feature Removed Successfully",
                    description=f"Removed: **{self.feature_name}**",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(
                    name="Removed By",
                    value=interaction.user.mention,
                    inline=True
                )
                
                features = await get_planned_features('planned')
                embed.set_footer(text=f"Total planned features: {len(features)}")
                
                await interaction.response.edit_message(embed=embed, view=None)
                logger.info(f"User {interaction.user.id} ({interaction.user.display_name}) removed feature ID {self.feature_id}")
            else:
                await interaction.response.send_message(
                    "❌ **Error Removing Feature**\n\nFailed to remove the feature from the database. Please try again.",
                    ephemeral=True
                )
        
        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.edit_message(
                content="Removal cancelled.",
                embed=None,
                view=None
            )

    @app_commands.command(name="planned", description="View planned bot features")
    async def planned(self, interaction: discord.Interaction):
        """Display planned features"""
        try:
            features = await get_planned_features('planned')
            
            if not features:
                await interaction.response.send_message(
                    "📝 **No Planned Features**\n\nThere are currently no planned features.",
                    ephemeral=True
                )
                return
            
            # Create and send embed with view
            embed = await self.create_features_embed(page=1)
            view = self.FeatureView(self, current_page=1)
            await view.update_buttons()
            
            await interaction.response.send_message(embed=embed, view=view)
            logger.info(f"User {interaction.user.id} ({interaction.user.display_name}) viewed planned features")
            
        except Exception as e:
            logger.error(f"Error displaying planned features: {e}")
            await interaction.response.send_message(
                "❌ **Error**\n\nFailed to load planned features. Please try again later.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(PlannedFeatures(bot))
    logger.info("PlannedFeatures cog loaded successfully")
