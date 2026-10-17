from helpers.color_palette import PALETTE
import discord
from discord.ext import commands
import logging
from pathlib import Path
from helpers.lunar_roles import COMMAND_GROUP

# ------------------------------------------------------
# Logging Setup - Clears on each bot run
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "server_boost.log"

# Create logger
logger = logging.getLogger("ServerBoost")
logger.setLevel(logging.INFO)

# Remove existing handlers to avoid duplicates
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

try:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception:
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(stream_handler)

logger.info("Server Boost cog logging initialized - file or stream fallback in use")


class ServerBoost(commands.Cog):
    """Server booster welcome DM. Custom roles live in cogs/customization/lunar_roles.py."""

    def __init__(self, bot):
        self.bot = bot
        logger.info("ServerBoost cog initialized")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Send DM to new server boosters."""
        # Check if user just started boosting
        if not before.premium_since and after.premium_since:
            try:
                # Send DM to the new booster
                embed = discord.Embed(
                    title="🎉 Welcome, Server Booster!",
                    description="Thank you for boosting our server! As a token of appreciation, you now have access to special perks:",
                    color=PALETTE.WARNING
                )

                embed.add_field(
                    name="🎨 Custom Role Creation",
                    value=f"Use `/{COMMAND_GROUP} role <name>` to create your own role, "
                          f"then `/{COMMAND_GROUP} color set` to color it!\n\n"
                          f"**Example:** `/{COMMAND_GROUP} role name:My Cool Role`",
                    inline=False
                )

                embed.add_field(
                    name="💡 Tips",
                    value="• You get **one** custom role per server\n"
                          f"• Rename or recolor it anytime with `/{COMMAND_GROUP} name` and `/{COMMAND_GROUP} color set`\n"
                          "• Choose any hex color you like!",
                    inline=False
                )

                embed.set_footer(text=f"Thank you for supporting {after.guild.name}!")

                await after.send(embed=embed)
                logger.info(f"Sent booster welcome DM to {after} in {after.guild}")

            except discord.Forbidden:
                logger.warning(f"Could not send booster DM to {after} - DMs disabled")
            except Exception as e:
                logger.error(f"Error sending booster DM to {after}: {e}")


async def setup(bot):
    await bot.add_cog(ServerBoost(bot))
    logger.info("ServerBoost cog loaded successfully")