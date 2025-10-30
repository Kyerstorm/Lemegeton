import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
import datetime
import logging
from pathlib import Path

logger = logging.getLogger("ALFiles")

DB_PATH = "data/alfiles.db"

def get_color():
    return discord.Color.from_rgb(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))


class ALFiles(commands.Cog):
    """AL Files - Anime/Manga profile image collection and sharing system."""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Ensure data directory exists
        Path("data").mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(DB_PATH)
        self.c = self.conn.cursor()
        self.setup_db()
        logger.info("ALFiles cog initialized")

    # --- SETUP ---
    def setup_db(self):
        """Initialize database tables."""
        self.c.execute('''CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contributor_id INTEGER,
            contributor_name TEXT,
            al_link TEXT,
            finalized BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        self.c.execute('''CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            image_url TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id)
        )''')
        self.conn.commit()
        logger.info("ALFiles database tables initialized")

    # --- HELPERS ---
    def get_draft(self, user_id):
        """Get user's active draft file ID."""
        self.c.execute("SELECT id FROM files WHERE contributor_id = ? AND finalized = 0", (user_id,))
        return self.c.fetchone()

    def create_draft(self, user):
        """Create a new draft file for user."""
        self.c.execute("INSERT INTO files (contributor_id, contributor_name, finalized) VALUES (?, ?, 0)", 
                       (user.id, str(user)))
        self.conn.commit()
        draft_id = self.c.lastrowid
        logger.info(f"Created draft #{draft_id} for user {user.id}")
        return draft_id

    def add_image_to_draft(self, file_id, url):
        """Add an image URL to a draft file."""
        self.c.execute("INSERT INTO images (file_id, image_url) VALUES (?, ?)", (file_id, url))
        self.conn.commit()
        logger.info(f"Added image to file #{file_id}")

    def finalize_file(self, file_id):
        """Mark a draft file as finalized/published."""
        self.c.execute("UPDATE files SET finalized = 1 WHERE id = ?", (file_id,))
        self.conn.commit()
        logger.info(f"Finalized file #{file_id}")

    def get_random_file(self, exclude_id=None):
        """Get a random finalized file ID, optionally excluding one."""
        if exclude_id:
            self.c.execute("SELECT id FROM files WHERE finalized = 1 AND id != ?", (exclude_id,))
        else:
            self.c.execute("SELECT id FROM files WHERE finalized = 1")
        files = self.c.fetchall()
        if not files:
            return None
        return random.choice(files)[0]

    def get_file_images(self, file_id):
        """Get all image URLs for a file."""
        self.c.execute("SELECT image_url FROM images WHERE file_id = ?", (file_id,))
        return [i[0] for i in self.c.fetchall()]

    def get_file_info(self, file_id):
        """Get file metadata (contributor, AL link, created date)."""
        self.c.execute("SELECT contributor_name, al_link, created_at FROM files WHERE id = ?", (file_id,))
        return self.c.fetchone()

    # --- PAGINATION VIEW ---
    class FileView(discord.ui.View):
        """Interactive view for browsing AL files with pagination and random button."""
        
        def __init__(self, cog, file_id, images, contributor_name, al_link):
            super().__init__(timeout=300)  # 5-minute timeout
            self.cog = cog
            self.file_id = file_id
            self.images = images
            self.index = 0
            self.contributor_name = contributor_name
            self.al_link = al_link

        async def update_embed(self, interaction):
            """Update the embed with current image and metadata."""
            embed = discord.Embed(
                title=f"📁 File #{self.file_id}",
                color=get_color()
            )
            embed.set_image(url=self.images[self.index])
            embed.set_footer(text=f"Contributor: {self.contributor_name}")
            if self.al_link:
                embed.add_field(name="🔗 AL Profile", value=f"[View Profile]({self.al_link})")
            embed.add_field(name="📸 Image", value=f"{self.index + 1}/{len(self.images)}", inline=False)
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
        async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Navigate to previous image."""
            self.index = (self.index - 1) % len(self.images)
            await self.update_embed(interaction)

        @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
        async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Navigate to next image."""
            self.index = (self.index + 1) % len(self.images)
            await self.update_embed(interaction)

        @discord.ui.button(label="🔀 Random", style=discord.ButtonStyle.primary)
        async def random_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Load a random different file."""
            new_id = self.cog.get_random_file(exclude_id=self.file_id)
            if not new_id:
                await interaction.response.send_message("No other files available!", ephemeral=True)
                return

            images = self.cog.get_file_images(new_id)
            contributor_name, al_link, _ = self.cog.get_file_info(new_id)
            new_view = ALFiles.FileView(self.cog, new_id, images, contributor_name, al_link)
            
            embed = discord.Embed(
                title=f"📁 File #{new_id}",
                color=get_color()
            )
            embed.set_image(url=images[0])
            embed.set_footer(text=f"Contributor: {contributor_name}")
            if al_link:
                embed.add_field(name="🔗 AL Profile", value=f"[View Profile]({al_link})")
            embed.add_field(name="📸 Image", value=f"1/{len(images)}", inline=False)
            
            await interaction.response.edit_message(embed=embed, view=new_view)

        async def on_timeout(self):
            """Disable buttons when view times out."""
            for item in self.children:
                item.disabled = True

    # --- COMMANDS ---
    @app_commands.command(name="al-files", description="📁 View or contribute AL Files (AniList profile images)")
    @app_commands.describe(
        upload="Upload an image to add to your draft file"
    )
    async def al_files(self, interaction: discord.Interaction, upload: discord.Attachment = None):
        """Main AL Files command - view random file or upload to draft."""
        user = interaction.user

        if upload:
            # Validate attachment is an image
            if not upload.content_type or not upload.content_type.startswith('image/'):
                await interaction.response.send_message("❌ Please upload a valid image file!", ephemeral=True)
                return
            
            # Add image to draft
            draft = self.get_draft(user.id)
            if not draft:
                file_id = self.create_draft(user)
                await interaction.response.send_message(
                    f"📁 Draft created (File #{file_id}).\n"
                    f"✅ First image added!\n"
                    f"Use `/al-files` again with more images to add them, or `/al-release` to publish.",
                    ephemeral=True
                )
            else:
                file_id = draft[0]
                await interaction.response.send_message(
                    f"🖼️ Image added to draft #{file_id}!\n"
                    f"Use this command again to add more, or `/al-release` to publish.",
                    ephemeral=True
                )

            self.add_image_to_draft(file_id, upload.url)
            return

        # Show random finalized file
        await interaction.response.defer()
        
        rand_id = self.get_random_file()
        if not rand_id:
            await interaction.followup.send(
                "❌ No finalized files yet!\n"
                "Be the first contributor using `/al-files upload:[image]`.",
                ephemeral=True
            )
            return

        images = self.get_file_images(rand_id)
        contributor_name, al_link, _ = self.get_file_info(rand_id)

        embed = discord.Embed(
            title=f"📁 File #{rand_id}",
            color=get_color()
        )
        embed.set_image(url=images[0])
        embed.set_footer(text=f"Contributor: {contributor_name}")
        if al_link:
            embed.add_field(name="🔗 AL Profile", value=f"[View Profile]({al_link})")
        embed.add_field(name="📸 Image", value=f"1/{len(images)}", inline=False)

        view = ALFiles.FileView(self, rand_id, images, contributor_name, al_link)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="al-release", description="✅ Release your drafted AL file to the public gallery")
    async def al_release(self, interaction: discord.Interaction):
        """Finalize and publish a draft file."""
        draft = self.get_draft(interaction.user.id)
        if not draft:
            await interaction.response.send_message(
                "❌ You don't have an active draft!\n"
                "Use `/al-files upload:[image]` to create one.",
                ephemeral=True
            )
            return

        file_id = draft[0]
        
        # Check if draft has any images
        images = self.get_file_images(file_id)
        if not images:
            await interaction.response.send_message(
                f"❌ Draft #{file_id} has no images!\n"
                "Add at least one image using `/al-files upload:[image]` before releasing.",
                ephemeral=True
            )
            return

        self.finalize_file(file_id)
        await interaction.response.send_message(
            f"✅ File #{file_id} released successfully!\n"
            f"📊 Total images: {len(images)}\n"
            f"Anyone can now view your contribution using `/al-files`."
        )
        logger.info(f"User {interaction.user.id} released file #{file_id} with {len(images)} images")

    @app_commands.command(name="al-lb", description="🏆 Show AL contributors leaderboard")
    async def al_lb(self, interaction: discord.Interaction):
        """Display leaderboard of top contributors."""
        await interaction.response.defer()
        
        self.c.execute("""
            SELECT contributor_name, COUNT(id) as total
            FROM files WHERE finalized = 1
            GROUP BY contributor_id
            ORDER BY total DESC
            LIMIT 25
        """)
        rows = self.c.fetchall()
        
        if not rows:
            await interaction.followup.send(
                "❌ No contributors yet!\n"
                "Be the first to contribute using `/al-files upload:[image]`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🏆 AL Contributors Leaderboard",
            description="Top contributors to the AL Files gallery",
            color=get_color()
        )
        
        # Add medal emojis for top 3
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, count) in enumerate(rows, start=1):
            medal = medals[i-1] if i <= 3 else f"#{i}"
            embed.add_field(
                name=f"{medal} {name}",
                value=f"📁 {count} file{'s' if count != 1 else ''}",
                inline=False
            )

        # Add total stats in footer
        self.c.execute("SELECT COUNT(DISTINCT contributor_id) FROM files WHERE finalized = 1")
        total_contributors = self.c.fetchone()[0]
        
        self.c.execute("SELECT COUNT(id) FROM files WHERE finalized = 1")
        total_files = self.c.fetchone()[0]
        
        self.c.execute("SELECT COUNT(id) FROM images WHERE file_id IN (SELECT id FROM files WHERE finalized = 1)")
        total_images = self.c.fetchone()[0]
        
        embed.set_footer(text=f"👥 {total_contributors} contributors • 📁 {total_files} files • 📸 {total_images} images")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="al-draft", description="📋 View your current draft status")
    async def al_draft(self, interaction: discord.Interaction):
        """Check current draft file status."""
        draft = self.get_draft(interaction.user.id)
        
        if not draft:
            await interaction.response.send_message(
                "📭 You don't have an active draft.\n"
                "Use `/al-files upload:[image]` to create one!",
                ephemeral=True
            )
            return
        
        file_id = draft[0]
        images = self.get_file_images(file_id)
        
        embed = discord.Embed(
            title=f"📋 Draft #{file_id}",
            description=f"Your current draft file",
            color=get_color()
        )
        
        embed.add_field(name="📸 Images", value=f"{len(images)} image{'s' if len(images) != 1 else ''}", inline=True)
        embed.add_field(name="✅ Status", value="Ready to release!" if images else "⚠️ No images yet", inline=True)
        
        if images:
            embed.set_thumbnail(url=images[0])
            embed.add_field(
                name="📤 Next Step",
                value="Use `/al-release` to publish your file!",
                inline=False
            )
        else:
            embed.add_field(
                name="📤 Next Step",
                value="Use `/al-files upload:[image]` to add images!",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_load(self):
        """Called when cog loads."""
        logger.info("ALFiles cog loaded successfully")

    async def cog_unload(self):
        """Called when cog unloads - clean up database connection."""
        if self.conn:
            self.conn.close()
            logger.info("ALFiles database connection closed")


async def setup(bot):
    """Setup function required for cog loading."""
    await bot.add_cog(ALFiles(bot))
    logger.info("ALFiles cog setup complete")