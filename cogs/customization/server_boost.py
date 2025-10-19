import discord
from discord.ext import commands
from discord import app_commands
import logging
from pathlib import Path

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
    """Server booster role management and welcome system."""

    def __init__(self, bot):
        self.bot = bot
        logger.info("ServerBoost cog initialized")

    # ============================================================================
    # BOOSTER ROLE SYSTEM
    # ============================================================================

    @app_commands.command(name="booster-role-set", description="Create and apply a custom role with your chosen color (Server Boosters only)")
    @app_commands.describe(
        role_name="Name for your custom role",
        hex_color="Hex color code (e.g. #FF0000 for red)"
    )
    async def booster_role_set(self, interaction: discord.Interaction, role_name: str, hex_color: str):
        """Allow server boosters to create and apply custom roles with custom colors."""
        await interaction.response.defer(ephemeral=True)

        # Check if user is a server booster
        if not interaction.user.premium_since:
            await interaction.followup.send(
                "❌ **Server Booster Required**\n\n"
                "This command is only available to server boosters. "
                "Boost this server to unlock custom role creation!",
                ephemeral=True
            )
            return

        # Validate role name
        if len(role_name) < 1 or len(role_name) > 100:
            await interaction.followup.send(
                "❌ **Invalid Role Name**\n\n"
                "Role name must be between 1-100 characters long.",
                ephemeral=True
            )
            return

        # Validate hex color
        hex_color = hex_color.strip()
        if not hex_color.startswith('#'):
            hex_color = f'#{hex_color}'

        try:
            # Try to convert hex to int to validate
            int(hex_color[1:], 16)
            if len(hex_color) != 7:
                raise ValueError("Invalid length")
        except ValueError:
            await interaction.followup.send(
                "❌ **Invalid Hex Color**\n\n"
                "Please provide a valid hex color code (e.g. #FF0000, #00FF00, #0000FF).",
                ephemeral=True
            )
            return

        try:
            # Create new role (users can have multiple custom roles if they want)
            # Find the highest role the bot can manage
            bot_member = interaction.guild.get_member(self.bot.user.id)
            highest_bot_role = max(
                (role for role in bot_member.roles if role.permissions.manage_roles),
                key=lambda r: r.position,
                default=None
            )

            if not highest_bot_role:
                await interaction.followup.send(
                    "❌ **Bot Permission Error**\n\n"
                    "The bot doesn't have permission to manage roles. Please contact a server administrator.",
                    ephemeral=True
                )
                return

            # Create role below the highest manageable role
            new_role = await interaction.guild.create_role(
                name=role_name,
                color=discord.Color.from_str(hex_color),
                reason=f"Booster role created by {interaction.user}"
            )

            # Move role to appropriate position (just below the highest bot-manageable role)
            try:
                await new_role.edit(position=highest_bot_role.position - 1)
            except discord.Forbidden:
                logger.warning(f"Could not adjust role position for {new_role.name}")

            # Assign role to user
            await interaction.user.add_roles(new_role)

            await interaction.followup.send(
                f"✅ **Role Created!**\n\n"
                f"Your new booster role has been created and assigned:\n"
                f"**Name:** {role_name}\n"
                f"**Color:** {hex_color}\n\n"
                f"You can create additional roles by running this command again!",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ **Permission Error**\n\n"
                "The bot doesn't have permission to create or manage roles. Please contact a server administrator.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error creating booster role: {e}")
            await interaction.followup.send(
                "❌ **Error**\n\n"
                "An unexpected error occurred while creating your role. Please try again later.",
                ephemeral=True
            )

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
                    color=discord.Color.gold()
                )

                embed.add_field(
                    name="🎨 Custom Role Creation",
                    value="Use `/booster-role-set` to create a custom role with your chosen name and color!\n\n"
                          "**Example:** `/booster-role-set role_name:My Cool Role hex_color:#FF6B6B`",
                    inline=False
                )

                embed.add_field(
                    name="💡 Tips",
                    value="• You can update your role anytime by running the command again\n"
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