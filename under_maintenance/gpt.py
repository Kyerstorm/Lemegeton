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

load_dotenv()

logger = logging.getLogger("gpt_v2")
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

PERSONA_LEXICON = {
    "roast":["bruh","mid","roasted","clapped","rekt"],
    "manhua":["heavens","blood","scroll","fate","ascend"],
    "dreamcore":["drift","hush","whisper","softly"],
    "ethereal":["moon","soft","faint","gleam"],
}

# ---------------- Provider layer----------------
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

# -- FreeProvider (g4f) simplified --
class FreeProvider(BaseProvider):
    def __init__(self):
        super().__init__()
        # minimal verified providers list from your earlier file
        self.working_providers = []
        if G4FProviderModule is not None:
            for name in ("Blackbox", "Chatai", "CohereForAI_C4AI_Command"):
                provider_attr = getattr(G4FProviderModule, name, None)
                if provider_attr is not None:
                    if name == "Blackbox":
                        models = ["blackboxai"]
                    elif name == "Chatai":
                        models = ["gpt-3.5-turbo","gpt-4"]
                    else:
                        models = ["command-r-plus","command-r"]
                    self.working_providers.append({"provider": provider_attr, "models": models, "name": name})
        # create a default client where possible
        try:
            self.client = G4FClient()
        except Exception:
            self.client = None

    def _select_model(self, model: Optional[str]) -> str:
        return model or "gpt-3.5-turbo"

    async def chat_completion(self, messages: List[Dict[str,str]], model: Optional[str] = None, **kwargs) -> str:
        if G4FClient is None:
            raise RuntimeError("g4f client not available")
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        # Use simplest path: let AsyncClient attempt a completion (may vary by environment)
        if G4FAsyncClient is not None:
            client = G4FAsyncClient()
            result = await client.chat.completions.create(model=self._select_model(model), messages=[{"role":"user","content":prompt}])
            # parse result
            if isinstance(result, dict):
                choices = result.get("choices", [])
                if choices and isinstance(choices, list):
                    msg = choices[0].get("message", {}).get("content")
                    if msg:
                        return msg
            if hasattr(result, "choices"):
                try:
                    return result.choices[0].message.content
                except Exception:
                    pass
            return str(result)
        else:
            # fallback to synchronous client via thread
            client = G4FClient()
            def call():
                return client.chat.completions.create(model=self._select_model(model), messages=[{"role":"user","content":prompt}], timeout=30)
            res = await asyncio.to_thread(call)
            # attempt parse
            if isinstance(res, dict):
                choices = res.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", str(res))
            if hasattr(res, "choices"):
                try:
                    return res.choices[0].message.content
                except Exception:
                    pass
            return str(res)

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        if G4FAsyncClient is None:
            raise RuntimeError("g4f async client not available")
        image_provider = getattr(G4FProviderModule, "BingCreateImages", None) or getattr(G4FProviderModule, "OpenaiChat", None)
        client = G4FAsyncClient(image_provider=image_provider)
        resp = await client.images.generate(prompt=prompt)
        # return first entry or string
        if isinstance(resp, list):
            return resp[0]
        if hasattr(resp, "url"):
            return resp.url
        return str(resp)

    def get_available_models(self) -> List[ModelInfo]:
        return [ModelInfo("gpt-3.5-turbo", ProviderType.FREE, "Free gpt-3.5-like")]

    def supports_image_generation(self) -> bool:
        return True

# -- OpenAIProvider --
class OpenAIProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        if AsyncOpenAI is None:
            raise RuntimeError("openai SDK (AsyncOpenAI) not available")
        self.client = AsyncOpenAI(api_key=api_key)

    async def chat_completion(self, messages: List[Dict[str,str]], model: Optional[str] = None, **kwargs) -> str:
        model = model or os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
        resp = await self.client.chat.completions.create(model=model, messages=messages, **kwargs)
        return resp.choices[0].message.content

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        model = model or "dall-e-3"
        resp = await self.client.images.generate(model=model, prompt=prompt, size=kwargs.get("size","1024x1024"), n=kwargs.get("n",1))
        # Return URL
        return resp.data[0].url

    def get_available_models(self) -> List[ModelInfo]:
        return [ModelInfo("gpt-4o-mini", ProviderType.OPENAI, "OpenAI GPT-4 variant")]

    def supports_image_generation(self) -> bool:
        return True

