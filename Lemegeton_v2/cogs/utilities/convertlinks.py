import discord
from discord.ext import commands
from discord import app_commands
import re
import logging
import asyncio

from helpers.anilist_helper import fetch_anilist_user_id

logger = logging.getLogger("ConvertLinks")


# Unicode progress bar aesthetic
def progress_bar(done: int, total: int, length: int = 12):
    if total == 0:
        return "⣿" * length
    filled = int((done / total) * length)
    return "⣿" * filled + "⣀" * (length - filled)


# =====================================================
# Session Container
# =====================================================

class ConvertSession:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.links: list[str] = []
        self.speed_mode = False  # New feature


# =====================================================
# Speed Mode toggle button
# =====================================================

class SpeedModeView(discord.ui.View):
    def __init__(self, session: ConvertSession):
        super().__init__(timeout=30)
        self.session = session

    @discord.ui.button(label="⚡ Enable Speed Mode", style=discord.ButtonStyle.gray)
    async def toggle_speed(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.session.speed_mode = True
        await interaction.response.edit_message(
            content="⚡ **Speed Mode enabled!** Conversion will be faster with fewer retries.",
            view=None
        )
        self.stop()


# =====================================================
# Add More / Done UI
# =====================================================

class AddMoreView(discord.ui.View):
    def __init__(self, session: ConvertSession):
        super().__init__(timeout=600)
        self.session = session

    @discord.ui.button(label="➕ Add More", style=discord.ButtonStyle.blurple)
    async def add_more(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Send more links (any amount).",
            ephemeral=True
        )

    @discord.ui.button(label="⚡ Speed Mode", style=discord.ButtonStyle.gray)
    async def speed_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Enable Speed Mode?",
            ephemeral=True,
            view=SpeedModeView(self.session)
        )

    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.green)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if not self.session.links:
            return await interaction.followup.send("❌ No links to convert.", ephemeral=True)

        # Remove duplicates
        original_count = len(self.session.links)
        self.session.links = list(dict.fromkeys(self.session.links))
        removed = original_count - len(self.session.links)

        # Notify user about deduplication
        if removed > 0:
            try:
                await interaction.user.send(f"♻ Removed **{removed}** duplicate link(s).")
            except:
                pass

        total = len(self.session.links)
        converted = []
        user = interaction.user

        # DM progress
        try:
            progress_msg = await user.send(
                f"🔄 **Converting {total} link(s)...**\n"
                f"{progress_bar(0, total)} `0/{total}`"
            )
        except:
            return await interaction.followup.send(
                "❌ I couldn't DM you. Turn on DMs.",
                ephemeral=True
            )

        # Convert each link
        for i, link in enumerate(self.session.links, start=1):

            username, diagnostic = self.extract_username(link)

            # Handle diagnostics for invalid URLs
            if username is None:
                converted.append(f"{link} → ❌ Invalid ({diagnostic})")
            else:
                try:
                    if self.session.speed_mode:
                        # Fast path: only one API attempt
                        uid = await fetch_anilist_user_id(username)
                    else:
                        # Retry logic (slow but safer)
                        uid = None
                        for _ in range(3):
                            uid = await fetch_anilist_user_id(username)
                            if uid:
                                break
                            await asyncio.sleep(0.3)

                    if uid:
                        converted.append(f"https://anilist.co/user/{uid}")
                    else:
                        converted.append(f"{link} → ❌ User not found")

                except Exception as e:
                    logger.error(f"Conversion error: {e}")
                    converted.append(f"{link} → ❌ Error fetching profile")

            # Update progress bar
            try:
                await progress_msg.edit(
                    content=(
                        f"🔄 **Converting {total} link(s)...**\n"
                        f"{progress_bar(i, total)} `{i}/{total}`"
                    )
                )
            except:
                pass

        # Send final summary
        final_text = "\n".join(converted)
        try:
            await user.send(f"📦 **Your Converted Links:**\n{final_text}")
        except:
            return await interaction.followup.send("❌ Could not DM results.", ephemeral=True)

        await interaction.followup.send("✅ All results have been DM’d!", ephemeral=True)
        self.stop()

    # =====================================================
    # Username extraction with diagnostics
    # =====================================================

    @staticmethod
    def extract_username(url: str):
        """
        Returns: (username or None, diagnostic str)
        """

        if not url.startswith("http"):
            return None, "Not a URL"

        if "anilist.co" not in url:
            return None, "Not an AniList URL"

        m = re.search(r"anilist\.co\/user\/([^\/\s]+)", url)

        if not m:
            return None, "Missing username in URL"

        username = m.group(1)
        return username, "OK"


# =====================================================
# Main Cog
# =====================================================

class ConvertLinksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sessions: dict[int, ConvertSession] = {}

    @app_commands.command(
        name="convertlinks",
        description="Convert AniList profile URLs to numeric ID URLs. (Batch mode, DMs)"
    )
    async def convertlinks(self, interaction: discord.Interaction):
        user = interaction.user

        session = ConvertSession(user.id)
        self.sessions[user.id] = session

        # DM session start
        try:
            await user.send(
                "📨 **Send the first link now!**\n"
                "I will store every link automatically.\n"
                "Use the buttons after each message to add more, enable Speed Mode, or finish."
            )
        except:
            return await interaction.response.send_message(
                "❌ Enable DMs so I can message you.",
                ephemeral=True
            )

        await interaction.response.send_message("📩 Session started! Check your DMs.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot:
            return
        if msg.guild is not None:
            return  # Only DM messages matter here

        session = self.sessions.get(msg.author.id)
        if not session:
            return

        # Extract links
        links = re.findall(r"https?://\S+", msg.content)
        session.links.extend(links)

        await msg.channel.send(
            f"✔ Added **{len(links)}** link(s).\n"
            f"Total stored: **{len(session.links)}**",
            view=AddMoreView(session)
        )


async def setup(bot):
    await bot.add_cog(ConvertLinksCog(bot))
