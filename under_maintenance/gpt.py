# gpt.py
"""
Unified cog combining:
 - ProviderManager (OpenAI, Claude, Gemini, Grok, free/g4f)
 - Persona definitions and persona access control
 - Image generation helper (OpenAI/g4f fallback)
 - Discord Cog with listeners, slash commands, ephemeral control panel
 - Persistent per-user conversation history via aiosqlite
"""

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

# provider libraries (import where needed)
# Install these libs: openai, g4f, google-generativeai, anthropic, aiohttp, aiosqlite, python-dotenv
try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

try:
    import g4f
    from g4f.client import Client as G4FClient
    from g4f.client import AsyncClient as G4FAsyncClient
    import g4f.Provider as G4FProviderModule
    # Many of the g4f providers exist as attributes under g4f.Provider
    # We'll reference directly where needed.
except Exception:
    g4f = None
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

logger = logging.getLogger("gpt")
logger.setLevel(logging.INFO)

# ---------------- PERSONAS (from your message) ----------------
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

# ---------------- Provider code (from your message 7) ----------------
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
        self.models: List[ModelInfo] = []

    @abstractmethod
    async def chat_completion(self, messages: List[Dict[str,str]], model: str = None, **kwargs) -> str:
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

# -- FreeProvider (g4f) --
class FreeProvider(BaseProvider):
    def __init__(self):
        super().__init__()
        # Minimal verified working providers list (from your code)
        self.working_providers = [
            {
                'provider': getattr(G4FProviderModule, 'Blackbox', None),
                'models': ['blackboxai'],
                'name': 'Blackbox'
            },
            {
                'provider': getattr(G4FProviderModule, 'Chatai', None),
                'models': ['gpt-3.5-turbo', 'gpt-4'],
                'name': 'Chatai'
            },
            {
                'provider': getattr(G4FProviderModule, 'CohereForAI_C4AI_Command', None),
                'models': ['command-r-plus', 'command-r'],
                'name': 'CohereForAI'
            }
        ]
        # Filter providers that are None (not present in g4f)
        self.working_providers = [p for p in self.working_providers if p['provider'] is not None]

        # create client with RetryProvider if available
        try:
            providers_list = [p['provider'] for p in self.working_providers]
            retry_provider = getattr(G4FProviderModule, 'RetryProvider', None)
            if retry_provider is not None and providers_list:
                self.client = G4FClient(provider=retry_provider(providers_list, shuffle=False))
            else:
                # fallback to a default g4f Client
                self.client = G4FClient()
        except Exception:
            # fall back to None client
            self.client = None

        self.current_provider_index = 0

    def _select_model(self, model: Optional[str]) -> str:
        if not model or model == "auto":
            return "gpt-3.5-turbo"
        return model

    def _get_provider_model(self, provider_info: dict, target_model: str) -> str:
        supported_models = provider_info['models']
        if target_model in supported_models:
            return target_model
        if 'gpt' in target_model.lower():
            for m in supported_models:
                if 'gpt' in m.lower():
                    return m
        if 'claude' in target_model.lower():
            for m in supported_models:
                if 'command' in m.lower():
                    return m
        return supported_models[0] if supported_models else target_model

    async def chat_completion(self, messages: List[Dict[str,str]], model: str = None, **kwargs) -> str:
        target_model = self._select_model(model)
        for attempt in range(len(self.working_providers)):
            provider_info = self.working_providers[attempt]
            try:
                provider_model = self._get_provider_model(provider_info, target_model)
                # Create a client for that provider
                client = G4FClient(provider=provider_info['provider'])
                # Convert to the API shape g4f expects (synchronous style via to_thread)
                prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
                # Use asyncio.to_thread to call blocking client if needed
                result = await asyncio.to_thread(lambda: client.chat.completions.create(model=provider_model, messages=[{"role":"user","content":prompt}], timeout=30))
                # g4f client returns a structure; attempt to parse content
                content = None
                if hasattr(result, 'choices') and result.choices:
                    content = getattr(result.choices[0].message, 'content', None)
                elif isinstance(result, dict):
                    # sometimes client returns dict-like
                    choices = result.get('choices')
                    if choices and isinstance(choices, list):
                        content = choices[0].get('message', {}).get('content')
                if content:
                    return content
            except Exception as e:
                logger.warning(f"Free provider attempt failed ({provider_info.get('name')}): {e}")
                continue
        raise Exception("All free providers failed. The service may be temporarily unavailable.")

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        # Many free providers can't reliably create images. Use g4f async client if available.
        if G4FAsyncClient is None:
            raise NotImplementedError("g4f async client not installed for image generation.")
        image_provider = getattr(G4FProviderModule, 'BingCreateImages', None) or getattr(G4FProviderModule, 'OpenaiChat', None)
        client = G4FAsyncClient(image_provider=image_provider)
        resp = await client.images.generate(prompt=prompt)
        # Try to return first element or url
        if isinstance(resp, list):
            return resp[0]
        if hasattr(resp, "url"):
            return resp.url
        return str(resp)

    def get_available_models(self) -> List[ModelInfo]:
        models = [
            ModelInfo("blackboxai", ProviderType.FREE, "Blackbox AI - reliable free model"),
            ModelInfo("gpt-3.5-turbo", ProviderType.FREE, "GPT-3.5 via Chatai - tested working"),
            ModelInfo("gpt-4", ProviderType.FREE, "GPT-4 via Chatai - tested working"),
            ModelInfo("command-r-plus", ProviderType.FREE, "Cohere Command R+ - tested working"),
            ModelInfo("command-r", ProviderType.FREE, "Cohere Command R - tested working"),
        ]
        # Filter out models for which provider was not available
        if not self.working_providers:
            return []
        return models

    def supports_image_generation(self) -> bool:
        # best-effort
        return True

