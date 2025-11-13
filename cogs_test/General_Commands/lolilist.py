import discord
from discord.ext import commands
import asyncio
import traceback
import logging
from datetime import datetime
from database import execute_db_operation
from anilist_helper import fetch_anilist_user_id, fetch_user_stats

logger = logging.getLogger("LoliList")
file_handler = logging.FileHandler("logs/loli_list.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)


class LoliList(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.per_page = 8

    async def cog_load(self):
        await self.ensure_table()

    async def ensure_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS loli_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            added_by INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            anilist_id INTEGER,
            anilist_username TEXT NOT NULL,
            anilist_url TEXT NOT NULL,
            avatar_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
        await execute_db_operation("init loli_list table", query)
        logger.info("✅ loli_list table verified or created")

    # ====================================================
    # 🧷 PREFIX MODERATOR COMMAND (Multi-Link Flow, Multi Rounds)
    # ====================================================
    @commands.command(name="loliadd")
    async def loliadd(self, ctx, link: str):
        """Moderator-only multi-round, multi-link addition flow."""
        try:
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

            # Moderator check
            mod_check = await execute_db_operation(
                "check moderator",
                "SELECT discord_id FROM bot_is_moderator WHERE discord_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
                fetch_type="one"
            )
            if not mod_check:
                logger.info(f"{ctx.author} tried loliadd without permission (ignored).")
                return

            # First confirmation
            view = self.ConfirmView()
            await ctx.send(
                embed=discord.Embed(
                    title="⚠️ Confirm Add",
                    description=f"Add **{link}** to the Loli List?",
                    color=discord.Color.yellow(),
                ),
                view=view,
                ephemeral=True
            )
            await view.wait()

            if not view.confirmed:
                await ctx.send(embed=discord.Embed(description="❌ Cancelled.", color=discord.Color.red()), ephemeral=True)
                return

            await self.process_link(ctx, link)

            # Start multi-round link collection
            more_rounds = True
            while more_rounds:
                await ctx.send(
                    embed=discord.Embed(
                        title="➕ Add More?",
                        description="Would you like to add more AniList links?\nType **yes** or **no** below.",
                        color=discord.Color.blurple(),
                    ),
                    ephemeral=True,
                )

                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel

                try:
                    reply = await self.bot.wait_for("message", check=check, timeout=30.0)
                    content = reply.content.lower()
                    await reply.delete()

                    if not content.startswith("y"):
                        more_rounds = False
                        await ctx.send(embed=discord.Embed(description="✅ Finished adding users.", color=discord.Color.green()), ephemeral=True)
                        break

                    # Accept more links
                    await ctx.send(
                        embed=discord.Embed(
                            description="Paste all AniList profile links separated by spaces or new lines.",
                            color=discord.Color.yellow(),
                        ),
                        ephemeral=True,
                    )
                    msg = await self.bot.wait_for("message", check=check, timeout=90.0)
                    links = [l.strip() for l in msg.content.split() if l.strip()]
                    await msg.delete()

                    success_count = 0
                    for l in links:
                        success = await self.process_link(ctx, l, silent=True)
                        if success:
                            success_count += 1
                    await ctx.send(
                        embed=discord.Embed(
                            description=f"✅ Added {success_count}/{len(links)} links successfully.",
                            color=discord.Color.green(),
                        ),
                        ephemeral=True,
                    )
                except asyncio.TimeoutError:
                    await ctx.send(embed=discord.Embed(description="⏰ Timeout — session ended.", color=discord.Color.orange()), ephemeral=True)
                    more_rounds = False
        except Exception as e:
            logger.error(f"Error in loliadd: {e}\n{traceback.format_exc()}")
            await ctx.send(embed=discord.Embed(description="❌ Internal error occurred.", color=discord.Color.red()), ephemeral=True)

    # ====================================================
    # 🧩 HELPER — Add Single Entry
    # ====================================================
    async def process_link(self, ctx, link: str, silent: bool = False):
        """Fetch AniList info and save user."""
        try:
            username = link.strip("/").split("/")[-1]
            anilist_id = await fetch_anilist_user_id(username)
            if not anilist_id:
                if not silent:
                    await ctx.send(embed=discord.Embed(description=f"❌ Invalid AniList link: `{link}`", color=discord.Color.red()), ephemeral=True)
                return False

            stats = await fetch_user_stats(username)
            avatar = stats.get("User", {}).get("avatar", {}).get("large") if stats else None
            display_name = stats.get("User", {}).get("name") if stats else username
            site_url = stats.get("User", {}).get("siteUrl") if stats else link

            await execute_db_operation(
                "insert loli entry",
                """
                INSERT INTO loli_list (added_by, guild_id, anilist_id, anilist_username, anilist_url, avatar_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ctx.author.id, ctx.guild.id, anilist_id, display_name, site_url, avatar)
            )

            if not silent:
                await ctx.send(
                    embed=discord.Embed(
                        description=f"✅ Added **[{display_name}]({site_url})**",
                        color=discord.Color.green(),
                    ),
                    ephemeral=True,
                )
            logger.info(f"Added {display_name} ({anilist_id}) by {ctx.author}")
            return True
        except Exception as e:
            logger.error(f"Failed to add {link}: {e}\n{traceback.format_exc()}")
            if not silent:
                await ctx.send(embed=discord.Embed(description=f"❌ Failed to add {link}", color=discord.Color.red()), ephemeral=True)
            return False

    # ====================================================
    # 💠 SLASH LEADERBOARD
    # ====================================================
    @commands.hybrid_command(name="lolilist", description="View the Loli leaderboard.")
    async def lolilist(self, ctx):
        await ctx.defer(ephemeral=False)
        try:
            entries = await execute_db_operation(
                "fetch loli entries",
                "SELECT anilist_username, anilist_url, avatar_url, created_at FROM loli_list ORDER BY created_at DESC",
                fetch_type="all",
            )
            if not entries:
                await ctx.send("❌ No entries found.", ephemeral=True)
                return

            warning_text = (
                "⚠️⚠️⚠️ **ABSOLUTELY DO NOT HARASS, CONTACT, TARGET, OR DISCUSS** "
                "ANY USERS LISTED BELOW. THIS LIST IS FOR VISUAL DISPLAY ONLY. ⚠️⚠️⚠️\n\n"
            )

            pages = [entries[i:i + self.per_page] for i in range(0, len(entries), self.per_page)]
            current = 0
            embed = await self.make_leaderboard_embed(pages[current], current + 1, len(pages))
            view = self.PaginationView(pages, current, self.make_leaderboard_embed)
            view.message = await ctx.send(content=warning_text, embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error in lolilist: {e}\n{traceback.format_exc()}")
            await ctx.send("❌ Failed to load leaderboard.", ephemeral=True)

    async def make_leaderboard_embed(self, page_entries, page_num, total_pages):
        embed = discord.Embed(
            title="Loli Leaderboard",
            color=discord.Color.from_rgb(255, 255, 255),
        )
        for i, (username, url, avatar, created_at) in enumerate(page_entries, start=1):
            date_text = created_at if isinstance(created_at, str) else created_at.strftime("%Y-%m-%d")
            embed.add_field(
                name=f"#{i} — [{username}]({url})",
                value=f"Added `{date_text}`",
                inline=False,
            )
        if page_entries[0][2]:
            embed.set_thumbnail(url=page_entries[0][2])
        embed.set_footer(text=f"Page {page_num}/{total_pages}")
        return embed

    class ConfirmView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=30)
            self.confirmed = False

        @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.confirmed = True
            await interaction.response.edit_message(embed=discord.Embed(description="Confirmed.", color=discord.Color.green()), view=None)
            self.stop()

        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.confirmed = False
            await interaction.response.edit_message(embed=discord.Embed(description="Cancelled.", color=discord.Color.red()), view=None)
            self.stop()

    class PaginationView(discord.ui.View):
        def __init__(self, pages, current, make_embed_func):
            super().__init__(timeout=120)
            self.pages = pages
            self.current = current
            self.make_embed_func = make_embed_func
            self.message = None

        @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.gray)
        async def prev(self, interaction, button):
            if self.current > 0:
                self.current -= 1
                embed = await self.make_embed_func(self.pages[self.current], self.current + 1, len(self.pages))
                await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.gray)
        async def next(self, interaction, button):
            if self.current < len(self.pages) - 1:
                self.current += 1
                embed = await self.make_embed_func(self.pages[self.current], self.current + 1, len(self.pages))
                await interaction.response.edit_message(embed=embed, view=self)

        async def on_timeout(self):
            for child in self.children:
                child.disabled = True
            if self.message:
                await self.message.edit(view=self)


async def setup(bot):
    await bot.add_cog(LoliList(bot))