# -- ClaudeProvider (minimal) --
class ClaudeProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        if AsyncAnthropic is None:
            self.client = None
            logger.warning("Anthropic SDK not installed; Claude disabled.")
        else:
            self.client = AsyncAnthropic(api_key=api_key)

    async def chat_completion(self, messages: List[Dict[str,str]], model: Optional[str] = None, **kwargs) -> str:
        if self.client is None:
            raise RuntimeError("Anthropic SDK unavailable")
        system_message = None
        claude_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_message = m["content"]
            else:
                claude_msgs.append({"role": m["role"], "content": m["content"]})
        resp = await self.client.messages.create(model=model or "claude-3-5-haiku-latest", messages=claude_msgs, system=system_message, max_tokens=kwargs.get("max_tokens",4096))
        # parse
        if hasattr(resp, "content"):
            try:
                return resp.content[0].text
            except Exception:
                pass
        return str(resp)

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError("Claude does not support image generation")

    def get_available_models(self) -> List[ModelInfo]:
        return [ModelInfo("claude-3-5-haiku-latest", ProviderType.CLAUDE, "Claude")] 

    def supports_image_generation(self) -> bool:
        return False

# -- GeminiProvider (minimal) --
class GeminiProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        if genai is None:
            self.client = None
            logger.warning("Google generativeai SDK not installed; Gemini disabled.")
        else:
            genai.configure(api_key=api_key)

    async def chat_completion(self, messages: List[Dict[str,str]], model: Optional[str] = None, **kwargs) -> str:
        if genai is None:
            raise RuntimeError("Gemini SDK not available")
        model_name = model or "gemini-2.0-flash-exp"
        gem = genai.GenerativeModel(model_name)
        chat = gem.start_chat(history=[])
        resp = None
        for m in messages:
            if m["role"] == "user":
                resp = await asyncio.to_thread(lambda c=m["content"]: chat.send_message(c))
            elif m["role"] == "assistant":
                chat.history.append({"role":"model","parts":[m["content"]]})
        return getattr(resp, "text", str(resp) if resp else "")

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        if genai is None:
            raise RuntimeError("Gemini SDK not available")
        model_name = model or "imagen-3.0-generate-001"
        imagen = genai.ImageGenerationModel(model_name)
        resp = await asyncio.to_thread(lambda: imagen.generate_images(prompt=prompt, number_of_images=kwargs.get("n",1), aspect_ratio=kwargs.get("aspect_ratio","1:1")))
        if hasattr(resp, "images") and resp.images:
            img = resp.images[0]
            if hasattr(img, "uri"):
                return img.uri
            if hasattr(img, "_image_bytes"):
                return img._image_bytes
        return str(resp)

    def get_available_models(self) -> List[ModelInfo]:
        return [ModelInfo("gemini-2.0-flash-exp", ProviderType.GEMINI, "Gemini")]

    def supports_image_generation(self) -> bool:
        return True

