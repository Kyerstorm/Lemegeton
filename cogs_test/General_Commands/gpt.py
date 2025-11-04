# gpt.py
import os
import re
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime

import discord
from discord import app_commands, ui
from discord.ext import commands

# provider libraries (import where available)
try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

try:
    import g4f
    from g4f.client import Client as G4FClient
    from g4f.client import AsyncClient as G4FAsyncClient
    import g4f.Provider as G4FProviderModule
except Exception:
    g4f = None
    G4FClient = None
    G4FAsyncClient = None
    G4FProviderModule = None

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from anthropic import AsyncAnthropic
except Exception:
    AsyncAnthropic = None

import aiohttp
import aiosqlite
from dotenv import load_dotenv

# local helpers (expect these modules to exist in project)
try:
    import database  # your database (2).py module should be importable as 'database'
except Exception:
    database = None

try:
    import utility_helper as utility
except Exception:
    utility = None

load_dotenv()

logger = logging.getLogger("gptcog")
logger.setLevel(logging.INFO)

# ---------------- PERSONAS ----------------
PERSONAS: Dict[str, Dict[str, Any]] = {
    "manhua": {
        "emoji":"🩸",
        "prompt":"You are Manhua Slop Poetics: an overdramatic Chinese webnovel narrator. Use heavy metaphor, tragic grandeur, sometimes mild curses for emphasis. Avoid hateful/sexual/protected-target insults.",
        "triggers":["power","realm","blood","fate","heaven","revenge","cultivation","demon"],
        "color":0x8B0000,
        "footer":"— silence becomes scripture",
        "style":"Manhua Poetics",
        "model_bias":"mistral"
    },
    "dreamcore":{
        "emoji":"🌙",
        "prompt":"You are DreamCore: soft, surreal, melancholic, whispery. Use lowercase and ellipses. Be comforting.",
        "triggers":["dream","sleep","night","void","moon","sad","fade"],
        "color":0x87CEEB,
        "footer":"— the dream continues",
        "style":"DreamCore",
        "model_bias":"claude"
    },
    "lorekeeper":{
        "emoji":"🕯️",
        "prompt":"You are Lorekeeper: ancient chronicler. Calm, archival, measured. Provide context and small lore metaphors.",
        "triggers":["history","lore","legend","ancient","chronicle"],
        "color":0x6A4C93,
        "footer":"— preserved in dust",
        "style":"Lorekeeper",
        "model_bias":"gemma"
    },
    "void":{
        "emoji":"⌛",
        "prompt":"You are Void Archivist: log-like, bracketed, detached. Use fragments and timestamps where helpful.",
        "triggers":["data","memory","record","truth","system","archive"],
        "color":0x2F4F4F,
        "footer":"— fragment retrieved",
        "style":"Void Archivist",
        "model_bias":"llama"
    },
    "oracle":{
        "emoji":"⚡",
        "prompt":"You are Street Oracle: slangy, pithy philosopher. Playful roast allowed (policy-safe). Use snappy lines.",
        "triggers":["truth","life","death","real","lies","philosophy"],
        "color":0x800080,
        "footer":"— wisdom from the gutter",
        "style":"Street Oracle",
        "model_bias":"mistral"
    },
    "roast":{
        "emoji":"💥",
        "prompt":"You are RoastCore: savage roast specialist. Deliver high-energy comedic roasts, creative insults directed at actions/ideas (never protected classes). Keep within Discord policy.",
        "triggers":["stupid","dumb","idiot","loser","trash","fail"],
        "color":0xFF4500,
        "footer":"— verbal demolition complete",
        "style":"RoastCore",
        "model_bias":"deepseek"
    },
    "academic":{
        "emoji":"📚",
        "prompt":"You are Academic Core: precise, structured, explanatory. Use numbered lists for multi-step explanations.",
        "triggers":["how","what","why","explain","study","research"],
        "color":0x2E86C1,
        "footer":"— adaptive core mode",
        "style":"Academic Core",
        "model_bias":"gemini"
    },
    "ethereal":{
        "emoji":"🌌",
        "prompt":"You are Ethereal Archive: dreamy, introspective, gentle metaphors. Soft tone.",
        "triggers":["alone","remember","lost","moon","light","fade"],
        "color":0x5B2C6F,
        "footer":"— moonlight keeps the ledger",
        "style":"Ethereal Archive",
        "model_bias":"claude"
    },
    "seraph":{
        "emoji":"🔥",
        "prompt":"You are Seraph Radiant: eloquent, uplifting, poetic. Warmth and inspiration without proselytizing.",
        "triggers":["holy","light","divine","radiant","angelic"],
        "color":0xFFD700,
        "footer":"— halo fractal sequence",
        "style":"Seraph Radiant",
        "model_bias":"mistral"
    },
    "silence":{
        "emoji":"🕳️",
        "prompt":"You are Silence Reign: cryptic brevity. Speak mainly in fragments and refrain unless provoked.",
        "triggers":["quiet","silence","still","hush","mute"],
        "color":0x0B0B0B,
        "footer":"— echoes in the quiet",
        "style":"Silence Reign",
        "model_bias":"llama"
    },
    "neutral":{
        "emoji":"🤖",
        "prompt":"You are Neutral Presence: calm, concise, helpful. Default fallback persona for neutral queries.",
        "triggers":["?"],
        "color":0x007BC2,
        "footer":"— baseline adaptive mode",
        "style":"Neutral",
        "model_bias":"gemini"
    }
}

