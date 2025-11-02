import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List
import logging
from datetime import datetime
import database
from cogs_test.general_commands.dashboard import command_meta

# Set up logging
logger = logging.getLogger('planned_features')

# Status types with colors and emojis
STATUS_CONFIG = {
    'planned': {'emoji': '📋', 'color': discord.Color.blue(), 'label': 'Planned'},
    'in_progress': {'emoji': '🔄', 'color': discord.Color.orange(), 'label': 'In Progress'},
    'testing': {'emoji': '🧪', 'color': discord.Color.yellow(), 'label': 'Testing'},
    'completed': {'emoji': '✅', 'color': discord.Color.green(), 'label': 'Completed'},
    'cancelled': {'emoji': '❌', 'color': discord.Color.red(), 'label': 'Cancelled'},
    'on_hold': {'emoji': '⏸️', 'color': discord.Color.light_gray(), 'label': 'On Hold'}
}

# Category types with emojis
CATEGORY_CONFIG = {
    'Anime/Manga Features': '📺',
    'Gaming Features': '🎮',
    'Social Features': '👥',
    'Server Management': '⚙️',
    'Utilities': '🔧',
    'Performance Improvements': '⚡',
    'Bug Fixes': '🐛'
}

def get_status_badge(status: str) -> str:
    """Get formatted status badge with emoji"""
    config = STATUS_CONFIG.get(status, STATUS_CONFIG['planned'])
    return f"{config['emoji']} {config['label']}"

def get_category_badge(category: str) -> str:
    """Get formatted category badge with emoji"""
    emoji = CATEGORY_CONFIG.get(category, '🔧')
    return f"{emoji} {category}"

def get_status_color(status: str) -> discord.Color:
    """Get color for status"""
    config = STATUS_CONFIG.get(status, STATUS_CONFIG['planned'])
    return config['color']