# -- GrokProvider (minimal) --
class GrokProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.api_key = api_key
        self.base_url = "https://api.x.ai/v1"

    async def chat_completion(self, messages: List[Dict[str,str]], model: Optional[str] = None, **kwargs) -> str:
        try:
            model = model or "grok-2-latest"
            hdrs = {"Authorization": f"Bearer {self.api_key}", "Content-Type":"application/json"}
            data = {"model": model, "messages": messages, "temperature": kwargs.get("temperature",0.7), "max_tokens": kwargs.get("max_tokens",4096)}
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/chat/completions", headers=hdrs, json=data) as resp:
                    j = await resp.json()
                    if resp.status != 200:
                        raise Exception(f"Grok error: {j}")
                    return j["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("Grok error: %s", e)
            raise

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError("Grok does not support image generation")

    def get_available_models(self) -> List[ModelInfo]:
        return [ModelInfo("grok-2-latest", ProviderType.GROK, "Grok")]

    def supports_image_generation(self) -> bool:
        return False

# -- ProviderManager: init providers based on env keys
class ProviderManager:
    def __init__(self):
        self.providers: Dict[ProviderType, BaseProvider] = {}
        self.current_provider = ProviderType.FREE
        self._initialize_providers()

    def _validate_api_key(self, api_key: str, provider_name: str, pattern: Optional[str] = None) -> bool:
        if not api_key or len(api_key) < 10:
            logger.warning(f"{provider_name} API key invalid/too short.")
            return False
        return True

    def _initialize_providers(self):
        # Always include Free provider
        self.providers[ProviderType.FREE] = FreeProvider()
        logger.info("Free provider initialized")

        cfgs = [
            ("OPENAI_KEY", ProviderType.OPENAI, OpenAIProvider),
            ("CLAUDE_KEY", ProviderType.CLAUDE, ClaudeProvider),
            ("GEMINI_KEY", ProviderType.GEMINI, GeminiProvider),
            ("GROK_KEY", ProviderType.GROK, GrokProvider),
        ]

        for env_key, ptype, pclass in cfgs:
            key = os.getenv(env_key)
            if key:
                if self._validate_api_key(key, ptype.value):
                    try:
                        self.providers[ptype] = pclass(key)
                        logger.info(f"Initialized provider {ptype.value}")
                    except Exception as e:
                        logger.error(f"Failed to init {ptype.value}: {e}")
                else:
                    logger.warning(f"Skipping provider {ptype.value} due to key validation")

    def set_current_provider(self, provider_type: ProviderType):
        if provider_type not in self.providers:
            raise ValueError("Provider not available")
        self.current_provider = provider_type

    def get_provider(self, provider_type: Optional[ProviderType] = None) -> BaseProvider:
        if provider_type:
            return self.providers[provider_type]
        return self.providers[self.current_provider]

    def get_available_providers(self) -> List[ProviderType]:
        return list(self.providers.keys())

    def get_provider_models(self, provider_type: ProviderType) -> List[ModelInfo]:
        p = self.providers.get(provider_type)
        if not p:
            return []
        return p.get_available_models()

# ---------------- Image helper (draw) ----------------
openai_client = None
if AsyncOpenAI is not None and os.getenv("OPENAI_KEY"):
    try:
        openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_KEY"))
    except Exception as e:
        logger.warning("AsyncOpenAI init failed: %s", e)
        openai_client = None

def _get_g4f_image_provider(name: str):
    if G4FProviderModule is None:
        return None
    return getattr(G4FProviderModule, name, None)

async def draw(prompt: str, provider_name: str = "openai", size: int = 1024, count: int = 1) -> List[Any]:
    """
    Returns a list of either URLs or bytes (if provider returns bytes).
    """
    # prefer OpenAI if configured and OPENAI_ENABLED != "False"
    use_openai = (os.getenv("OPENAI_ENABLED", "True") != "False") and openai_client is not None
    if provider_name.lower() == "openai" and use_openai:
        resp = await openai_client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=f"{size}x{size}" if isinstance(size, int) else str(size),
            n=count
        )
        urls = [d.url for d in resp.data]
        return urls
    else:
        # fallback to g4f
        if G4FAsyncClient is None:
            raise RuntimeError("g4f async client not available for image generation.")
        image_provider = _get_g4f_image_provider(provider_name) or _get_g4f_image_provider("BingCreateImages")
        client = G4FAsyncClient(image_provider=image_provider)
        resp = await client.images.generate(prompt=prompt)
        if isinstance(resp, list):
            return resp[:count]
        return [str(resp)]

# ---------------- Persistence with aiosqlite ----------------
DB_PATH = os.getenv("GPT_COG_DB", "data/gpt_cog.db")
# schema:
# conversations: id INTEGER PRIMARY KEY, guild_id TEXT, user_id TEXT, ts TEXT, role TEXT, content TEXT
# guild_settings: guild_id TEXT PRIMARY KEY, persona TEXT, provider TEXT

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

# NOTE: avoid running the event loop at import time (it breaks when the bot


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
        # upsert
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
            await reply.reply(c)
        else:
            await channel.send(c)

