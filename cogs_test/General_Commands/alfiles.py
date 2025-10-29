import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
import datetime

DB_PATH = "alfiles.db"

def get_color():
    return discord.Color.from_rgb(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))


class ALFiles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect(DB_PATH)
        self.c = self.conn.cursor()
        self.setup_db()

    # --- SETUP ---
    def setup_db(self):
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

    # --- HELPERS ---
    def get_draft(self, user_id):
        self.c.execute("SELECT id FROM files WHERE contributor_id = ? AND finalized = 0", (user_id,))
        return self.c.fetchone()

    def create_draft(self, user):
        self.c.execute("INSERT INTO files (contributor_id, contributor_name, finalized) VALUES (?, ?, 0)", 
                       (user.id, str(user)))
        self.conn.commit()
        return self.c.lastrowid

    def add_image_to_draft(self, file_id, url):
        self.c.execute("INSERT INTO images (file_id, image_url) VALUES (?, ?)", (file_id, url))
        self.conn.commit()

    def finalize_file(self, file_id):
        self.c.execute("UPDATE files SET finalized = 1 WHERE id = ?", (file_id,))
        self.conn.commit()

    def get_random_file(self, exclude_id=None):
        if exclude_id:
            self.c.execute("SELECT id FROM files WHERE finalized = 1 AND id != ?", (exclude_id,))
        else:
            self.c.execute("SELECT id FROM files WHERE finalized = 1")
        files = self.c.fetchall()
        if not files:
            return None
        return random.choice(files)[0]

    def get_file_images(self, file_id):
        self.c.execute("SELECT image_url FROM images WHERE file_id = ?", (file_id,))
        return [i[0] for i in self.c.fetchall()]

    def get_file_info(self, file_id):
        self.c.execute("SELECT contributor_name, al_link, created_at FROM files WHERE id = ?", (file_id,))
        return self.c.fetchone()

    # --- PAGINATION VIEW ---
    class FileView(discord.ui.View):
        def __init__(self, cog, file_id, images, contributor_name, al_link):
            super().__init__(timeout=None)
            self.cog = cog
            self.file_id = file_id
            self.images = images
            self.index = 0
            self.contributor_name = contributor_name
            self.al_link = al_link

        async def update_embed(self, interaction):
            embed = discord.Embed(
                title=f"File #{self.file_id}",
                color=get_color()
            )
            embed.set_image(url=self.images[self.index])
            embed.set_footer(text=f"Contributor: {self.contributor_name}")
            if self.al_link:
                embed.add_field(name="AL Profile", value=f"[View Profile]({self.al_link})")
            embed.add_field(name="Image", value=f"{self.index + 1}/{len(self.images)}", inline=False)
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
        async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.index = (self.index - 1) % len(self.images)
            await self.update_embed(interaction)

        @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
        async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.index = (self.index + 1) % len(self.images)
            await self.update_embed(interaction)

        @discord.ui.button(label="🔀 Random", style=discord.ButtonStyle.primary)
        async def random_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            new_id = self.cog.get_random_file(exclude_id=self.file_id)
            if not new_id:
                await interaction.response.send_message("No other files available!", ephemeral=True)
                return

            images = self.cog.get_file_images(new_id)
            contributor_name, al_link, _ = self.cog.get_file_info(new_id)
            new_view = ALFiles.FileView(self.cog, new_id, images, contributor_name, al_link)
            embed = discord.Embed(
                title=f"File #{new_id}",
                color=get_color()
            )
            embed.set_image(url=images[0])
            embed.set_footer(text=f"Contributor: {contributor_name}")
            if al_link:
                embed.add_field(name="AL Profile", value=f"[View Profile]({al_link})")
            await interaction.response.edit_message(embed=embed, view=new_view)

    # --- COMMANDS ---
    @app_commands.command(name="al_files", description="View or contribute AL Files")
    async def al_files(self, interaction: discord.Interaction, upload: discord.Attachment = None):
        user = interaction.user

        if upload:
            # Add image to draft
            draft = self.get_draft(user.id)
            if not draft:
                file_id = self.create_draft(user)
                await interaction.response.send_message(f"📁 Draft created (File #{file_id}). Upload more images to add!")
            else:
                file_id = draft[0]

            self.add_image_to_draft(file_id, upload.url)
            await interaction.followup.send(f"🖼️ Image added to draft #{file_id}! Use this command again to add more, or `/al_release` to publish.")
            return

        # Otherwise: show random finalized file
        rand_id = self.get_random_file()
        if not rand_id:
            await interaction.response.send_message("❌ No finalized files yet! Contribute using `/al_files upload`.", ephemeral=True)
            return

        images = self.get_file_images(rand_id)
        contributor_name, al_link, _ = self.get_file_info(rand_id)

        embed = discord.Embed(
            title=f"File #{rand_id}",
            color=get_color()
        )
        embed.set_image(url=images[0])
        embed.set_footer(text=f"Contributor: {contributor_name}")
        if al_link:
            embed.add_field(name="AL Profile", value=f"[View Profile]({al_link})")

        view = ALFiles.FileView(self, rand_id, images, contributor_name, al_link)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="al_release", description="Release your drafted AL file")
    async def al_release(self, interaction: discord.Interaction):
        draft = self.get_draft(interaction.user.id)
        if not draft:
            await interaction.response.send_message("You don't have an active draft!", ephemeral=True)
            return

        self.finalize_file(draft[0])
        await interaction.response.send_message(f"✅ File #{draft[0]} released successfully!")

    @app_commands.command(name="al_lb", description="Show AL contributors leaderboard")
    async def al_lb(self, interaction: discord.Interaction):
        self.c.execute("""
            SELECT contributor_name, COUNT(id) as total
            FROM files WHERE finalized = 1
            GROUP BY contributor_id
            ORDER BY total DESC
        """)
        rows = self.c.fetchall()
        if not rows:
            await interaction.response.send_message("No contributors yet!", ephemeral=True)
            return

        embed = discord.Embed(title="🏆 AL Contributors Leaderboard", color=get_color())
        for i, row in enumerate(rows, start=1):
            embed.add_field(name=f"#{i} {row[0]}", value=f"Files: {row[1]}", inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(ALFiles(bot))