# -- OpenAIProvider from message 7 --
class OpenAIProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        if AsyncOpenAI is None:
            raise RuntimeError("openai AsyncOpenAI not available. Install the openai SDK with async support.")
        self.client = AsyncOpenAI(api_key=api_key)

    async def chat_completion(self, messages: List[Dict[str,str]], model: str = None, **kwargs) -> str:
        try:
            if not model:
                model = "gpt-4o-mini"
            response = await self.client.chat.completions.create(model=model, messages=messages, **kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI provider error: {e}")
            raise

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        try:
            response = await self.client.images.generate(
                model=model or "dall-e-3",
                prompt=prompt,
                size=kwargs.get("size", "1024x1024"),
                quality=kwargs.get("quality", "standard"),
                n=1
            )
            return response.data[0].url
        except Exception as e:
            logger.error(f"OpenAI image generation error: {e}")
            raise

    def get_available_models(self) -> List[ModelInfo]:
        return [
            ModelInfo("gpt-4o", ProviderType.OPENAI, "Most capable GPT-4 model", supports_vision=True),
            ModelInfo("gpt-4o-mini", ProviderType.OPENAI, "Affordable GPT-4 model", supports_vision=True),
            ModelInfo("o1", ProviderType.OPENAI, "Reasoning model"),
            ModelInfo("o1-mini", ProviderType.OPENAI, "Smaller reasoning model"),
            ModelInfo("dall-e-3", ProviderType.OPENAI, "DALL-E 3 image generation", supports_image_generation=True),
            ModelInfo("dall-e-2", ProviderType.OPENAI, "DALL-E 2 image generation", supports_image_generation=True),
        ]

    def supports_image_generation(self) -> bool:
        return True

# -- ClaudeProvider --
class ClaudeProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        if AsyncAnthropic is None:
            logger.warning("anthropic AsyncAnthropic not installed; ClaudeProvider will be disabled.")
            self.client = None
        else:
            self.client = AsyncAnthropic(api_key=api_key)

    async def chat_completion(self, messages: List[Dict[str,str]], model: str = None, **kwargs) -> str:
        if self.client is None:
            raise RuntimeError("Anthropic client unavailable.")
        try:
            if not model:
                model = "claude-3-5-haiku-latest"
            system_message = None
            claude_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    claude_messages.append({"role": msg["role"], "content": msg["content"]})
            response = await self.client.messages.create(model=model, messages=claude_messages, system=system_message, max_tokens=kwargs.get("max_tokens", 4096))
            # response.content may be list
            return response.content[0].text if hasattr(response, "content") else getattr(response, "text", str(response))
        except Exception as e:
            logger.error(f"Claude provider error: {e}")
            raise

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError("Claude does not support image generation")

    def get_available_models(self) -> List[ModelInfo]:
        return [
            ModelInfo("claude-3-5-sonnet-latest", ProviderType.CLAUDE, "Most capable Claude model"),
            ModelInfo("claude-3-5-haiku-latest", ProviderType.CLAUDE, "Fast and affordable"),
            ModelInfo("claude-3-opus-latest", ProviderType.CLAUDE, "Previous flagship model"),
        ]

    def supports_image_generation(self) -> bool:
        return False

# -- GeminiProvider --
class GeminiProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        if genai is None:
            logger.warning("google.generativeai not installed; GeminiProvider disabled.")
            self.client = None
        else:
            genai.configure(api_key=api_key)

    async def chat_completion(self, messages: List[Dict[str,str]], model: str = None, **kwargs) -> str:
        if genai is None:
            raise RuntimeError("Gemini SDK not available.")
        try:
            if not model:
                model = "gemini-2.0-flash-exp"
            gemini_model = genai.GenerativeModel(model)
            chat = gemini_model.start_chat(history=[])
            response = None
            for msg in messages:
                if msg["role"] == "user":
                    response = await asyncio.to_thread(lambda m=msg["content"]: chat.send_message(m))
                elif msg["role"] == "assistant":
                    chat.history.append({"role": "model", "parts": [msg["content"]]})
            return response.text if response is not None else ""
        except Exception as e:
            logger.error(f"Gemini provider error: {e}")
            raise

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        if genai is None:
            raise RuntimeError("Gemini SDK not available.")
        try:
            model_name = model or "imagen-3.0-generate-001"
            imagen = genai.ImageGenerationModel(model_name)
            response = await asyncio.to_thread(lambda: imagen.generate_images(prompt=prompt, number_of_images=1, aspect_ratio=kwargs.get("aspect_ratio", "1:1")))
            # response.images[0]._image_bytes or url
            if hasattr(response, "images"):
                img = response.images[0]
                if hasattr(img, "_image_bytes"):
                    return img._image_bytes
                if hasattr(img, "uri"):
                    return img.uri
            return str(response)
        except Exception as e:
            logger.error(f"Gemini image generation error: {e}")
            raise

    def get_available_models(self) -> List[ModelInfo]:
        return [
            ModelInfo("gemini-2.0-flash-exp", ProviderType.GEMINI, "Latest experimental model", supports_vision=True),
            ModelInfo("gemini-1.5-pro", ProviderType.GEMINI, "Advanced reasoning", supports_vision=True),
            ModelInfo("gemini-1.5-flash", ProviderType.GEMINI, "Fast multimodal", supports_vision=True),
            ModelInfo("imagen-3.0-generate-001", ProviderType.GEMINI, "Image generation", supports_image_generation=True),
        ]

    def supports_image_generation(self) -> bool:
        return True

# -- GrokProvider --
class GrokProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.api_key = api_key
        self.base_url = "https://api.x.ai/v1"

    async def chat_completion(self, messages: List[Dict[str,str]], model: str = None, **kwargs) -> str:
        try:
            if not model:
                model = "grok-2-latest"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            data = {"model": model, "messages": messages, "temperature": kwargs.get("temperature", 0.7), "max_tokens": kwargs.get("max_tokens", 4096)}
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/chat/completions", headers=headers, json=data) as resp:
                    result = await resp.json()
                    if resp.status != 200:
                        raise Exception(f"Grok API error: {result}")
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Grok provider error: {e}")
            raise

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError("Grok does not support image generation yet")

    def get_available_models(self) -> List[ModelInfo]:
        return [
            ModelInfo("grok-2-latest", ProviderType.GROK, "Latest Grok-2 model"),
            ModelInfo("grok-2-mini", ProviderType.GROK, "Smaller, faster Grok model"),
        ]

    def supports_image_generation(self) -> bool:
        return False

# -- ProviderManager (complete) --
class ProviderManager:
    def __init__(self):
        self.providers: Dict[ProviderType, BaseProvider] = {}
        self.current_provider = ProviderType.FREE
        self._initialize_providers()

    def _validate_api_key(self, api_key: str, provider_name: str, pattern: Optional[str] = None) -> bool:
        if not api_key or len(api_key) < 10:
            logger.warning(f"Invalid {provider_name} API key: too short (length: {len(api_key) if api_key else 0})")
            return False
        if pattern and not re.match(pattern, api_key):
            logger.warning(f"API key format warning for {provider_name}")
        return True

    def _initialize_providers(self):
        # Always add free provider
        self.providers[ProviderType.FREE] = FreeProvider()
        logger.info("Initialized free provider")

        api_configs = [
            ("OPENAI_KEY", ProviderType.OPENAI, OpenAIProvider, r'^sk-[a-zA-Z0-9]{20,}$'),
            ("CLAUDE_KEY", ProviderType.CLAUDE, ClaudeProvider, r'^sk-ant-[a-zA-Z0-9-]{10,}$'),
            ("GEMINI_KEY", ProviderType.GEMINI, GeminiProvider, r'^[a-zA-Z0-9_-]{10,}$'),
            ("GROK_KEY", ProviderType.GROK, GrokProvider, r'^xai-[a-zA-Z0-9-]{10,}$')
        ]

        for env_key, ptype, pclass, pattern in api_configs:
            api_key = os.getenv(env_key)
            if api_key:
                logger.info(f"Found {env_key} (len {len(api_key)})")
                if self._validate_api_key(api_key, ptype.value, pattern):
                    try:
                        self.providers[ptype] = pclass(api_key)
                        logger.info(f"✅ Initialized {ptype.value} provider")
                    except Exception as e:
                        logger.error(f"❌ Failed to initialize {ptype.value}: {e}")
                else:
                    logger.warning(f"❌ Skipping {ptype.value} due to invalid API key format")
            else:
                logger.debug(f"No {env_key} provided - skipping {ptype.value}")

    def get_provider(self, provider_type: Optional[ProviderType] = None) -> BaseProvider:
        if provider_type:
            if provider_type not in self.providers:
                raise ValueError(f"Provider {provider_type.value} not available")
            return self.providers[provider_type]
        return self.providers[self.current_provider]

    def set_current_provider(self, provider_type: ProviderType):
        if provider_type not in self.providers:
            raise ValueError(f"Provider {provider_type.value} not available")
        self.current_provider = provider_type

    def get_available_providers(self) -> List[ProviderType]:
        return list(self.providers.keys())

    def get_all_models(self) -> Dict[ProviderType, List[ModelInfo]]:
        result = {}
        for provider_type, provider in self.providers.items():
            try:
                result[provider_type] = provider.get_available_models()
            except Exception:
                result[provider_type] = []
        return result

    def get_provider_models(self, provider_type: ProviderType) -> List[ModelInfo]:
        if provider_type not in self.providers:
            return []
        return self.providers[provider_type].get_available_models()

# ---------------- Image generator helper (original snippet combined) ----------------
openai_client = None
if AsyncOpenAI is not None and os.getenv("OPENAI_KEY"):
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_KEY"))

def get_image_provider(provider_name: str):
    if G4FProviderModule is None:
        return None
    providers = {
        "Gemini": getattr(G4FProviderModule, "Gemini", None),
        "openai": getattr(G4FProviderModule, "OpenaiChat", None),
        "BingCreateImages": getattr(G4FProviderModule, "BingCreateImages", None),
    }
    return providers.get(provider_name, providers.get("BingCreateImages"))

async def draw(prompt: str, model: str = "openai") -> str:
    # If OPENAI_ENABLED is explicitly "False", use g4f. Default to OpenAI if key present.
    if os.getenv("OPENAI_ENABLED", "True") == "False" or openai_client is None:
        if G4FAsyncClient is None:
            raise RuntimeError("g4f async client not available for image generation.")
        image_provider = get_image_provider(model)
        g4f_client = G4FAsyncClient(image_provider=image_provider)
        response = await g4f_client.images.generate(prompt=prompt)
        if isinstance(response, list):
            return response[0]
        if hasattr(response, "url"):
            return response.url
        return str(response)
    else:
        response = await openai_client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1792x1024",
            quality="auto",
            n=1,
        )
        return response.data[0].url

