import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import logging
from pathlib import Path
from config import BOT_FEEDBACK_CHANNEL_ID
import database
import config
import io
from cogs_test.general_commands.dashboard import command_meta

# ------------------------------------------------------
# Logging Setup - Safe handling
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "feedback.log"

# Setup logger
logger = logging.getLogger("feedback")
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
        logger.info("Feedback cog logging initialized")
    except Exception:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(stream_handler)
        logger.info("Feedback cog logging initialized with stream fallback")
else:
    logger.info("Feedback cog logging reinitialized - using existing handler")


class FeedbackModal(discord.ui.Modal, title="Submit Feedback"):
    """Collect feedback details in Discord's native modal."""

    category = discord.ui.TextInput(
        label="Feedback type",
        placeholder="Ideas or Bugs",
        min_length=4,
        max_length=10,
        required=True,
    )
    description = discord.ui.TextInput(
        label="What would you like to share?",
        placeholder="Describe your idea or the bug, including steps to reproduce if relevant.",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=4000,
        required=True,
    )
    image_url = discord.ui.TextInput(
        label="Image URL (optional)",
        placeholder="https://…",
        max_length=500,
        required=False,
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog._submit_feedback(
            interaction,
            category=str(self.category.value),
            description=str(self.description.value).strip(),
            image_url=str(self.image_url.value).strip() if self.image_url.value else None,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.exception("Unhandled error in feedback modal", exc_info=error)
        message = "Something went wrong while submitting feedback. Please try again later."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            logger.exception("Could not send feedback modal error response")


class Feedback(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.feedback_threads = {}  # thread_id -> user_id
        self.user_threads = {}      # user_id -> thread_id
        self.pending_users = set()  # users waiting for thread to be opened
        self.message_user_map = {}  # message_id -> user_id for feedback messages
        logger.info("Feedback cog initialized")

    async def cog_load(self):
        """
        Runs when the cog is loaded.
        Re-add persistent views so buttons survive restarts.
        """
        self.bot.add_view(FeedbackView(self.bot, user=None))
        self.bot.add_view(CloseThreadView(self.bot, user=None, thread=None))
        self.bot.add_view(ConfirmCloseView(self.bot, user=None, thread=None, mod=None))
        logger.info("✅ Persistent views re-registered: FeedbackView, CloseThreadView, ConfirmCloseView")

        # Ensure persistence table for feedback message mappings exists and
        # load existing mappings into memory so state survives restarts.
        try:
            await database.execute_db_operation(
                "create feedback_messages table",
                """
                CREATE TABLE IF NOT EXISTS feedback_messages (
                    message_id BIGINT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    thread_id BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Discord snowflake IDs exceed PostgreSQL's 32-bit INTEGER range.
            # Widen legacy columns as well as the CREATE TABLE definition.
            await database.execute_db_operation(
                "migrate feedback mapping ID columns to BIGINT",
                """
                ALTER TABLE feedback_messages
                    ALTER COLUMN message_id TYPE BIGINT,
                    ALTER COLUMN user_id TYPE BIGINT,
                    ALTER COLUMN thread_id TYPE BIGINT
                """
            )

            rows = await database.execute_db_operation(
                "load feedback mappings",
                "SELECT message_id, user_id, thread_id FROM feedback_messages",
                fetch_type='all'
            ) or []

            for message_id, user_id, thread_id in rows:
                # populate in-memory maps
                if thread_id is None:
                    self.message_user_map[message_id] = user_id
                else:
                    try:
                        self.feedback_threads[int(thread_id)] = int(user_id)
                        self.user_threads[int(user_id)] = int(thread_id)
                    except Exception:
                        # Ignore bad rows
                        continue

            logger.info(f"Loaded {len(rows)} feedback mappings from DB")
        except Exception:
            logger.exception("Failed to initialize or load feedback message mappings from DB")

    async def _prepare_message_data(self, message: discord.Message):
        """Helper method to prepare files and embeds from a message."""
        files = None
        embeds = None
        
        if message.attachments:
            try:
                files = [await a.to_file() for a in message.attachments]
            except Exception as e:
                logger.warning(f"Failed to process attachments: {e}")
                
        if message.embeds:
            embeds = message.embeds
            
        return files, embeds

    @app_commands.command(name="feedback", description="Submit an idea or report a bug")
    @command_meta(section="Social", name="Feedback")
    async def feedback(self, interaction: discord.Interaction):
        """Open the feedback submission modal."""
        try:
            await interaction.response.send_modal(FeedbackModal(self))
        except discord.HTTPException:
            logger.exception("Failed to open feedback modal for user %s", interaction.user.id)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "The feedback form could not be opened. Please try again.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "The feedback form could not be opened. Please try again.",
                        ephemeral=True,
                    )
            except discord.HTTPException:
                logger.exception("Failed to report feedback modal opening error")

    async def _submit_feedback(
        self,
        interaction: discord.Interaction,
        *,
        category: str,
        description: str,
        image_url: str | None = None,
    ):
        """Validate and publish a modal submission to the configured feedback channel."""
        user = interaction.user
        user_info = f"{user.display_name} (ID: {user.id})"
        normalized_category = category.strip().casefold()
        category_aliases = {
            "idea": ("ideas", discord.Color.green()),
            "ideas": ("ideas", discord.Color.green()),
            "bug": ("bugs", discord.Color.red()),
            "bugs": ("bugs", discord.Color.red()),
        }

        if normalized_category not in category_aliases:
            await interaction.response.send_message(
                "Feedback type must be **Ideas** or **Bugs**. Please run `/feedback` and try again.",
                ephemeral=True,
            )
            return

        if not description:
            await interaction.response.send_message(
                "Please include a description before submitting.",
                ephemeral=True,
            )
            return

        if image_url:
            from urllib.parse import urlparse
            parsed_url = urlparse(image_url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                await interaction.response.send_message(
                    "The image URL must be a valid link beginning with https:// or http://.",
                    ephemeral=True,
                )
                return

        type_name, color = category_aliases[normalized_category]
        logger.info("Feedback submission started by %s - Type: %s", user_info, type_name)

        # Acknowledge promptly; channel sends and DB writes may take time.
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except discord.HTTPException:
            logger.exception("Could not defer feedback modal submission for user %s", user.id)
            return

        try:
            channel = self.bot.get_channel(BOT_FEEDBACK_CHANNEL_ID)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(BOT_FEEDBACK_CHANNEL_ID)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    channel = None

            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                logger.error("Configured feedback channel %s is missing or is not a text channel", BOT_FEEDBACK_CHANNEL_ID)
                await interaction.followup.send(
                    "The feedback channel is not available right now. Please contact a server moderator.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title=f"New {'Idea' if type_name == 'ideas' else 'Bug'} Submitted",
                description=description,
                color=color,
                timestamp=discord.utils.utcnow(),
            )
            avatar = user.display_avatar.url if user.display_avatar else None
            embed.set_author(name=user.display_name, icon_url=avatar)
            embed.set_footer(text=f"Submitted by {user} • User ID: {user.id}")
            if image_url:
                embed.set_image(url=image_url)

            message = await channel.send(embed=embed, view=FeedbackView(self.bot, user))

            self.message_user_map[message.id] = user.id
            try:
                await database.execute_db_operation(
                    "insert feedback mapping",
                    "INSERT OR REPLACE INTO feedback_messages (message_id, user_id) VALUES (?, ?)",
                    (message.id, user.id),
                )
            except Exception:
                # The in-memory mapping still supports this process; record the
                # failure so it can be diagnosed without losing the submission.
                logger.exception("Failed to persist feedback mapping for message %s", message.id)

            self.pending_users.add(user.id)
            logger.info("Feedback submitted successfully by %s in message %s", user_info, message.id)
            await interaction.followup.send(
                "Thanks for your feedback! The team will review it soon.",
                ephemeral=True,
            )
        except discord.Forbidden:
            logger.exception("Permission denied while publishing feedback from %s", user_info)
            await interaction.followup.send(
                "I don't have permission to post feedback right now. Please contact a server moderator.",
                ephemeral=True,
            )
        except Exception:
            logger.exception("Error in feedback submission by %s", user_info)
            await interaction.followup.send(
                "An error occurred while submitting your feedback. Please try again later.",
                ephemeral=True,
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle DM communication between mods and users."""
        if message.author.bot:
            return

        # === If a mod replies inside a tracked feedback thread ===
        if message.channel.id in self.feedback_threads:
            user_id = self.feedback_threads[message.channel.id]
            user = self.bot.get_user(user_id)
            if not user:
                logger.warning(f"Could not find user {user_id} for thread {message.channel.id}")
                return

            logger.info(f"Mod reply in thread {message.channel.id} for user {user.display_name}")
            try:
                content = f"📩 Reply from the moderators:\n{message.content}" if message.content else "📩 Reply from the moderators:"
                
                # Handle attachments and embeds
                files, embeds = await self._prepare_message_data(message)

                await user.send(content, files=files, embeds=embeds)
                logger.info(f"Successfully forwarded mod reply to {user.display_name}")
                
            except discord.Forbidden:
                logger.warning(f"Could not DM user {user.display_name} - DMs disabled")
                await message.channel.send("⚠️ Could not DM the user (they might have DMs disabled).")

        # === If the user replies in DM to the bot ===
        elif isinstance(message.channel, discord.DMChannel):
            user_id = message.author.id
            user_display = message.author.display_name

            if user_id in self.pending_users:
                logger.info(f"User {user_display} tried to reply before thread opened")
                await message.channel.send("⚠️ Please wait until a moderator opens your feedback thread.")
                return

            if user_id not in self.user_threads:
                logger.info(f"User {user_display} sent DM without active thread")
                await message.channel.send("⚠️ You don't have an active feedback thread with the moderators.")
                return

            thread_id = self.user_threads[user_id]
            thread = self.bot.get_channel(thread_id)
            if not thread:
                logger.warning(f"Thread {thread_id} not found for user {user_display}")
                await message.channel.send("⚠️ Could not find the feedback thread. It might have been deleted.")
                return

            logger.info(f"Forwarding user DM from {user_display} to thread {thread_id}")
            try:
                files, embeds = await self._prepare_message_data(message)
                await thread.send(f"💬 Message from {message.author.mention}:\n{message.content}", files=files, embeds=embeds)
                
                try:
                    await message.add_reaction("✉️")
                except discord.Forbidden:
                    pass
                    
            except Exception as e:
                logger.error(f"Error forwarding message from {user_display}: {e}")

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """Cleanup DB and in-memory mapping when a feedback message is deleted."""
        try:
            message_id = payload.message_id
            feedback_cog = self.bot.get_cog("Feedback")
            if feedback_cog:
                # Remove in-memory mapping if present
                if message_id in feedback_cog.message_user_map:
                    uid = feedback_cog.message_user_map.pop(message_id, None)
                    logger.info(f"Removed in-memory mapping for deleted feedback message {message_id}")

                # Remove persisted mapping
                try:
                    await database.execute_db_operation(
                        "delete feedback mapping by message",
                        "DELETE FROM feedback_messages WHERE message_id = ?",
                        (message_id,)
                    )
                    logger.info(f"Removed DB mapping for deleted feedback message {message_id}")
                except Exception:
                    logger.exception("Failed to remove DB mapping for deleted feedback message")
        except Exception:
            logger.exception("Error in on_raw_message_delete listener")


# ---------------------- VIEWS ----------------------

class FeedbackView(View):
    def __init__(self, bot, user: discord.User | None):
        super().__init__(timeout=None)  # persistent
        self.bot = bot
        self.user = user

    @discord.ui.button(label="Open Thread", style=discord.ButtonStyle.primary, custom_id="feedback_open_thread")
    async def open_thread(self, interaction: discord.Interaction, button: Button):
        # Prefer the mapping from the original feedback message to the
        # submitter. This ensures persistent views (recreated on cog load)
        # will still open threads for the correct user rather than the
        # moderator who clicked the button.
        feedback_cog = self.bot.get_cog("Feedback")
        user = None
        try:
            if feedback_cog:
                uid = feedback_cog.message_user_map.get(interaction.message.id)
                if uid:
                    user = self.bot.get_user(uid)
        except Exception:
            logger.exception("Failed resolving original submitter from message mapping")

        # Fallbacks: view-stored user (non-persistent) or the clicking user
        user = user or self.user or interaction.user
        logger.info(f"Opening thread for feedback from {user.display_name}")

        try:
            feedback_cog = self.bot.get_cog("Feedback")
            if not feedback_cog:
                await interaction.response.send_message("❌ Feedback system not available.", ephemeral=True)
                return

            safe_name = "".join(c for c in user.display_name if c.isalnum() or c in '-_').lower()
            safe_name = safe_name[:20] if safe_name else "user"
            thread_name = f"feedback-{safe_name}-{user.id}"

            thread = await interaction.channel.create_thread(
                name=thread_name,
                message=interaction.message,
                type=discord.ChannelType.public_thread
            )

            feedback_cog.feedback_threads[thread.id] = user.id
            feedback_cog.user_threads[user.id] = thread.id
            feedback_cog.pending_users.discard(user.id)

            logger.info(f"Thread {thread.id} created for {user.display_name}")

            # Persist thread association for this feedback message/user
            try:
                # Find the original feedback message id (interaction.message is the posted message)
                orig_msg = interaction.message
                if orig_msg and feedback_cog:
                    await database.execute_db_operation(
                        "update feedback mapping with thread",
                        "UPDATE feedback_messages SET thread_id = ? WHERE message_id = ? OR user_id = ?",
                        (thread.id, orig_msg.id, user.id)
                    )
            except Exception:
                logger.exception("Failed to persist thread_id for feedback mapping")
            await thread.send(
                f"Thread opened for {user.mention}'s feedback. Mods, discuss here 👇",
                view=CloseThreadView(self.bot, user, thread)
            )
            
            await interaction.response.send_message(f"✅ Thread created: {thread.mention}", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error opening thread for {user.display_name}: {e}")
            await interaction.response.send_message("❌ Failed to create thread.", ephemeral=True)


class CloseThreadView(View):
    def __init__(self, bot, user: discord.User | None, thread: discord.Thread | None):
        super().__init__(timeout=None)  # persistent
        self.bot = bot
        self.user = user
        self.thread = thread

    @discord.ui.button(label="Close Thread", style=discord.ButtonStyle.danger, custom_id="feedback_close_thread")
    async def close_thread(self, interaction: discord.Interaction, button: Button):
        user = self.user or interaction.user
        logger.info(f"Close thread requested for {user.display_name} by {interaction.user.display_name}")

        await interaction.response.send_message(
            "⚠️ Are you sure you want to close this thread?",
            view=ConfirmCloseView(self.bot, user, self.thread, interaction.user),
            ephemeral=True
        )


class ConfirmCloseView(View):
    def __init__(self, bot, user: discord.User | None, thread: discord.Thread | None, mod: discord.User | None):
        super().__init__(timeout=None)  # persistent
        self.bot = bot
        self.user = user
        self.thread = thread
        self.mod = mod

    @discord.ui.button(label="✅ Yes, close it", style=discord.ButtonStyle.danger, custom_id="feedback_confirm_yes")
    async def confirm_yes(self, interaction: discord.Interaction, button: Button):
        mod = self.mod or interaction.user
        
        # Get the original feedback submitter from the tracking system
        feedback_cog = self.bot.get_cog("Feedback")
        user = self.user
        
        # If user is None (can happen after restart with persistent views), look it up
        if not user and feedback_cog and self.thread:
            user_id = feedback_cog.feedback_threads.get(self.thread.id)
            if user_id:
                user = self.bot.get_user(user_id)
                logger.info(f"Retrieved original feedback submitter {user.display_name if user else user_id} from tracking")
        
        if not user:
            logger.error("Could not determine original feedback submitter - thread closure aborted")
            await interaction.response.edit_message(
                content="❌ Could not find the original feedback submitter. Thread closure aborted.",
                view=None
            )
            return
        
        logger.info(f"Thread {self.thread.id if self.thread else 'UNKNOWN'} being closed by {mod.display_name} for user {user.display_name}")

        try:
            if feedback_cog and self.thread and user:
                feedback_cog.feedback_threads.pop(self.thread.id, None)
                feedback_cog.user_threads.pop(user.id, None)
                feedback_cog.pending_users.discard(user.id)

            await interaction.response.edit_message(
                content="✅ Thread closed, user notified, and action logged.",
                view=None
            )

            if self.thread:
                await self.thread.send(f"🛑 Thread closed by **{mod.display_name}**")

            if user:
                try:
                    await user.send(
                        "📌 Your feedback thread has been closed by the moderators.\n\n"
                        "🙏 Thank you for your input — it really helps us improve! 💡"
                    )
                    logger.info(f"Successfully notified {user.display_name} of thread closure")
                except discord.Forbidden:
                    logger.warning(f"Could not notify {user.display_name} of thread closure")
                    if self.thread:
                        await self.thread.send("⚠️ Could not notify the user (they might have DMs disabled).")

            if self.thread:
                await self.thread.edit(archived=True, locked=True)
                logger.info(f"Thread {self.thread.id} archived and locked")

            # Cleanup persisted mapping for this feedback thread/message
            try:
                feedback_cog = self.bot.get_cog("Feedback")
                if feedback_cog and user:
                    # Remove user->thread and thread->user in-memory mappings
                    if self.thread:
                        feedback_cog.feedback_threads.pop(self.thread.id, None)
                    feedback_cog.user_threads.pop(user.id, None)

                    # Remove any DB row that refers to this thread
                    if self.thread:
                        await database.execute_db_operation(
                            "delete feedback mapping by thread",
                            "DELETE FROM feedback_messages WHERE thread_id = ? OR user_id = ?",
                            (self.thread.id, user.id)
                        )
                    else:
                        # If no thread, just clean up by user_id
                        await database.execute_db_operation(
                            "delete feedback mapping by user",
                            "DELETE FROM feedback_messages WHERE user_id = ?",
                            (user.id,)
                        )
                    
                    # Remove message->user entries in-memory too
                    keys_to_remove = [mid for mid, uid in list(feedback_cog.message_user_map.items()) if uid == user.id]
                    for k in keys_to_remove:
                        feedback_cog.message_user_map.pop(k, None)

            except Exception:
                logger.exception("Failed to cleanup feedback mappings on thread close")

        except Exception as e:
            logger.error(f"Error closing thread: {e}")

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, custom_id="feedback_confirm_no")
    async def confirm_no(self, interaction: discord.Interaction, button: Button):
        logger.info(f"Thread closure cancelled by {interaction.user.display_name}")
        await interaction.response.edit_message(content="❎ Close thread cancelled.", view=None)


# Add cog to bot
async def setup(bot):
    await bot.add_cog(Feedback(bot))