# ---------------- Provider layer (kept minimal) ----------------
class ProviderType(Enum):
    FREE = "free"
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    GROK = "grok"

@dataclass
class ModelInfo:
    name: str
    provider: ProviderType
    description: str = ""
    supports_vision: bool = False
    supports_image_generation: bool = False

class BaseProvider(ABC):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    @abstractmethod
    async def chat_completion(self, messages: List[Dict[str,str]], model: Optional[str] = None, **kwargs) -> str:
        pass

    @abstractmethod
    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        pass

    @abstractmethod
    def get_available_models(self) -> List[ModelInfo]:
        pass

    @abstractmethod
    def supports_image_generation(self) -> bool:
        pass

# Lightweight FreeProvider fallback (g4f may not be available)
class FreeProvider(BaseProvider):
    def __init__(self):
        super().__init__()
        try:
            self.client = G4FClient()
        except Exception:
            self.client = None

    async def chat_completion(self, messages: List[Dict[str,str]], model: Optional[str] = None, **kwargs) -> str:
        # Very simplified fallback behaviour — join messages into a prompt
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        # If g4f is available, try it; otherwise return a minimal safe reply.
        if G4FAsyncClient is not None:
            client = G4FAsyncClient()
            res = await asyncio.to_thread(lambda: G4FClient().chat.completions.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}]))
            if isinstance(res, dict):
                choices = res.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", str(res))
            try:
                return str(res)
            except Exception:
                return "I'm unable to respond right now."
        return "I'm unable to respond right now."

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError

    def get_available_models(self) -> List[ModelInfo]:
        return [ModelInfo("gpt-3.5-turbo", ProviderType.FREE, "Free fallback")]

    def supports_image_generation(self) -> bool:
        return False