# ---------------- Persistence util (aiosqlite) ----------------
DB_PATH = os.getenv("GPT_COG_DB", "gpt_cog.db")

async def ensure_db():
    # create tables: conversations (user_id TEXT, timestamp, role, content)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            user_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        await db.commit()

asyncio.get_event_loop().run_until_complete(ensure_db())

async def save_message(user_id: int, role: str, content: str):
    ts = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO conversations (user_id, ts, role, content) VALUES (?, ?, ?, ?)",
                         (str(user_id), ts, role, content))
        await db.commit()

async def load_conversation(user_id: int, limit: int = 50) -> List[Dict[str,str]]:
    rows = []
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT role, content FROM conversations WHERE user_id = ? ORDER BY ts ASC LIMIT ?",
                                  (str(user_id), limit))
        rows = await cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]

async def clear_conversation(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversations WHERE user_id = ?", (str(user_id),))
        await db.commit()

# ---------------- Utility message splitting ----------------
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

async def send_split(destination: discord.abc.Messageable, text: str, reply: Optional[discord.Message] = None):
    chunks = split_long_message(text, 2000)
    for i, c in enumerate(chunks):
        if reply and i == 0:
            await reply.reply(c)
        else:
            await destination.send(c)

# ---------------- Discord UI: Control Panel View and helper components ----------------
class ServerControlPanelView(ui.View):
    """
    Panel that will be shown ephemerally to the user in the guild when they click the 'Open Control Panel' button.
    Includes persona dropdown and buttons for rotate provider, regenerate, reset.
    Visible only to the user via ephemeral interaction.
    """
    def __init__(self, cog: "GPTCog", user_id: int, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.user_id = user_id

        options = []
        for name, pdata in PERSONAS.items():
            options.append(discord.SelectOption(label=name, description=pdata.get("style",""), emoji=pdata.get("emoji")))

        self.persona_select = ui.Select(placeholder="Select persona...", options=options, min_values=1, max_values=1)
        self.persona_select.callback = self.persona_select_cb
        self.add_item(self.persona_select)

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
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return
        selected = self.persona_select.values[0]
        await self.cog._set_persona_for_user(interaction.user, selected)
        await interaction.response.send_message(f"Persona set to **{selected}** {PERSONAS[selected].get('emoji')}", ephemeral=True)

    async def rotate_provider_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return
        pm = self.cog.provider_manager
        avail = pm.get_available_providers()
        try:
            idx = avail.index(pm.current_provider)
            next_idx = (idx + 1) % len(avail)
            pm.current_provider = avail[next_idx]
            await interaction.response.send_message(f"Provider switched to `{pm.current_provider.value}`", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Could not switch provider: {e}", ephemeral=True)

    async def regen_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return
        result = await self.cog.regenerate_last(interaction.user.id)
        await interaction.response.send_message(result, ephemeral=True)

    async def reset_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel isn't for you.", ephemeral=True)
            return
        await clear_conversation(interaction.user.id)
        await self.cog._set_persona_for_user(interaction.user, "neutral")
        await interaction.response.send_message("Conversation reset and persona set to neutral.", ephemeral=True)

class OpenPanelButton(ui.View):
    def __init__(self, cog: "GPTCog", owner_id: int, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.owner_id = owner_id
        self.open_btn = ui.Button(label="Open Control Panel (ephemeral)", style=discord.ButtonStyle.primary)
        self.open_btn.callback = self.open_cb
        self.add_item(self.open_btn)

    async def open_cb(self, interaction: discord.Interaction):
        # Only allow the triggering user to use the button to open ephemeral panel
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("You are not authorized to open this panel.", ephemeral=True)
            return
        view = ServerControlPanelView(self.cog, user_id=self.owner_id)
        await interaction.response.send_message("Server Control Panel (ephemeral):", view=view, ephemeral=True)

# ---------------- The Cog ----------------
class GPTCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.provider_manager = ProviderManager()
        self.lock = asyncio.Lock()
        # ensure default persona mapping is in metadata if needed
        # per-user current persona fallback: neutral
        # DB handles persistence; keep an in-memory cache for speed (optional)
        self.persona_cache: Dict[int, str] = {}  # user_id -> persona
        # Register background task to ensure db alive
        # Not necessary to loop, but safe to ensure DB exists (done above)
        self.bot.loop.create_task(self._ensure_app_commands_registered())

    async def _ensure_app_commands_registered(self):
        await self.bot.wait_until_ready()
        # ensure sync of commands (in on_ready we also add them)
        try:
            # commands are attached when Cog is loaded via tree sync
            logger.info("GPTCog ready")
        except Exception as e:
            logger.debug("App command registration issue: %s", e)

    # --- Persona / metadata helpers ---
    async def _set_persona_for_user(self, user: discord.User, persona: str):
        if persona not in PERSONAS:
            raise ValueError("Unknown persona")
        # clear existing conversation for clean persona context
        await clear_conversation(user.id)
        self.persona_cache[user.id] = persona
        persona_prompt = PERSONAS[persona]["prompt"]
        # save persona as system message
        await save_message(user.id, "system", persona_prompt)
        try:
            await user.send(f"Persona switched to **{persona}** {PERSONAS[persona].get('emoji','')}")
        except Exception:
            # silent if can't DM
            pass

    def _get_persona_for_user(self, user_id: int) -> str:
        return self.persona_cache.get(user_id, "neutral")

    def _detect_persona_trigger(self, text: str) -> Optional[str]:
        t = text.lower()
        for pname, pdata in PERSONAS.items():
            for trig in pdata.get("triggers", []):
                if re.search(rf"\b{re.escape(trig)}\b", t):
                    return pname
        return None

    # --- Provider/model helpers ---
    def get_provider_info(self) -> Dict[str, Any]:
        provider = self.provider_manager.get_provider()
        try:
            models = provider.get_available_models()
        except Exception:
            models = []
        return {
            "provider": self.provider_manager.current_provider.value,
            "models": [m.name for m in models],
            "supports_images": provider.supports_image_generation()
        }

    # --- Core conversation logic (persisted) ---
    async def generate_response_for_user(self, user_id: int, user_content: str) -> str:
        """
        Load conversation, append user message, pick provider, request completion, save assistant reply.
        """
        async with self.lock:
            conv = await load_conversation(user_id)
            # detect persona auto-switch
            auto = self._detect_persona_trigger(user_content)
            if auto and self._get_persona_for_user(user_id) != auto:
                await self._set_persona_for_user(self.bot.get_user(user_id) or discord.Object(id=user_id), auto)
                conv = await load_conversation(user_id)

            # Append user message and persist
            await save_message(user_id, "user", user_content)
            conv.append({"role":"user","content":user_content})

            # Trim conv to reasonable size (keep first system and last 20)
            if len(conv) > 40:
                system_msgs = [m for m in conv[:3] if m["role"] == "system"]
                conv = system_msgs + conv[-20:]

            provider = self.provider_manager.get_provider()
            try:
                result = await provider.chat_completion(messages=conv, model=None)
                await save_message(user_id, "assistant", result)
                return result
            except Exception as e:
                logger.exception("Provider error: %s", e)
                # fallback attempt to free provider
                try:
                    free = self.provider_manager.get_provider(ProviderType.FREE)
                    result = await free.chat_completion(messages=conv, model=None)
                    await save_message(user_id, "assistant", result)
                    return result + "\n\n*⚠️ Fallback to free provider due to error.*"
                except Exception as e2:
                    logger.error("Fallback failed: %s", e2)
                    return "❌ I'm having trouble right now. Please try again later."

    async def regenerate_last(self, user_id: int) -> str:
        conv = await load_conversation(user_id, limit=200)
        # find last user message
        last_user = None
        idx = None
        for i in range(len(conv)-1, -1, -1):
            if conv[i]["role"] == "user":
                last_user = conv[i]["content"]
                idx = i
                break
        if last_user is None:
            return "No user message to regenerate."
        # delete assistant messages after idx
        async with aiosqlite.connect(DB_PATH) as db:
            # delete assistant rows that are after the last user's timestamp
            # simpler: clear all assistant rows after last user message by deleting based on rowid/time - for speed, we will just append a new assistant message ignoring previous assistant duplicates
            pass
        # generate new
        return await self.generate_response_for_user(user_id, last_user)

    # --- Event listeners ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots
        if message.author.bot:
            return

        # SECRET TRIGGER: TGA -> reply with a message + button that opens ephemeral control panel
        if re.search(r"\bTGA\b", message.content, re.IGNORECASE):
            try:
                view = OpenPanelButton(self, owner_id=message.author.id)
                # reply in channel with a small ephemeral-like instruction; cannot create real ephemeral from message,
                # so we provide a button that when clicked will open an ephemeral interaction view to that user.
                embed = discord.Embed(
                    title="Server Control Panel",
                    description="Click the button below to open the server control panel (ephemeral view visible only to you).",
                    color=0x2F3136
                )
                embed.set_footer(text="Control panel access granted for 5 minutes")
                await message.reply(embed=embed, view=view)
                # optionally delete the user's TGA message for cleanliness (safe attempt)
                try:
                    await message.delete()
                except Exception:
                    pass
            except Exception as e:
                logger.exception("Could not respond to TGA: %s", e)

        # If bot mentioned or user replies to a bot message -> handle conversation
        bot_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = False
        if message.reference and isinstance(message.reference.resolved, discord.Message):
            ref = message.reference.resolved
            if ref.author and ref.author.id == self.bot.user.id:
                is_reply_to_bot = True

        if bot_mentioned or is_reply_to_bot:
            user_id = message.author.id
            # strip mention from content
            content = re.sub(rf"<@!{self.bot.user.id}>", "", message.content).strip()
            if not content:
                # If no content after mention, maybe show persona/help
                await message.reply("Yes? Mention me with something to chat or ask me `/help`.", reference=message)
                return

            # Ensure persona exists in cache, else load from DB conversation first system row
            if user_id not in self.persona_cache:
                conv = await load_conversation(user_id, limit=10)
                persona_found = "neutral"
                for m in conv:
                    if m["role"] == "system":
                        # attempt to find matching persona by exact system prompt (not guaranteed)
                        for pname, pdata in PERSONAS.items():
                            if pdata["prompt"] == m["content"]:
                                persona_found = pname
                                break
                self.persona_cache[user_id] = persona_found

            # send typing
            async with message.channel.typing():
                try:
                    response = await self.generate_response_for_user(user_id, content)
                    persona = self._get_persona_for_user(user_id)
                    color = PERSONAS.get(persona, {}).get("color", 0x007BC2)
                    footer = PERSONAS.get(persona, {}).get("footer", "")
                    emoji = PERSONAS.get(persona, {}).get("emoji", "")
                    embed = discord.Embed(description=response[:4096], color=color)
                    embed.set_footer(text=footer)
                    embed.set_author(name=f"{emoji} {persona}", icon_url=self.bot.user.display_avatar.url)
                    # reply
                    await message.reply(embed=embed)
                except Exception as e:
                    logger.exception("Error processing message: %s", e)
                    await message.reply("❌ Error while generating response.")

    # --- Slash commands: persona/provider/reset/image ---
    @app_commands.command(name="persona", description="Set your conversation persona (Manage Guild required).")
    async def persona(self, interaction: discord.Interaction, persona: str):
        # permission check
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Guild permission to use this command.", ephemeral=True)
            return
        if persona not in PERSONAS:
            await interaction.response.send_message("Unknown persona.", ephemeral=True)
            return
        await self._set_persona_for_user(interaction.user, persona)
        await interaction.response.send_message(f"Persona set to **{persona}** {PERSONAS[persona].get('emoji','')}", ephemeral=True)

    @app_commands.command(name="provider", description="Switch provider for the bot (Manage Guild required).")
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

    @app_commands.command(name="reset", description="Reset your conversation history.")
    async def reset(self, interaction: discord.Interaction):
        await clear_conversation(interaction.user.id)
        self.persona_cache[interaction.user.id] = "neutral"
        await interaction.response.send_message("Your conversation has been reset and persona set to neutral.", ephemeral=True)

    @app_commands.command(name="image", description="Generate an image from a prompt.")
    async def image(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(ephemeral=False)
        # generate image using draw function
        try:
            image_url_or_data = await draw(prompt, model="openai")
            # If result is bytes or base64, we cannot upload easily without conversion. Try to send as embed if URL.
            if isinstance(image_url_or_data, bytes):
                await interaction.followup.send("Image generated (binary). Unable to attach directly in this build. Provide a URL instead.")
            else:
                embed = discord.Embed(title="Image generation", description=f"Prompt: {prompt}", color=0x1F8B4C)
                embed.set_image(url=image_url_or_data)
                await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.exception("Image generation error: %s", e)
            await interaction.followup.send(f"Image generation failed: {e}")

    # Register cog commands when ready
    @commands.Cog.listener()
    async def on_ready(self):
        # Add commands to tree if not already present
        try:
            # Attach command objects (they already exist as methods); ensure they are registered
            self.bot.tree.add_command(self.persona)
            self.bot.tree.add_command(self.provider)
            self.bot.tree.add_command(self.reset)
            self.bot.tree.add_command(self.image)
            await self.bot.tree.sync()
            logger.info("GPTCog commands registered/synced.")
        except Exception as e:
            logger.debug("Command registration problem: %s", e)

# ---------------- Setup function for cog-only usage ----------------
async def setup(bot: commands.Bot):
    """Cog setup for discord.ext.commands loading."""
    await bot.add_cog(GPTCog(bot))