class PlannedFeatures(commands.Cog):
    """Planned features management system"""

    def __init__(self, bot):
        self.bot = bot
        logger.info("PlannedFeatures cog initialized (using database)")
    
    async def get_planned_features(self, status: Optional[str] = None, category: Optional[str] = None) -> List[dict]:
        """Get all planned features, optionally filtered by status and/or category."""
        try:
            # Build dynamic query based on filters
            query = """SELECT id, name, description, added_date, added_by, uploaded_from_file,
                              last_edited, last_edited_by, status, category
                       FROM planned_features"""

            conditions = []
            params = []

            if status:
                conditions.append("status = ?")
                params.append(status)

            if category:
                conditions.append("category = ?")
                params.append(category)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY added_date DESC"

            rows = await database.execute_db_operation(
                "get planned features",
                query,
                tuple(params) if params else None,
                fetch_type='all'
            )

            if not rows:
                return []

            features = []
            for row in rows:
                features.append({
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'added_date': row[3],
                    'added_by': row[4],
                    'uploaded_from_file': row[5],
                    'last_edited': row[6],
                    'last_edited_by': row[7],
                    'status': row[8],
                    'category': row[9] if len(row) > 9 else 'Utilities'
                })

            return features
        except Exception as e:
            logger.error(f"Error getting features: {e}", exc_info=True)
            return []
    
    async def track_status_change(self, feature_id: int, old_status: Optional[str], new_status: str, changed_by: int, notes: Optional[str] = None):
        """Track status changes in history table"""
        try:
            await database.execute_db_operation(
                "track status change",
                """INSERT INTO feature_status_history
                   (feature_id, old_status, new_status, changed_by, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (feature_id, old_status, new_status, changed_by, notes)
            )
            logger.info(f"Tracked status change for feature {feature_id}: {old_status} -> {new_status}")
        except Exception as e:
            logger.error(f"Error tracking status change: {e}", exc_info=True)

    async def add_planned_feature(self, name: str, description: str, added_by: str, **kwargs) -> int:
        """Add a new planned feature. Returns the feature ID."""
        try:
            added_date = datetime.now().isoformat()
            uploaded_from_file = kwargs.get('uploaded_from_file')
            category = kwargs.get('category', 'Utilities')
            status = kwargs.get('status', 'planned')

            # Insert and get the auto-generated ID
            feature_id = await database.execute_db_operation(
                "insert planned feature",
                """INSERT INTO planned_features
                   (name, description, added_date, added_by, uploaded_from_file, status, category)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, description, added_date, added_by, uploaded_from_file, status, category),
                fetch_type='lastrowid'
            )

            if feature_id:
                logger.info(f"Added planned feature: {name} (ID: {feature_id}, Category: {category})")
                # Track initial status
                await self.track_status_change(feature_id, None, status, int(added_by))
                return feature_id
            return 0
        except Exception as e:
            logger.error(f"Error adding planned feature {name}: {e}", exc_info=True)
            return 0
    
    async def update_planned_feature(self, feature_id: int, changed_by: Optional[int] = None, **kwargs) -> bool:
        """Update a planned feature with provided fields."""
        try:
            # Get current feature to check for status changes
            old_feature = None
            if 'status' in kwargs:
                features = await self.get_planned_features()
                old_feature = next((f for f in features if f['id'] == feature_id), None)

            # Update last_edited timestamp if any changes are made
            if any(key in kwargs for key in ['name', 'description', 'status', 'category']):
                kwargs['last_edited'] = datetime.now().isoformat()

            # Build UPDATE query dynamically based on provided fields
            update_fields = []
            values = []
            for key, value in kwargs.items():
                update_fields.append(f"{key} = ?")
                values.append(value)

            if not update_fields:
                return True  # Nothing to update

            values.append(feature_id)  # For WHERE clause
            query = f"UPDATE planned_features SET {', '.join(update_fields)} WHERE id = ?"

            await database.execute_db_operation(
                f"update planned feature {feature_id}",
                query,
                tuple(values)
            )

            # Track status change if status was updated
            if 'status' in kwargs and old_feature and changed_by:
                old_status = old_feature.get('status')
                new_status = kwargs['status']
                if old_status != new_status:
                    await self.track_status_change(feature_id, old_status, new_status, changed_by)

            logger.info(f"Updated planned feature ID {feature_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating planned feature {feature_id}: {e}", exc_info=True)
            return False

    async def delete_planned_feature(self, feature_id: int) -> bool:
        """Delete a planned feature."""
        try:
            await database.execute_db_operation(
                f"delete planned feature {feature_id}",
                "DELETE FROM planned_features WHERE id = ?",
                (feature_id,)
            )

            logger.info(f"Deleted planned feature ID {feature_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting planned feature {feature_id}: {e}", exc_info=True)
            return False
    
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
    
    async def create_features_embed(self, page: int = 1, status_filter: Optional[str] = None, category_filter: Optional[str] = None) -> discord.Embed:
        """Create an embed displaying planned features with optional filters"""
        features = await self.get_planned_features(status=status_filter, category=category_filter)

        # Pagination settings
        features_per_page = 1
        total_pages = max(1, (len(features) + features_per_page - 1) // features_per_page)
        start_idx = (page - 1) * features_per_page
        end_idx = start_idx + features_per_page
        page_features = features[start_idx:end_idx]

        # Build title with filters
        title = "🚀 Planned Features"
        filters_text = []
        if status_filter:
            filters_text.append(f"Status: {get_status_badge(status_filter)}")
        if category_filter:
            filters_text.append(f"Category: {get_category_badge(category_filter)}")

        if filters_text:
            title += f" ({', '.join(filters_text)})"

        # Determine embed color based on status filter or use default
        embed_color = get_status_color(status_filter) if status_filter else discord.Color.blue()

        # Create embed
        embed = discord.Embed(
            title=title,
            description=f"Page {page}/{total_pages} • Total: {len(features)} features",
            color=embed_color,
            timestamp=datetime.now()
        )

        # Add features to embed
        if page_features:
            for i, feature in enumerate(page_features, start=start_idx + 1):
                name = feature.get('name', 'Unknown Feature')
                description = feature.get('description', 'No description available')
                added_date = feature.get('added_date', 'Unknown')
                status = feature.get('status', 'planned')
                category = feature.get('category', 'Utilities')

                # Discord embed field name limit is 256 characters
                # Reserve space for number prefix (e.g., "99. ")
                field_name = f"{i}. {name}"
                if len(field_name) > 256:
                    # Truncate name to fit: number + ". " + name + "..."
                    prefix = f"{i}. "
                    max_name_length = 256 - len(prefix) - 3  # 3 for "..."
                    field_name = prefix + name[:max_name_length] + "..."

                # Add status and category badges
                metadata = f"\n{get_status_badge(status)} | {get_category_badge(category)}"

                # Format the date part
                date_text = f"\n*Added: {added_date[:10] if len(added_date) >= 10 else added_date}*"

                # Discord embed field value limit is 1024 characters
                # Reserve space for metadata and date text
                max_desc_length = 1024 - len(metadata) - len(date_text)

                # Truncate description if needed
                if len(description) > max_desc_length:
                    description = description[:max_desc_length - 3] + "..."

                embed.add_field(
                    name=field_name,
                    value=f"{description}{metadata}{date_text}",
                    inline=False
                )
        else:
            embed.add_field(
                name="No Features",
                value="No features match the selected filters.",
                inline=False
            )

        # Add footer
        embed.set_footer(text=f"Use /planned to view all features")

        return embed

    class FeatureView(discord.ui.View):
        """View for navigating between feature pages"""

        def __init__(self, cog, current_page: int = 1, status_filter: Optional[str] = None, category_filter: Optional[str] = None):
            super().__init__(timeout=300)
            self.cog = cog
            self.current_page = current_page
            self.status_filter = status_filter
            self.category_filter = category_filter

        async def update_buttons(self):
            """Update button states based on current page"""
            features = await self.cog.get_planned_features(status=self.status_filter, category=self.category_filter)
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
                embed = await self.cog.create_features_embed(self.current_page, self.status_filter, self.category_filter)
                await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.primary, disabled=True)
        async def page_info(self, interaction: discord.Interaction, button: discord.ui.Button):
            # This button is just for display
            await interaction.response.defer()

        @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            features = await self.cog.get_planned_features(status=self.status_filter, category=self.category_filter)
            features_per_page = 1
            total_pages = max(1, (len(features) + features_per_page - 1) // features_per_page)

            if self.current_page < total_pages:
                self.current_page += 1
                await self.update_buttons()
                embed = await self.cog.create_features_embed(self.current_page, self.status_filter, self.category_filter)
                await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="🔍 Filter", style=discord.ButtonStyle.blurple, row=1)
        async def filter_features(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Show filter options"""
            view = PlannedFeatures.FilterView(self.cog, self.current_page, self.status_filter, self.category_filter)
            await interaction.response.send_message(
                "🔍 **Filter Features**\n\nSelect filters below:",
                view=view,
                ephemeral=True
            )
        
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
            
            features = await self.cog.get_planned_features('planned')
            if not features:
                await interaction.response.send_message(
                    "❌ **No Features to Edit**\n\nThere are no planned features to edit.",
                    ephemeral=True
                )
                return
            
            # Show edit feature selection
            view = PlannedFeatures.EditFeatureView(self.cog, self.current_page)
            select = await view.create_and_add_select_menu()
            view.add_item(select)
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
            
            features = await self.cog.get_planned_features('planned')
            if not features:
                await interaction.response.send_message(
                    "❌ **No Features to Remove**\n\nThere are no planned features to remove.",
                    ephemeral=True
                )
                return
            
            # Show remove feature selection
            view = PlannedFeatures.RemoveFeatureView(self.cog, self.current_page)
            select = await view.create_and_add_select_menu()
            view.add_item(select)
            await interaction.response.send_message(
                "🗑️ **Remove Planned Feature**\n\nSelect a feature to remove:",
                view=view,
                ephemeral=True
            )

    class FilterView(discord.ui.View):
        """View for filtering features by status and category"""

        def __init__(self, cog, current_page: int, current_status_filter: Optional[str], current_category_filter: Optional[str]):
            super().__init__(timeout=300)
            self.cog = cog
            self.current_page = current_page
            self.selected_status = current_status_filter
            self.selected_category = current_category_filter

            # Add status select menu
            status_options = [discord.SelectOption(label="All Statuses", value="all", default=(current_status_filter is None))]
            for status_key, config in STATUS_CONFIG.items():
                status_options.append(
                    discord.SelectOption(
                        label=config['label'],
                        value=status_key,
                        emoji=config['emoji'],
                        default=(current_status_filter == status_key)
                    )
                )

            self.status_select = discord.ui.Select(
                placeholder="Filter by Status...",
                options=status_options,
                row=0
            )
            self.status_select.callback = self.status_selected
            self.add_item(self.status_select)

            # Add category select menu
            category_options = [discord.SelectOption(label="All Categories", value="all", default=(current_category_filter is None))]
            for category, emoji in CATEGORY_CONFIG.items():
                category_options.append(
                    discord.SelectOption(
                        label=category,
                        value=category,
                        emoji=emoji,
                        default=(current_category_filter == category)
                    )
                )

            self.category_select = discord.ui.Select(
                placeholder="Filter by Category...",
                options=category_options,
                row=1
            )
            self.category_select.callback = self.category_selected
            self.add_item(self.category_select)

        async def status_selected(self, interaction: discord.Interaction):
            """Handle status filter selection"""
            selected = interaction.data['values'][0]
            self.selected_status = None if selected == "all" else selected
            await interaction.response.send_message(
                f"✅ Status filter updated to: **{get_status_badge(self.selected_status) if self.selected_status else 'All Statuses'}**",
                ephemeral=True
            )

        async def category_selected(self, interaction: discord.Interaction):
            """Handle category filter selection"""
            selected = interaction.data['values'][0]
            self.selected_category = None if selected == "all" else selected
            await interaction.response.send_message(
                f"✅ Category filter updated to: **{get_category_badge(self.selected_category) if self.selected_category else 'All Categories'}**",
                ephemeral=True
            )

        @discord.ui.button(label="Apply Filters", style=discord.ButtonStyle.green, row=2)
        async def apply_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Apply the selected filters"""
            # Create new embed with filters
            embed = await self.cog.create_features_embed(1, self.selected_status, self.selected_category)
            view = PlannedFeatures.FeatureView(self.cog, 1, self.selected_status, self.selected_category)
            await view.update_buttons()

            # Update the original message (need to get it from interaction)
            await interaction.response.send_message(
                "✅ Filters applied! Check the updated feature list.",
                ephemeral=True
            )

        @discord.ui.button(label="Clear Filters", style=discord.ButtonStyle.secondary, row=2)
        async def clear_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Clear all filters"""
            embed = await self.cog.create_features_embed(1, None, None)
            view = PlannedFeatures.FeatureView(self.cog, 1, None, None)
            await view.update_buttons()

            await interaction.response.send_message(
                "✅ All filters cleared!",
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

        category = discord.ui.TextInput(
            label="Category",
            placeholder="Utilities | Anime/Manga | Gaming | Social | Server | Performance | Bug Fixes",
            default="Utilities",
            max_length=50,
            required=False
        )

        status = discord.ui.TextInput(
            label="Status",
            placeholder="planned | in_progress | testing | completed | cancelled | on_hold",
            default="planned",
            max_length=20,
            required=False
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

            # Validate and normalize category
            category_input = self.category.value.strip() if self.category.value else "Utilities"
            # Map common short forms to full category names
            category_map = {
                'utilities': 'Utilities',
                'anime': 'Anime/Manga Features',
                'manga': 'Anime/Manga Features',
                'gaming': 'Gaming Features',
                'social': 'Social Features',
                'server': 'Server Management',
                'performance': 'Performance Improvements',
                'bug': 'Bug Fixes'
            }
            category = category_map.get(category_input.lower(), category_input)

            # Validate category
            if category not in CATEGORY_CONFIG:
                category = 'Utilities'  # Default to Utilities if invalid

            # Validate and normalize status
            status_input = self.status.value.strip() if self.status.value else "planned"
            status = status_input.lower()

            # Validate status
            if status not in STATUS_CONFIG:
                status = 'planned'  # Default to planned if invalid

            # Add to database
            feature_id = await self.cog.add_planned_feature(
                name=self.name.value.strip(),
                description=self.description.value.strip(),
                added_by=str(interaction.user.id),
                added_date=datetime.now().isoformat(),
                category=category,
                status=status
            )
            
            if feature_id:
                # Create success embed
                embed = discord.Embed(
                    title="✅ Planned Feature Added Successfully",
                    description="Added to **Planned Features**",
                    color=get_status_color(status),
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
                    name="Status",
                    value=get_status_badge(status),
                    inline=True
                )

                embed.add_field(
                    name="Category",
                    value=get_category_badge(category),
                    inline=True
                )

                embed.add_field(
                    name="Added By",
                    value=interaction.user.mention,
                    inline=True
                )

                features = await self.cog.get_planned_features()
                embed.set_footer(text=f"Total features: {len(features)}")
                
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
            # Note: Select menu will be added after view creation due to async requirement
            
        async def create_and_add_select_menu(self):
            """Create select menu with features"""
            features = await self.cog.get_planned_features('planned')
            
            # Limit to 25 options (Discord limit)
            features = features[:25]
            
            options = []
            for i, feature in enumerate(features, 1):
                # Safely truncate label to 100 chars (Discord limit)
                name = feature.get('name', 'Unknown')
                label = f"{i}. {name}"
                if len(label) > 100:
                    label = f"{i}. {name[:97 - len(str(i)) - 2]}..."
                
                # Safely truncate description to 100 chars (Discord limit)
                desc = feature.get('description', '')
                if len(desc) > 100:
                    desc = desc[:97] + "..."
                
                options.append(
                    discord.SelectOption(
                        label=label,
                        description=desc,
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
            features = await self.cog.get_planned_features('planned')
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

            self.category = discord.ui.TextInput(
                label="Category",
                placeholder="Utilities | Anime/Manga | Gaming | Social | Server | Performance | Bug Fixes",
                default=feature.get('category', 'Utilities'),
                max_length=50,
                required=False
            )
            self.add_item(self.category)

            self.status = discord.ui.TextInput(
                label="Status",
                placeholder="planned | in_progress | testing | completed | cancelled | on_hold",
                default=feature.get('status', 'planned'),
                max_length=20,
                required=False
            )
            self.add_item(self.status)

        async def on_submit(self, interaction: discord.Interaction):
            # Validate and normalize category
            category_input = self.category.value.strip() if self.category.value else "Utilities"
            category_map = {
                'utilities': 'Utilities',
                'anime': 'Anime/Manga Features',
                'manga': 'Anime/Manga Features',
                'gaming': 'Gaming Features',
                'social': 'Social Features',
                'server': 'Server Management',
                'performance': 'Performance Improvements',
                'bug': 'Bug Fixes'
            }
            category = category_map.get(category_input.lower(), category_input)
            if category not in CATEGORY_CONFIG:
                category = 'Utilities'

            # Validate and normalize status
            status_input = self.status.value.strip() if self.status.value else "planned"
            status = status_input.lower()
            if status not in STATUS_CONFIG:
                status = 'planned'

            # Update in database
            success = await self.cog.update_planned_feature(
                feature_id=self.feature_id,
                changed_by=interaction.user.id,
                name=self.name.value.strip(),
                description=self.description.value.strip(),
                category=category,
                status=status,
                last_edited=datetime.now().isoformat(),
                last_edited_by=str(interaction.user.id)
            )
            
            if success:
                # Create success embed
                embed = discord.Embed(
                    title="✅ Planned Feature Updated Successfully",
                    color=get_status_color(status),
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
                    name="Status",
                    value=get_status_badge(status),
                    inline=True
                )

                embed.add_field(
                    name="Category",
                    value=get_category_badge(category),
                    inline=True
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
            # Note: Select menu will be added after view creation due to async requirement
            
        async def create_and_add_select_menu(self):
            """Create select menu with features"""
            features = await self.cog.get_planned_features('planned')
            
            # Limit to 25 options (Discord limit)
            features = features[:25]
            
            options = []
            for i, feature in enumerate(features, 1):
                # Safely truncate label to 100 chars (Discord limit)
                name = feature.get('name', 'Unknown')
                label = f"{i}. {name}"
                if len(label) > 100:
                    label = f"{i}. {name[:97 - len(str(i)) - 2]}..."
                
                # Safely truncate description to 100 chars (Discord limit)
                desc = feature.get('description', '')
                if len(desc) > 100:
                    desc = desc[:97] + "..."
                
                options.append(
                    discord.SelectOption(
                        label=label,
                        description=desc,
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
            features = await self.cog.get_planned_features('planned')
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
            success = await self.cog.delete_planned_feature(self.feature_id)
            
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
                
                features = await self.cog.get_planned_features('planned')
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
    @command_meta(section="Utilities", name="Planned Features")
    async def planned(self, interaction: discord.Interaction):
        """Display planned features"""
        try:
            # Restrict viewing planned features to bot moderators only
            try:
                from database import is_user_bot_moderator
                if not await is_user_bot_moderator(interaction.user):
                    await interaction.response.send_message(
                        "❌ **Access Denied**\n\nOnly bot moderators can view planned features.",
                        ephemeral=True
                    )
                    return
            except Exception:
                # If the bot-moderator check fails for any reason, deny access conservatively
                await interaction.response.send_message(
                    "❌ **Access Denied**\n\nOnly bot moderators can view planned features.",
                    ephemeral=True
                )
                return
            # Defer response first to prevent timeout
            await interaction.response.defer()

            # Get all features (no filter by default, show everything)
            features = await self.get_planned_features()

            if not features:
                await interaction.followup.send(
                    "📝 **No Features**\n\nThere are currently no features in the system.",
                    ephemeral=True
                )
                return

            # Create and send embed with view (no filters applied initially)
            embed = await self.create_features_embed(page=1, status_filter=None, category_filter=None)
            view = self.FeatureView(self, current_page=1, status_filter=None, category_filter=None)
            await view.update_buttons()

            await interaction.followup.send(embed=embed, view=view)
            logger.info(f"User {interaction.user.id} ({interaction.user.display_name}) viewed planned features")
            
        except Exception as e:
            logger.error(f"Error displaying planned features: {e}")
            # Check if response was already deferred
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ **Error**\n\nFailed to load planned features. Please try again later.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ **Error**\n\nFailed to load planned features. Please try again later.",
                    ephemeral=True
                )


async def setup(bot):
    await bot.add_cog(PlannedFeatures(bot))
    logger.info("PlannedFeatures cog loaded successfully")