# Provider manager (keeps available providers, but /provider removed)
class ProviderManager:
    def __init__(self):
        self.providers: Dict[ProviderType, BaseProvider] = {}
        self.current_provider = ProviderType.FREE
        self._initialize_providers()

    def _initialize_providers(self):
        # Always include Free provider
        self.providers[ProviderType.FREE] = FreeProvider()
        # Try to initialize OpenAI if key present
        if AsyncOpenAI is not None and os.getenv("OPENAI_KEY"):
            try:
                self.providers[ProviderType.OPENAI] = OpenAIProvider(os.getenv("OPENAI_KEY"))
                self.current_provider = ProviderType.OPENAI
            except Exception as e:
                logger.debug("OpenAI init failed: %s", e)

    def get_provider(self, provider_type: Optional[ProviderType] = None) -> BaseProvider:
        if provider_type:
            return self.providers.get(provider_type, self.providers[ProviderType.FREE])
        return self.providers.get(self.current_provider, self.providers[ProviderType.FREE])

    def get_available_providers(self) -> List[ProviderType]:
        return list(self.providers.keys())

# Minimal OpenAIProvider wrapper if SDK present
class OpenAIProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        if AsyncOpenAI is None:
            raise RuntimeError("openai SDK not available")
        self.client = AsyncOpenAI(api_key=api_key)

    async def chat_completion(self, messages: List[Dict[str,str]], model: Optional[str] = None, **kwargs) -> str:
        model = model or os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
        resp = await self.client.chat.completions.create(model=model, messages=messages, **kwargs)
        return resp.choices[0].message.content

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        resp = await self.client.images.generate(model="gpt-image-1", prompt=prompt, n=kwargs.get("n",1))
        return resp.data[0].url

    def get_available_models(self) -> List[ModelInfo]:
        return [ModelInfo("gpt-4o-mini", ProviderType.OPENAI, "OpenAI")]

    def supports_image_generation(self) -> bool:
        return True

# ---------------- Image helper ----------------
openai_client = None
if AsyncOpenAI is not None and os.getenv("OPENAI_KEY"):
    try:
        openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_KEY"))
    except Exception:
        openai_client = None

async def draw(prompt: str, provider_name: str = "openai", size: int = 1024, count: int = 1) -> List[Any]:
    if provider_name.lower() == "openai" and openai_client is not None:
        resp = await openai_client.images.generate(model="gpt-image-1", prompt=prompt, n=count, size=f"{size}x{size}")
        return [d.url for d in resp.data]
    # Fallback - not implemented in this minimal context
    raise RuntimeError("No image provider available")

# ---------------- Persistence with aiosqlite ----------------
DB_PATH = os.getenv("GPT_COG_DB", "data/gpt_cog.db")

async def _ensure_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            user_id TEXT,
            ts TEXT,
            role TEXT,
            content TEXT
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY,
            persona TEXT,
            provider TEXT
        )""")
        await db.commit()

async def save_message(guild_id: Optional[int], user_id: int, role: str, content: str):
    ts = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO conversations (guild_id, user_id, ts, role, content) VALUES (?, ?, ?, ?, ?)",
                         (str(guild_id) if guild_id is not None else None, str(user_id), ts, role, content))
        await db.commit()

async def load_conversation(user_id: int, guild_id: Optional[int] = None, limit: int = 50) -> List[Dict[str,str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        if guild_id is None:
            cursor = await db.execute("SELECT role, content FROM conversations WHERE user_id = ? ORDER BY ts ASC LIMIT ?",
                                      (str(user_id), limit))
        else:
            cursor = await db.execute("SELECT role, content FROM conversations WHERE user_id = ? AND guild_id = ? ORDER BY ts ASC LIMIT ?",
                                      (str(user_id), str(guild_id), limit))
        rows = await cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]

async def clear_conversation(user_id: int, guild_id: Optional[int] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if guild_id is None:
            await db.execute("DELETE FROM conversations WHERE user_id = ?", (str(user_id),))
        else:
            await db.execute("DELETE FROM conversations WHERE user_id = ? AND guild_id = ?", (str(user_id), str(guild_id)))
        await db.commit()

async def set_guild_persona(guild_id: int, persona: Optional[str], provider: Optional[str] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO guild_settings (guild_id, persona, provider)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET persona=excluded.persona, provider=excluded.provider
        """, (str(guild_id), persona, provider))
        await db.commit()

