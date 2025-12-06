import discord
from discord.ext import commands
from typing import Optional, List
import logging
from datetime import datetime
import database
from database import is_user_bot_moderator

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
        """
        Unified permission check: DB-only bot moderators.
        Returns True only if the user is present in the is_user_bot_moderator table.
        """
        try:
            # Use the top-level import
            return await is_user_bot_moderator(interaction.user)
        except Exception as e:
            logger.error(f"Error checking mod permissions: {e}", exc_info=True)
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
                metadata = f"\n{get_status_badge(status)} • {get_category_badge(category)}"

                # Prepare field value with a short description
                field_value = f"{description[:1000]}\n\n**Added:** {added_date}"

                embed.add_field(name=field_name, value=field_value + metadata, inline=False)

        # Add footer
        embed.set_footer(text=f"Use !planned to view all features")

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
            # Silent permission check
            if not await is_user_bot_moderator(interaction.user):
                return
            view = PlannedFeatures.FilterView(self.cog, self.current_page, self.status_filter, self.category_filter)
            await interaction.response.send_message(
                "🔍 **Filter Features**\n\nSelect filters below:",
                view=view,
                ephemeral=True
            )
        
        @discord.ui.button(label="➕ Add Feature", style=discord.ButtonStyle.green, row=1)
        async def add_feature(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Silent permission check -> do nothing if user not in DB
            if not await is_user_bot_moderator(interaction.user):
                return
            
            # Show add feature modal
            modal = PlannedFeatures.AddFeatureModal(self.cog)
            await interaction.response.send_modal(modal)
        
        @discord.ui.button(label="✏️ Edit Feature", style=discord.ButtonStyle.blurple, row=1)
        async def edit_feature(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Silent permission check
            if not await is_user_bot_moderator(interaction.user):
                return
            
            features = await self.cog.get_planned_features('planned')
            if not features:
                # No need to notify non-mods; but since the user is a mod (we passed above), we give ephemeral feedback
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
            # Silent permission check
            if not await is_user_bot_moderator(interaction.user):
                return
            
            features = await self.cog.get_planned_features('planned')
            if not features:
                await interaction.response.send_message(
                    "❌ **No Features to Remove**\n\nThere are no planned features to remove.",
                    ephemeral=True
                )
                return
            
            # Show remove selection
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
        def __init__(self, cog, current_page: int = 1, status_filter: Optional[str] = None, category_filter: Optional[str] = None):
            super().__init__(timeout=300)
            self.cog = cog
            self.current_page = current_page
            self.status_filter = status_filter
            self.category_filter = category_filter

            # Build selects now
            status_options = [discord.SelectOption(label=v['label'], value=k) for k,v in STATUS_CONFIG.items()]
            category_options = [discord.SelectOption(label=k, value=k) for k in CATEGORY_CONFIG.keys()]

            self.status_select = discord.ui.Select(placeholder="Status", min_values=1, max_values=1, options=status_options)
            self.category_select = discord.ui.Select(placeholder="Category", min_values=1, max_values=1, options=category_options)

            self.status_select.callback = self.status_selected
            self.category_select.callback = self.category_selected

            self.add_item(self.status_select)
            self.add_item(self.category_select)

        async def status_selected(self, interaction: discord.Interaction):
            # Silent permission check (only mods can interact)
            if not await is_user_bot_moderator(interaction.user):
                return
            selected = interaction.data.get('values', [None])[0]
            self.status_filter = selected
            embed = await self.cog.create_features_embed(self.current_page, status_filter=self.status_filter, category_filter=self.category_filter)
            view = PlannedFeatures.FeatureView(self.cog, current_page=self.current_page, status_filter=self.status_filter, category_filter=self.category_filter)
            await view.update_buttons()
            await interaction.response.edit_message(embed=embed, view=view)

        async def category_selected(self, interaction: discord.Interaction):
            # Silent permission check
            if not await is_user_bot_moderator(interaction.user):
                return
            selected = interaction.data.get('values', [None])[0]
            self.category_filter = selected
            embed = await self.cog.create_features_embed(self.current_page, status_filter=self.status_filter, category_filter=self.category_filter)
            view = PlannedFeatures.FeatureView(self.cog, current_page=self.current_page, status_filter=self.status_filter, category_filter=self.category_filter)
            await view.update_buttons()
            await interaction.response.edit_message(embed=embed, view=view)

    class AddFeatureModal(discord.ui.Modal):
        """Modal for adding a new planned feature"""

        def __init__(self, cog):
            super().__init__(title="Add Planned Feature")
            self.cog = cog

            self.name = discord.ui.TextInput(
                label="Feature Name",
                placeholder="Enter the name of the planned feature...",
                max_length=100,
                required=True
            )
            self.add_item(self.name)

            self.description = discord.ui.TextInput(
                label="Feature Description",
                placeholder="Describe what this planned feature will do...",
                style=discord.TextStyle.paragraph,
                required=True
            )
            self.add_item(self.description)

            self.category = discord.ui.TextInput(
                label="Category",
                placeholder="Utilities | Anime/Manga | Gaming | Social | Server | Performance | Bug Fixes",
                max_length=50,
                required=False
            )
            self.add_item(self.category)

            self.status = discord.ui.TextInput(
                label="Status",
                placeholder="planned | in_progress | testing | completed | cancelled | on_hold",
                max_length=20,
                required=False
            )
            self.add_item(self.status)

        async def on_submit(self, interaction: discord.Interaction):
            # Silent permission check before processing modal submission
            if not await is_user_bot_moderator(interaction.user):
                return

            # Validate category
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
                    label = f"{i}. {name[:97 - len(str(i)) - 2]}."
                
                # Safely truncate description to 100 chars (Discord limit)
                desc = feature.get('description', '')
                if len(desc) > 100:
                    desc = desc[:97] + "."
                
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
                placeholder="Select a feature to edit.",
                min_values=1,
                max_values=1,
                options=options
            )
            select.callback = self.feature_selected
            return select
        
        async def feature_selected(self, interaction: discord.Interaction):
            """Handle feature selection"""
            # Silent permission check
            if not await is_user_bot_moderator(interaction.user):
                return

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
            # Silent permission check
            if not await is_user_bot_moderator(interaction.user):
                return

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
                    label = f"{i}. {name[:97 - len(str(i)) - 2]}."
                
                # Safely truncate description to 100 chars (Discord limit)
                desc = feature.get('description', '')
                if len(desc) > 100:
                    desc = desc[:97] + "."
                
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
                placeholder="Select a feature to remove.",
                min_values=1,
                max_values=1,
                options=options
            )
            select.callback = self.feature_selected
            return select
        
        async def feature_selected(self, interaction: discord.Interaction):
            """Handle feature selection"""
            # Silent permission check
            if not await is_user_bot_moderator(interaction.user):
                return

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
            # Silent permission check
            if not await is_user_bot_moderator(interaction.user):
                return

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

    @commands.command(name="planned")
    async def planned(self, ctx: commands.Context):
        """
        Prefix command version of the planned features viewer.
        Only users listed in database.is_user_bot_moderator are allowed to use this command.
        If the user is not a bot-moderator, the command silently returns (no message).
        """
        try:
            # Permission gate: only bot moderators can use the command.
            try:
                if not await is_user_bot_moderator(ctx.author):
                    # Silent skip per your request
                    return
            except Exception:
                # If the check fails for any reason, conservatively skip without message.
                return

            # Get all features (no filter by default, show everything)
            features = await self.get_planned_features()

            if not features:
                await ctx.send("📝 **No Features**\n\nThere are currently no features in the system.")
                return

            # Create and send embed with view (no filters applied initially)
            embed = await self.create_features_embed(page=1, status_filter=None, category_filter=None)
            view = self.FeatureView(self, current_page=1, status_filter=None, category_filter=None)
            await view.update_buttons()

            await ctx.send(embed=embed, view=view)
            logger.info(f"User {ctx.author.id} ({ctx.author.display_name}) viewed planned features (via prefix command)")
            
        except Exception as e:
            logger.error(f"Error displaying planned features: {e}", exc_info=True)
            try:
                await ctx.send("❌ **Error**\n\nFailed to load planned features. Please try again later.")
            except Exception:
                # If sending fails, log and swallow
                logger.exception("Failed to send error message to channel")

async def setup(bot):
    await bot.add_cog(PlannedFeatures(bot))
    logger.info("PlannedFeatures cog loaded successfully")