# ---------------- Control panel UI ----------------
class ServerControlPanelView(ui.View):
    def __init__(self, cog: "GPTV2Cog", user_id: int, guild: discord.Guild, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user_id = user_id
        self.guild = guild

        # persona select
        options = [discord.SelectOption(label=name, description=data.get("style",""), emoji=data.get("emoji")) for name,data in PERSONAS.items()]
        self.persona_select = ui.Select(placeholder="Select persona (admin only)...", options=options, min_values=1, max_values=1)
        self.persona_select.callback = self.persona_select_cb
        self.add_item(self.persona_select)

        # buttons
        self.rotate_provider_btn = ui.Button(label="Rotate Provider", style=discord.ButtonStyle.primary)
        self.rotate_provider_btn.callback = self.rotate_provider_cb
        self.add_item(self.rotate_provider_btn)

        self.regen_btn = ui.Button(label="Regenerate Last", style=discord.ButtonStyle.secondary)
        self.regen_btn.callback = self.regen_cb
        self.add_item(self.regen_btn)

        self.reset_btn = ui.Button(label="Reset Conversation", style=discord.ButtonStyle.danger)
        self.reset_btn.callback = self.reset_cb
        self.add_item(self.reset_btn)

    async def persona_select_cb(self, interaction: discord.Interaction):
        # only allow server admins (has manage_guild)
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Guild permission to change the server persona.", ephemeral=True)
            return
        selected = self.persona_select.values[0]
        await set_guild_persona(self.guild.id, selected, None)
        await interaction.response.send_message(f"Server persona set to **{selected}** {PERSONAS[selected].get('emoji','')}", ephemeral=True)

    async def rotate_provider_cb(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Guild to rotate provider.", ephemeral=True)
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
        # regenerate last response for this user
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return
        result = await self.cog.regenerate_last(interaction.user.id, interaction.guild.id if interaction.guild else None)
        await interaction.response.send_message(result, ephemeral=True)

    async def reset_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return
        await clear_conversation(interaction.user.id, interaction.guild.id if interaction.guild else None)
        await interaction.response.send_message("Conversation reset.", ephemeral=True)

class OpenPanelButton(ui.View):
    def __init__(self, cog: "GPTV2Cog", owner_id: int, guild: discord.Guild, timeout: float = 300.0):
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
        view = ServerControlPanelView(self.cog, user_id=self.owner_id, guild=self.guild)
        await interaction.response.send_message("Server control panel (ephemeral):", view=view, ephemeral=True)

# ---------------- The Cog ----------------
class GPTV2Cog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.provider_manager = ProviderManager()
        self.lock = asyncio.Lock()
        # cache guild persona to avoid DB hits
        self.guild_persona_cache: Dict[int, Optional[str]] = {}
        # background task to ensure DB persists
        self.bot.loop.create_task(self._warmup())

    async def _warmup(self):
        # Ensure DB schema exists now that we're running inside the bot's event loop
        try:
            await _ensure_db()
        except Exception as e:
            logger.exception("_ensure_db() failed during warmup: %s", e)

        await self.bot.wait_until_ready()
        # pre-load guild settings into cache
        for g in self.bot.guilds:
            persona, provider = await get_guild_settings(g.id)
            self.guild_persona_cache[g.id] = persona

    def _detect_persona_trigger(self, text: str) -> Optional[str]:
        t = text.lower()
        for pname, pdata in PERSONAS.items():
            for trig in pdata.get("triggers", []):
                if re.search(rf"\b{re.escape(trig)}\b", t):
                    return pname
        return None

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
        Load conversation (persisted), append user message, ask provider, save assistant reply.
        """
        async with self.lock:
            conv = await load_conversation(user_id, guild_id, limit=100)
            # check guild persona (locked)
            guild_persona = await self._get_guild_persona(guild_id)
            if guild_persona:
                # if not already present as system message, insert it
                if not any(m["role"] == "system" for m in conv):
                    await save_message(guild_id, user_id, "system", PERSONAS[guild_persona]["prompt"])
                    conv.insert(0, {"role":"system","content":PERSONAS[guild_persona]["prompt"]})
            else:
                # if no guild persona, allow auto triggers to set persona as system message for this user-only session
                auto_p = self._detect_persona_trigger(content)
                if auto_p and not any(m["role"] == "system" for m in conv):
                    await save_message(guild_id, user_id, "system", PERSONAS[auto_p]["prompt"])
                    conv.insert(0, {"role":"system","content":PERSONAS[auto_p]["prompt"]})

            # Append user message and persist
            await save_message(guild_id, user_id, "user", content)
            conv.append({"role":"user","content":content})

            # trim
            if len(conv) > 60:
                system_msgs = [m for m in conv[:3] if m["role"] == "system"]
                conv = system_msgs + conv[-40:]

            provider = self.provider_manager.get_provider()
            try:
                result = await provider.chat_completion(messages=conv, model=None)
                await save_message(guild_id, user_id, "assistant", result)
                return result
            except Exception as e:
                logger.exception("Provider error: %s", e)
                # fallback to free
                try:
                    free = self.provider_manager.get_provider(ProviderType.FREE)
                    result = await free.chat_completion(messages=conv, model=None)
                    await save_message(guild_id, user_id, "assistant", result)
                    return result + "\n\n*⚠️ Fallback to free provider.*"
                except Exception as e2:
                    logger.error("Fallback failed: %s", e2)
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
        # We'll append new assistant reply instead of deleting historical rows
        return await self.generate_response(user_id, guild_id, last_user)

    # ---------------- Event listeners ----------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots
        if message.author.bot:
            return

        # SECRET: TGA -> reply with a message containing a button that opens ephemeral server control panel for clicker.
        if re.search(r"\bTGA\b", message.content, re.IGNORECASE):
            try:
                view = OpenPanelButton(self, owner_id=message.author.id, guild=message.guild)
                embed = discord.Embed(
                    title="Server Control Panel",
                    description="Click the button below to open the ephemeral server control panel (visible only to you).",
                    color=0x2F3136
                )
                embed.set_footer(text="Control panel expires in 5 minutes")
                await message.reply(embed=embed, view=view)
                try:
                    await message.delete()
                except Exception:
                    pass
            except Exception as e:
                logger.exception("TGA handling error: %s", e)

        # handle normal mentions or replies to the bot
        bot_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = False
        if message.reference and isinstance(message.reference.resolved, discord.Message):
            ref = message.reference.resolved
            if ref.author and ref.author.id == self.bot.user.id:
                is_reply_to_bot = True

        if bot_mentioned or is_reply_to_bot:
            user_id = message.author.id
            guild_id = message.guild.id if message.guild else None
            # strip mention tokens
            content = re.sub(rf"<@!{self.bot.user.id}>", "", message.content).strip()
            # if empty content after mention, prompt
            if not content:
                await message.reply("Yes? Mention me with something to chat or use `/help`.", reference=message)
                return

            # show typing indicator while generating (only for text)
            async with message.channel.typing():
                try:
                    response = await self.generate_response(user_id, guild_id, content)
                    # Determine persona for embed styling
                    persona = await self._get_guild_persona(guild_id) or self._detect_persona_trigger(content) or "neutral"
                    pdata = PERSONAS.get(persona, PERSONAS["neutral"])
                    embed = discord.Embed(description=response[:4096], color=pdata.get("color", 0x007BC2))
                    embed.set_author(name=f"{pdata.get('emoji','')} {persona}", icon_url=self.bot.user.display_avatar.url)
                    embed.set_footer(text=pdata.get("footer",""))
                    await message.reply(embed=embed)
                except Exception as e:
                    logger.exception("Reply generation error: %s", e)
                    await message.reply("❌ Error while generating response.", reference=message)

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

    @app_commands.command(name="provider", description="Set current provider for the bot (Manage Guild required).")
    async def provider(self, interaction: discord.Interaction, provider_name: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Guild permission to use this command.", ephemeral=True)
            return
        try:
            ptype = ProviderType(provider_name)
            self.provider_manager.set_current_provider(ptype)
            await interaction.response.send_message(f"Provider switched to `{ptype.value}`", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Could not switch provider: {e}", ephemeral=True)

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
            # prefer embed with URL if possible
            sent_any = False
            for r in results:
                if isinstance(r, bytes):
                    # upload as file if bytes
                    fp = discord.File(fp=discord.utils._bytes_to_file(r), filename="image.png") if hasattr(discord.utils, "_bytes_to_file") else None
                    if fp:
                        await interaction.followup.send(file=fp)
                    else:
                        await interaction.followup.send("Image generated (binary). Unable to attach in this environment.")
                    sent_any = True
                else:
                    text = str(r)
                    # If looks like URL, embed
                    if re.match(r"^https?://", text):
                        embed = discord.Embed(title="Image result", description=f"Prompt: {prompt}", color=0x1F8B4C)
                        embed.set_image(url=text)
                        await interaction.followup.send(embed=embed)
                        sent_any = True
                    else:
                        # send as plain text
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
            self.bot.tree.add_command(self.provider)
            self.bot.tree.add_command(self.providers)
            self.bot.tree.add_command(self.models)
            self.bot.tree.add_command(self.reset)
            self.bot.tree.add_command(self.image)
            await self.bot.tree.sync()
            logger.info("GPT v2 commands synced.")
        except Exception as e:
            logger.debug("Command sync issue: %s", e)

# ---------------- Setup ----------------
async def setup(bot: commands.Bot):
    """Load the cog into a Bot (cog-only)."""
    await bot.add_cog(GPTV2Cog(bot))