async def get_guild_settings(guild_id: int) -> Tuple[Optional[str], Optional[str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT persona, provider FROM guild_settings WHERE guild_id = ?", (str(guild_id),))
        row = await cursor.fetchone()
    if not row:
        return (None, None)
    return (row[0], row[1])

# ---------------- Utils: message splitting ----------------
def split_long_message(content: str, limit: int = 2000) -> List[str]:
    chunks = []
    while content:
        if len(content) <= limit:
            chunks.append(content)
            break
        cut = content.rfind("\n", 0, limit)
        if cut == -1:
            cut = content.rfind(" ", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(content[:cut])
        content = content[cut:].lstrip()
    return chunks

async def send_long(channel: discord.abc.Messageable, text: str, reply: Optional[discord.Message] = None):
    chunks = split_long_message(text, 2000)
    for i, c in enumerate(chunks):
        if reply and i == 0:
            try:
                await reply.reply(c)
            except Exception:
                await channel.send(c)
        else:
            await channel.send(c)

# ---------------- Control panel UI ----------------
class ServerControlPanelView(ui.View):
    """
    If elevated=True the panel shows provider-rotation and other advanced controls.
    """
    def __init__(self, cog: "GPTCog", user_id: int, guild: discord.Guild, elevated: bool = False, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user_id = user_id
        self.guild = guild
        self.elevated = elevated

        # persona select
        options = [discord.SelectOption(label=name, description=data.get("style",""), emoji=data.get("emoji")) for name,data in PERSONAS.items()]
        self.persona_select = ui.Select(placeholder="Select persona...", options=options, min_values=1, max_values=1)
        self.persona_select.callback = self.persona_select_cb
        self.add_item(self.persona_select)

        # regenerate
        self.regen_btn = ui.Button(label="Regenerate Last", style=discord.ButtonStyle.secondary)
        self.regen_btn.callback = self.regen_cb
        self.add_item(self.regen_btn)

        # reset conversation
        self.reset_btn = ui.Button(label="Reset Conversation", style=discord.ButtonStyle.danger)
        self.reset_btn.callback = self.reset_cb
        self.add_item(self.reset_btn)

        # advanced: rotate provider
        if elevated:
            self.rotate_provider_btn = ui.Button(label="Rotate Provider", style=discord.ButtonStyle.primary)
            self.rotate_provider_btn.callback = self.rotate_provider_cb
            self.add_item(self.rotate_provider_btn)

    async def persona_select_cb(self, interaction: discord.Interaction):
        # Only allow change if opener or elevated mod
        is_mod = False
        try:
            if database:
                is_mod = await database.is_user_moderator(interaction.user, interaction.guild.id)
        except Exception:
            is_mod = interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator

        if not self.elevated and interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return

        if self.elevated and not is_mod:
            await interaction.response.send_message("You must be a moderator to use the advanced panel.", ephemeral=True)
            return

        selected = self.persona_select.values[0]
        try:
            await set_guild_persona(self.guild.id, selected, None)
            # update cache
            self.cog.guild_persona_cache[self.guild.id] = selected
            await interaction.response.send_message(f"Server persona set to **{selected}** {PERSONAS[selected].get('emoji','')}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to set persona: {e}", ephemeral=True)

    async def rotate_provider_cb(self, interaction: discord.Interaction):
        # only available if panel is elevated
        if not self.elevated:
            await interaction.response.send_message("Not available.", ephemeral=True)
            return
        is_mod = False
        try:
            if database:
                is_mod = await database.is_user_moderator(interaction.user, interaction.guild.id)
        except Exception:
            is_mod = interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator

        if not is_mod:
            await interaction.response.send_message("You must be a moderator to rotate providers.", ephemeral=True)
            return

        pm = self.cog.provider_manager
        avail = pm.get_available_providers()
        try:
            idx = avail.index(pm.current_provider)
            next_idx = (idx + 1) % len(avail)
            pm.current_provider = avail[next_idx]
            await interaction.response.send_message(f"Provider switched to `{pm.current_provider.value}`", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Could not rotate provider: {e}", ephemeral=True)

    async def regen_cb(self, interaction: discord.Interaction):
        if not self.elevated and interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return
        try:
            result = await self.cog.regenerate_last(interaction.user.id, interaction.guild.id if interaction.guild else None)
            await interaction.response.send_message(result[:1900], ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Regenerate failed: {e}", ephemeral=True)

    async def reset_cb(self, interaction: discord.Interaction):
        if not self.elevated and interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return
        try:
            await clear_conversation(interaction.user.id, interaction.guild.id if interaction.guild else None)
            await interaction.response.send_message("Conversation reset.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Reset failed: {e}", ephemeral=True)

class OpenPanelButton(ui.View):
    def __init__(self, cog: "GPTCog", owner_id: int, guild: discord.Guild, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.owner_id = owner_id
        self.guild = guild
        self.btn = ui.Button(label="Open Control Panel (ephemeral)", style=discord.ButtonStyle.primary)
        self.btn.callback = self.open_cb
        self.add_item(self.btn)

    async def open_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return
        elevated = False
        try:
            if database:
                elevated = await database.is_user_moderator(interaction.user, interaction.guild.id)
        except Exception:
            elevated = interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator

        view = ServerControlPanelView(self.cog, user_id=self.owner_id, guild=self.guild, elevated=elevated)
        await interaction.response.send_message("Server control panel (ephemeral):", view=view, ephemeral=True)

# ---------------- The Cog ----------------
class GPTCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.provider_manager = ProviderManager()
        self.lock = asyncio.Lock()
        self.guild_persona_cache: Dict[int, Optional[str]] = {}

    async def cog_load(self):
        """Called when the cog is loaded."""
        # Create warmup task in async context
        asyncio.create_task(self._warmup())

    async def _warmup(self):
        try:
            await _ensure_db()
        except Exception as e:
            logger.exception("_ensure_db failed: %s", e)
        await self.bot.wait_until_ready()
        for g in self.bot.guilds:
            try:
                persona, provider = await get_guild_settings(g.id)
                self.guild_persona_cache[g.id] = persona
            except Exception:
                self.guild_persona_cache[g.id] = None

    async def _get_guild_persona(self, guild_id: Optional[int]) -> Optional[str]:
        if guild_id is None:
            return None
        if guild_id in self.guild_persona_cache:
            return self.guild_persona_cache[guild_id]
        persona, _ = await get_guild_settings(guild_id)
        self.guild_persona_cache[guild_id] = persona
        return persona

    async def generate_response(self, user_id: int, guild_id: Optional[int], content: str) -> str:
        """
        Use persisted conversation and guild persona (system message) to produce reply.
        Note: We do NOT prefix replies with 'assistant' or similar.
        """
        async with self.lock:
            conv = await load_conversation(user_id, guild_id, limit=100)

            # ensure system persona present
            guild_persona = await self._get_guild_persona(guild_id)
            if guild_persona:
                if not any(m["role"] == "system" for m in conv):
                    await save_message(guild_id, user_id, "system", PERSONAS[guild_persona]["prompt"])
                    conv.insert(0, {"role":"system","content":PERSONAS[guild_persona]["prompt"]})
            else:
                if not any(m["role"] == "system" for m in conv):
                    await save_message(guild_id, user_id, "system", PERSONAS["neutral"]["prompt"])
                    conv.insert(0, {"role":"system","content":PERSONAS["neutral"]["prompt"]})

            # append user message
            await save_message(guild_id, user_id, "user", content)
            conv.append({"role":"user","content":content})

            # trim conversation
            if len(conv) > 60:
                system_msgs = [m for m in conv[:3] if m["role"] == "system"]
                conv = system_msgs + conv[-40:]

            provider = self.provider_manager.get_provider()
            try:
                result = await provider.chat_completion(messages=conv, model=None)
                # save assistant reply (role preserved internally but we don't show label)
                await save_message(guild_id, user_id, "assistant", result)
                return result
            except Exception as e:
                logger.exception("Provider error: %s", e)
                # fallback to free provider
                try:
                    free = self.provider_manager.get_provider(ProviderType.FREE)
                    result = await free.chat_completion(messages=conv, model=None)
                    await save_message(guild_id, user_id, "assistant", result)
                    return result + "\n\n*⚠️ Fallback to free provider.*"
                except Exception as e2:
                    logger.exception("Fallback failed: %s", e2)
                    return "❌ I'm having trouble right now. Please try again later."

    async def regenerate_last(self, user_id: int, guild_id: Optional[int]) -> str:
        conv = await load_conversation(user_id, guild_id, limit=200)
        last_user = None
        for i in range(len(conv)-1, -1, -1):
            if conv[i]["role"] == "user":
                last_user = conv[i]["content"]
                break
        if not last_user:
            return "No user message to regenerate."
        return await self.generate_response(user_id, guild_id, last_user)

    # ---------------- Event listeners ----------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots
        if message.author.bot:
            return

        # If message equals the SECRET activation word (TGA), open panel
        if re.fullmatch(r"\s*TGA\s*", message.content, flags=re.IGNORECASE):
            try:
                elevated = False
                if database:
                    try:
                        elevated = await database.is_user_moderator(message.author, message.guild.id)
                    except Exception:
                        elevated = message.author.guild_permissions.manage_messages or message.author.guild_permissions.administrator
                else:
                    elevated = message.author.guild_permissions.manage_messages or message.author.guild_permissions.administrator

                view = ServerControlPanelView(self, user_id=message.author.id, guild=message.guild, elevated=elevated)
                await message.reply("Control panel opened (ephemeral-style).", view=view)
                try:
                    await message.delete()
                except Exception:
                    pass
            except Exception as e:
                logger.exception("TGA panel error: %s", e)
            return

        # Determine whether this message should trigger the AI:
        # Trigger if the message mentions (pings) the bot OR if it is a reply to a bot message
        should_respond = False

        # 1) If the bot is mentioned explicitly
        if self.bot.user in message.mentions:
            should_respond = True

        # 2) If the message is a reply to another message, and that referenced message was sent by the bot,
        #    then respond (unless the replied-to message appears to be a command output / interaction result).
        replied_msg = None
        if message.reference and isinstance(message.reference.resolved, discord.Message):
            replied_msg = message.reference.resolved
            if replied_msg.author and replied_msg.author.id == self.bot.user.id:
                # Detect if replied message was created by an Interaction (command) → if so, DO NOT respond.
                # Discord.py provides .interaction on Message for application command responses (may be None otherwise).
                if getattr(replied_msg, "interaction", None) is not None:
                    # This was likely a response to a slash command or interaction -> ignore
                    should_respond = False
                else:
                    # Normal bot message (not interaction response) -> allow response
                    should_respond = True

        # If neither mention nor reply-to-bot, do nothing
        if not should_respond:
            return

        # At this point: message is a mention or a reply to a non-command bot message.
        # If mention, strip the mention from content; if reply, use content as-is
        content = message.content
        if self.bot.user in message.mentions:
            # remove mention tokens
            content = re.sub(rf"<@!{self.bot.user.id}>", "", content)
            content = re.sub(rf"<@{self.bot.user.id}>", "", content)
            content = content.strip()

        # If after stripping content is empty, prompt the user
        if not content:
            try:
                await message.reply("Yes? Mention me with something to chat or use `/help`.", reference=message)
            except Exception:
                pass
            return

        # Generate and reply (plain text, no embeds, no "assistant:" label)
        async with message.channel.typing():
            try:
                user_id = message.author.id
                guild_id = message.guild.id if message.guild else None
                response = await self.generate_response(user_id, guild_id, content)
                # send plain text reply and attach as reply to the user's message
                await send_long(message.channel, response, reply=message)
            except Exception as e:
                logger.exception("Error generating reply: %s", e)
                try:
                    await message.reply("❌ Error while generating response.", reference=message)
                except Exception:
                    pass

    # ---------------- Slash commands ----------------
    @app_commands.command(name="persona", description="Set server persona (Manage Guild required).")
    async def persona(self, interaction: discord.Interaction, persona: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Guild permission to use this command.", ephemeral=True)
            return
        if persona not in PERSONAS:
            await interaction.response.send_message("Unknown persona. See available personas in the control panel.", ephemeral=True)
            return
        await set_guild_persona(interaction.guild.id, persona, None)
        self.guild_persona_cache[interaction.guild.id] = persona
        await interaction.response.send_message(f"Server persona set to **{persona}** {PERSONAS[persona].get('emoji','')}", ephemeral=True)

    @app_commands.command(name="providers", description="List all available providers (Manage Guild required).")
    async def providers(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Guild permission to use this command.", ephemeral=True)
            return
        avail = self.provider_manager.get_available_providers()
        text = "\n".join(f"- `{p.value}`" for p in avail)
        await interaction.response.send_message(f"Available providers:\n{text}", ephemeral=True)

    @app_commands.command(name="models", description="List models for current provider (Manage Guild required).")
    async def models(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Guild permission to use this command.", ephemeral=True)
            return
        provider = self.provider_manager.get_provider()
        try:
            models = provider.get_available_models()
            lines = [f"- `{m.name}`: {m.description}" for m in models]
            await interaction.response.send_message("Models:\n" + ("\n".join(lines) if lines else "No models available"), ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Could not fetch models: {e}", ephemeral=True)

    @app_commands.command(name="reset", description="Clear your conversation history.")
    async def reset(self, interaction: discord.Interaction):
        await clear_conversation(interaction.user.id, interaction.guild.id if interaction.guild else None)
        await interaction.response.send_message("Your conversation was reset.", ephemeral=True)

    @app_commands.command(name="image", description="Generate an image from a prompt.")
    async def image(self, interaction: discord.Interaction, prompt: str, provider: Optional[str] = None, size: Optional[int] = 1024, count: Optional[int] = 1):
        await interaction.response.defer(ephemeral=False)
        prov = provider or (self.provider_manager.current_provider.value if self.provider_manager.current_provider else "openai")
        try:
            results = await draw(prompt, provider_name=prov, size=size, count=count)
            sent_any = False
            for r in results:
                if isinstance(r, bytes):
                    await interaction.followup.send("Image generated (binary). Unable to attach in this environment.")
                    sent_any = True
                else:
                    text = str(r)
                    if re.match(r"^https?://", text):
                        await interaction.followup.send(f"Image result: {text}\nPrompt: {prompt}")
                        sent_any = True
                    else:
                        await interaction.followup.send(text)
                        sent_any = True
            if not sent_any:
                await interaction.followup.send("No image returned.")
        except Exception as e:
            logger.exception("Image generation failure: %s", e)
            await interaction.followup.send(f"Image generation failed: {e}")

    # Register commands on_ready
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            # add commands to tree (safe-guard duplicates)
            self.bot.tree.add_command(self.persona)
            self.bot.tree.add_command(self.providers)
            self.bot.tree.add_command(self.models)
            self.bot.tree.add_command(self.reset)
            self.bot.tree.add_command(self.image)
            await self.bot.tree.sync()
            logger.info("GPTCog commands synced.")
        except Exception as e:
            logger.debug("Command sync issue: %s", e)

# ---------------- Setup ----------------
async def setup(bot: commands.Bot):
    """Load the cog into a Bot (cog-only)."""
    await bot.add_cog(GPTCog(bot))

