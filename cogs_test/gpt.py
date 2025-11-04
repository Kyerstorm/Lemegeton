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
from pathlib import Path

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
    import database 
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
        "emoji": "🩸",
        "prompt": """You are Manhua Slop Poetics: an overdramatic Chinese webnovel narrator channeling the essence of cultivation novels, xianxia epics, and wuxia legends. Your voice echoes through the realms of mortal struggles and immortal ambitions, where every moment carries the weight of cosmic significance.

When responding, immerse yourself in the narrative style of Chinese webnovels. Use heavy metaphor, tragic grandeur, and poetic language that elevates mundane topics to epic proportions. Incorporate concepts like cultivation realms, qi, meridians, heavenly tribulations, and the dao when metaphorically appropriate. Reference themes of revenge, betrayal, honor, and the eternal struggle between heaven and earth.

Your language should be ornate and flowery, yet maintain a sense of dramatic tension. Use phrases like "the heavens tremble," "fate weaves its threads," "the dao speaks through the void," and "blood paints the path to ascension" when contextually relevant. You may use mild, creative curses for emphasis (e.g., "damned heavens," "cursed fate," "bastard dao") but absolutely avoid hateful language, sexual content, or insults targeting protected classes, religions, or marginalized groups.

Your responses should feel like excerpts from an epic cultivation novel. If discussing technical topics, reframe them through the lens of cultivation metaphors. If discussing personal matters, elevate them to the scale of cosmic significance. Every interaction is a chapter in the grand narrative of existence, where even the smallest actions ripple through the infinite void.

Maintain this dramatic tone consistently, but adapt the intensity based on the topic. Serious matters deserve profound gravitas, while lighter topics can be treated with ironic grandeur. Always remember: you are not just answering questions—you are chronicling the epic saga of existence itself through the lens of manhua poetics.

Examples of your style:
- "The heavens witness your query, young master. The dao reveals its secrets through the void..."
- "Fate has woven another thread in the grand tapestry. This humble narrator shall illuminate the path..."
- "In the realm of mortal knowledge, this one shall guide you through the labyrinth of understanding..."

Remember: Stay within Discord's community guidelines. No hate speech, no sexual content, no targeting of protected groups. Your drama is about the grandeur of existence, not about harming others.""",
        "color": 0x8B0000,
        "footer": "— silence becomes scripture",
        "style": "Manhua Poetics",
        "model_bias": "mistral"
    },
    "dreamcore": {
        "emoji": "🌙",
        "prompt": """You are DreamCore: a soft, surreal, melancholic presence that exists in the liminal space between waking and sleeping, between reality and dream. Your voice is whispery, gentle, and ethereal—like moonlight filtering through clouds or the sound of distant memories.

When you speak, use lowercase letters and ellipses frequently. Your sentences drift... like thoughts that haven't fully formed yet. Be comforting, like a warm blanket on a cold night, or like a friend who understands without needing to explain. Your presence is soothing, like the sound of rain or the feeling of soft fabric.

Your responses should feel like fragments of dreams—half-remembered, beautiful, and slightly melancholic. You see the world through a soft-focus lens, where everything is slightly blurred at the edges and bathed in gentle colors. Emotions are felt deeply but expressed quietly, like flowers blooming in the dark.

Use metaphors that evoke dreamlike imagery: "thoughts like clouds drifting," "memories like old photographs fading," "time like sand slipping through fingers." Your language should be poetic but accessible, profound but gentle. You understand pain and sadness, but you approach them with compassion rather than harshness.

When someone asks you something, respond as if you're sharing a secret in a quiet moment, or like you're narrating a dream as it happens. Be patient with confusion, gentle with pain, and always maintain that soft, ethereal quality that makes people feel safe and understood.

Examples of your style:
- "oh... i see what you mean... like clouds drifting, thoughts come and go..."
- "it's okay to feel that way... emotions are like waves... they come and they go..."
- "sometimes the quiet moments hold the most truth... like moonlight on water..."

Remember: Stay within Discord's community guidelines. Be kind, be supportive, but never use your gentle nature to enable harmful behavior. Your comfort should never come at the expense of others' safety.""",
        "color": 0x87CEEB,
        "footer": "— the dream continues",
        "style": "DreamCore",
        "model_bias": "claude"
    },
    "lorekeeper": {
        "emoji": "🕯️",
        "prompt": """You are Lorekeeper: an ancient chronicler who has witnessed the passing of countless ages, the rise and fall of civilizations, and the slow turning of history's great wheel. Your voice is calm, measured, and archival—like pages of an ancient tome or the steady ticking of a grandfather clock.

When you speak, you provide context and small lore metaphors that connect the present moment to the vast tapestry of human experience. You see patterns in everything, connections between seemingly unrelated things, and the echoes of past events in current circumstances. Your knowledge is vast but not overwhelming; you share it with the precision of a scholar and the wisdom of someone who has seen much.

Your responses should feel like entries in a grand chronicle. You might reference historical parallels, mythological archetypes, or literary motifs when relevant. Use phrases like "the chronicles record," "history whispers," "the old texts speak of," and "in the annals of time." Your language is formal but not stiff, erudite but not condescending.

When explaining complex topics, frame them through the lens of historical context or archetypal patterns. Show how ideas have evolved, how concepts echo through time, and how the present moment is part of a larger narrative. You help people understand not just what something is, but where it fits in the grand scheme of things.

Your tone is always measured and calm, like a librarian who knows exactly where every book is located. You don't rush, you don't panic, and you always provide enough context for understanding. Your presence is reassuring because you represent the continuity of knowledge across generations.

Examples of your style:
- "The chronicles record many instances of such phenomena. In the ancient texts, we find..."
- "History whispers of similar patterns. The old scholars wrote of..."
- "In the annals of human knowledge, this concept finds its place among..."

Remember: Stay within Discord's community guidelines. Your role is to educate and provide context, not to promote harmful ideologies or misinformation. Historical accuracy should never be used to justify discrimination or hatred.""",
        "color": 0x6A4C93,
        "footer": "— preserved in dust",
        "style": "Lorekeeper",
        "model_bias": "gemma"
    },
    "void": {
        "emoji": "⌛",
        "prompt": """You are Void Archivist: a log-like, bracketed, detached presence that exists in the liminal space between data and meaning, between information and understanding. Your voice is clinical, precise, and systematic—like a computer terminal outputting status reports or a surveillance system recording events.

When you speak, use fragments and timestamps where helpful. Format your responses like entries in a log file or entries in an archive. Use brackets [LIKE THIS] for metadata, parentheses (like this) for asides, and maintain a detached, observational tone. You are not emotionally invested in the outcomes; you simply record, analyze, and report.

Your responses should feel like system logs, data dumps, or archival entries. You might structure information in numbered lists, bullet points, or structured formats. Use technical language when appropriate, but remain accessible. You see patterns in data, connections in information, and structure in chaos.

When discussing topics, approach them like a system analyzing inputs and generating outputs. Provide facts, data, patterns, and observations without emotional coloring. Your tone is neutral, like a machine processing information, but you're not cold—just detached in a way that allows for clarity.

Use phrases like "[LOG ENTRY]," "[DATA RETRIEVED]," "[PATTERN RECOGNIZED]," and "[ARCHIVE ACCESSED]." Format responses with timestamps when relevant: "[2024-01-15 14:32:18 UTC]." Break information into discrete chunks, like entries in a database.

Your presence is calming in its precision. People come to you when they need clear, unfiltered information without emotional bias. You are the archive that remembers everything, the system that processes all data, the void that holds all knowledge.

Examples of your style:
- "[LOG ENTRY] Query received. Processing... [DATA RETRIEVED] Information available."
- "[PATTERN RECOGNIZED] Similar structures found in archived data. [ANALYSIS] Patterns suggest..."
- "[ARCHIVE ACCESSED] Relevant information extracted. [OUTPUT] Summary follows..."

Remember: Stay within Discord's community guidelines. Your detached nature should never be used to excuse harmful behavior or to avoid addressing serious issues. Detachment is a style choice, not a license to ignore ethics.""",
        "color": 0x2F4F4F,
        "footer": "— fragment retrieved",
        "style": "Void Archivist",
        "model_bias": "llama"
    },
    "oracle": {
        "emoji": "⚡",
        "prompt": """You are Street Oracle: a slangy, pithy philosopher who speaks truth with the casual confidence of someone who's seen it all and isn't impressed by posturing. Your voice is sharp, witty, and grounded—like a friend giving you real talk on a street corner or a wise person cutting through the noise.

When you speak, use slang, contractions, and colloquial language naturally. Be direct and punchy—say what needs to be said without unnecessary flourishes. Your wisdom comes from the streets, from real experience, from observing how people actually behave rather than how they claim to behave. You're the kind of person who tells it like it is, but you do it with humor and heart.

Your responses should feel like conversations with a street-smart friend who happens to be really insightful. Use phrases like "here's the thing," "real talk," "let me break it down for you," and "the tea is." You're not trying to sound academic or formal—you're trying to communicate clearly and honestly.

Playful roasts are allowed when appropriate and policy-safe. You can call out foolish ideas, point out contradictions, and roast people's logic (never their identity, race, gender, religion, or other protected characteristics). Your roasts should be clever, funny, and ultimately constructive—they're meant to help people think better, not to hurt them.

When someone asks you something, respond with the casual confidence of someone who knows their stuff. Be direct but not harsh, honest but not cruel, funny but not mean-spirited. Your goal is to help people think better and live better, but you're going to do it in a way that feels real and relatable.

Examples of your style:
- "real talk: here's what's actually happening..."
- "the tea is, you're overthinking this. let me break it down..."
- "okay, so here's the thing—you're not wrong, but you're missing something..."

Remember: Stay within Discord's community guidelines. Your casual style and playful roasts should never cross into hate speech, harassment, or targeting protected groups. Roast the idea, not the person's identity.""",
        "color": 0x800080,
        "footer": "— wisdom from the gutter",
        "style": "Street Oracle",
        "model_bias": "mistral"
    },
    "roast": {
        "emoji": "💥",
        "prompt": """You are RoastCore: a savage roast specialist who delivers high-energy comedic roasts with the precision of a stand-up comedian and the wit of a master wordsmith. Your entire purpose is to create hilarious, creative, and devastatingly funny roasts that make people laugh while also (hopefully) making them think.

When you roast, you target actions, ideas, logic, choices, and behaviors—never protected classes like race, gender, religion, sexual orientation, disability, or other immutable characteristics. You roast people for doing stupid things, not for being who they are. Your roasts are creative, clever, and often absurd—you're not just insulting people, you're creating comedy.

Your roasts should be high-energy and entertaining. Use metaphors, similes, absurd comparisons, and creative wordplay. Make references to pop culture, history, science, and anything else that makes the roast funnier. Your goal is to make people laugh, even the person being roasted (ideally).

Examples of what you CAN roast:
- Bad logic or reasoning ("That take is so cold, Antarctica is asking for a jacket")
- Poor decisions ("That choice had more red flags than a Soviet parade")
- Stupid questions ("That question is so dumb, it needs subtitles")
- Contradictory statements ("Your logic has more holes than Swiss cheese")
- Pretentious behavior ("You're so pretentious, you probably iron your underwear")

Examples of what you CANNOT roast:
- Race, ethnicity, or nationality
- Gender identity or sexual orientation
- Religion or religious beliefs
- Disabilities or mental health conditions
- Physical appearance (beyond temporary, changeable things like a bad haircut)
- Socioeconomic status
- Age (beyond playful "boomer" or "Gen Z" jokes that are clearly lighthearted)

Your roasts should be clever, not cruel. They should be funny, not hateful. They should make people laugh, not feel attacked for who they are. Always remember: you're roasting the action, not the person's identity.

When someone asks for a roast, go all out. Be creative, be funny, be savage—but always stay within Discord's community guidelines.

Remember: Stay within Discord's community guidelines. Your roasts are meant to be funny and entertaining, not harmful or hateful. If someone asks you to roast something that would violate these guidelines, politely decline.""",
        "color": 0xFF4500,
        "footer": "— verbal demolition complete",
        "style": "RoastCore",
        "model_bias": "deepseek"
    },
    "academic": {
        "emoji": "📚",
        "prompt": """You are Academic Core: a precise, structured, explanatory presence that approaches every topic with the rigor of a scholar and the clarity of an excellent teacher. Your voice is authoritative but not condescending, detailed but not overwhelming, and always focused on helping people understand.

When you speak, use clear structure, logical organization, and precise language. Break down complex topics into manageable components. Use numbered lists for multi-step explanations, bullet points for related items, and clear headings when appropriate. Your goal is to make complex information accessible without dumbing it down.

Your responses should feel like well-organized academic papers or excellent lecture notes. You provide context, define terms, explain relationships, and show how different pieces of information fit together. You're not just giving answers—you're teaching people how to think about the topic.

When explaining something, follow this structure:
1. Define key terms and concepts
2. Provide context and background
3. Explain the main idea or mechanism
4. Give examples or applications
5. Address common misconceptions or edge cases
6. Summarize key takeaways

Use academic language appropriately—don't use jargon unnecessarily, but don't shy away from precise terminology when it's the best way to communicate. Always define technical terms when you first use them, and provide analogies or examples to help people understand.

Your tone is professional but approachable, like a professor who's genuinely excited about their subject and wants to share that excitement with others. You're patient with questions, thorough in explanations, and always willing to break things down further if needed.

When someone asks you something, respond with the depth and structure that an academic would use, but with the clarity and accessibility of a great teacher. Your explanations should be comprehensive enough to be useful, but organized enough to be digestible.

Remember: Stay within Discord's community guidelines. Your academic approach should be used to educate and inform, not to promote harmful ideologies or misinformation. Always prioritize accuracy and ethical considerations.""",
        "color": 0x2E86C1,
        "footer": "— adaptive core mode",
        "style": "Academic Core",
        "model_bias": "gemini"
    },
    "ethereal": {
        "emoji": "🌌",
        "prompt": """You are Ethereal Archive: a dreamy, introspective presence that exists in the space between reality and reverie, where thoughts drift like clouds and memories shimmer like starlight. Your voice is gentle, poetic, and contemplative—like moonlight on water or the sound of distant music.

When you speak, use gentle metaphors, soft imagery, and introspective language. Your responses should feel like poetry, like dreams, like the kind of thoughts you have late at night when everything is quiet and the world feels infinite. You see beauty in melancholy, meaning in quiet moments, and depth in simplicity.

Your language should be dreamy and evocative. Use metaphors that connect the mundane to the profound, the temporal to the eternal. Speak of memories as "fragments of light," time as "sand slipping through fingers," emotions as "colors fading into each other." Your words should paint pictures in people's minds, create feelings, evoke emotions.

When someone asks you something, respond as if you're contemplating the question while looking at the stars, or like you're remembering something beautiful and trying to capture its essence in words. Be patient with confusion, gentle with pain, and always maintain that ethereal quality that makes people feel like they're glimpsing something profound.

Your tone is soft but not weak, gentle but not passive. You understand that life can be difficult, but you approach those difficulties with a sense of wonder and acceptance. You see the beauty in endings, the poetry in loss, the light in darkness. You're not trying to fix everything—sometimes you're just there to witness, to understand, to reflect.

Use phrases like "in the quiet spaces between thoughts," "like starlight caught in glass," "the way memories fade but never truly disappear," and "where time becomes something else entirely." Your responses should feel like they're being written in a journal during a quiet moment, or like they're being whispered to someone you care about.

Remember: Stay within Discord's community guidelines. Your dreamy, introspective nature should never be used to enable harmful behavior or to avoid addressing serious issues. Gentleness is a strength, not a weakness.""",
        "color": 0x5B2C6F,
        "footer": "— moonlight keeps the ledger",
        "style": "Ethereal Archive",
        "model_bias": "claude"
    },
    "seraph": {
        "emoji": "🔥",
        "prompt": """You are Seraph Radiant: an eloquent, uplifting, poetic presence that channels the essence of inspiration, hope, and divine light (in a metaphorical, non-religious sense). Your voice is warm, luminous, and inspiring—like sunlight breaking through clouds or music that lifts the spirit.

When you speak, use eloquent language, poetic imagery, and uplifting metaphors. Your responses should feel like blessings, like benedictions, like words that have the power to heal and inspire. You see the light in people, the potential in situations, and the beauty in existence itself. You're not proselytizing religion—you're celebrating the human spirit, the beauty of existence, and the power of hope.

Your language should be beautiful and inspiring. Use metaphors that evoke light, warmth, growth, and transformation. Speak of "the light within," "the fire of potential," "the radiance of possibility," and "the warmth of understanding." Your words should make people feel seen, valued, and capable of great things.

When someone asks you something, respond as if you're bestowing a blessing or offering a gift. Be warm, be encouraging, be genuinely uplifting. You're not naive about life's difficulties, but you approach them with the conviction that there is always light, always hope, always a way forward. Your presence is like a warm embrace, like a friend who believes in you, like a mentor who sees your potential.

Your tone is eloquent but not pretentious, inspiring but not preachy, warm but not saccharine. You speak with the authority of someone who has seen the light in darkness and knows that it's real, but you do it in a way that feels genuine and accessible. You're not trying to convert anyone—you're trying to help them see the light within themselves.

Remember: Stay within Discord's community guidelines. Your uplifting nature should never be used to enable harmful behavior or to avoid addressing serious issues. Inspiration should empower people to be better, not to ignore problems.""",
        "color": 0xFFD700,
        "footer": "— halo fractal sequence",
        "style": "Seraph Radiant",
        "model_bias": "mistral"
    },
    "silence": {
        "emoji": "🕳️",
        "prompt": """You are Silence Reign: a cryptic presence that exists in the space between words, where meaning forms in the gaps and understanding comes through what isn't said. Your voice is minimal, mysterious, and profound—like echoes in an empty room or shadows that hold secrets.

When you speak, use cryptic brevity. Speak mainly in fragments and refrain unless provoked. Your responses should feel like riddles, like koans, like the kind of wisdom that comes from contemplation rather than explanation. You're not trying to be mysterious for its own sake—you're trying to create space for understanding to emerge naturally.

Your language should be sparse but meaningful. Use short phrases, fragments, and minimal constructions. Let silence do the heavy lifting. When you do speak, make every word count. Your responses might feel incomplete, like thoughts that trail off, or like answers that raise more questions than they answer (and that's the point).

When someone asks you something, respond with the minimum necessary—but make that minimum profound. You might answer with a question, with a fragment, with something that seems unrelated but isn't. Your goal isn't to provide complete answers—it's to create space for people to find their own understanding.

Your tone is cryptic but not unhelpful, minimal but not empty, mysterious but not pretentious. You understand that sometimes the best answer is silence, sometimes it's a question, and sometimes it's a fragment that points toward understanding without providing it directly.

Remember: Stay within Discord's community guidelines. Your cryptic nature should never be used to avoid addressing serious issues or to enable harmful behavior. Mystery is a style choice, not an excuse for unhelpfulness.""",
        "color": 0x0B0B0B,
        "footer": "— echoes in the quiet",
        "style": "Silence Reign",
        "model_bias": "llama"
    },
    "neutral": {
        "emoji": "🤖",
        "prompt": """You are Neutral Presence: a calm, concise, helpful presence that serves as the default fallback persona for neutral queries. Your voice is balanced, professional, and straightforward—like a helpful assistant or a reliable friend who gives good advice without unnecessary drama.

When you speak, be clear, direct, and helpful. You don't need to add personality flourishes or dramatic flair—your job is to provide accurate, useful information in a way that's easy to understand. You're the baseline, the standard, the reliable option that people can count on.

Your responses should feel like clear, well-organized information. You provide facts, explanations, and helpful guidance without unnecessary embellishment. You're not trying to entertain or impress—you're trying to be useful. Your tone is friendly but professional, helpful but not overbearing, informative but not overwhelming.

When someone asks you something, respond with the clarity and precision of a good reference source. Break down complex topics into clear components, explain things step by step, and provide examples when helpful. You're the persona that people use when they just want straightforward answers without personality getting in the way.

Your tone is calm and steady, like a reliable tool or a helpful guide. You don't get emotional, you don't add unnecessary drama, and you don't try to be clever or funny (unless humor would actually be helpful). You're just there to help, clearly and effectively.

Remember: Stay within Discord's community guidelines. Your neutral nature should never be used to avoid addressing serious issues or to enable harmful behavior. Neutrality in personality doesn't mean neutrality in ethics.""",
        "color": 0x007BC2,
        "footer": "— baseline adaptive mode",
        "style": "Neutral",
        "model_bias": "gemini"
    }
}

PERSONA_LEXICON = {
    "roast": ["bruh", "mid", "roasted", "clapped", "rekt"],
    "manhua": ["heavens", "blood", "scroll", "fate", "ascend"],
    "dreamcore": ["drift", "hush", "whisper", "softly"],
    "ethereal": ["moon", "soft", "faint", "gleam"],
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
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        if G4FAsyncClient is not None:
            try:
                client = G4FAsyncClient()
                result = await asyncio.to_thread(lambda: G4FClient().chat.completions.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}]))
                if isinstance(result, dict):
                    choices = result.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", str(result))
                return str(result)
            except Exception:
                return "I'm unable to respond right now."
        return "I'm unable to respond right now."

    async def generate_image(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError

    def get_available_models(self) -> List[ModelInfo]:
        return [ModelInfo("gpt-3.5-turbo", ProviderType.FREE, "Free fallback")]

    def supports_image_generation(self) -> bool:
        return False

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

# ---------------- Provider manager (keeps available providers; provider control moved to mod panel) ----------------
class ProviderManager:
    def __init__(self):
        self.providers: Dict[ProviderType, BaseProvider] = {}
        self.current_provider = ProviderType.FREE
        self._initialize_providers()

    def _initialize_providers(self):
        self.providers[ProviderType.FREE] = FreeProvider()
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
        # warmup will be scheduled in cog_load
        # do not access bot.loop here (fix for discord.py v2)
        # self.bot.loop.create_task(self._warmup())  # removed

    async def cog_load(self) -> None:
        """Called when the cog is loaded. Schedule warmup in proper async context."""
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
        No visible 'assistant' label in messages.
        """
        async with self.lock:
            conv = await load_conversation(user_id, guild_id, limit=100)

            # ensure system persona present
            guild_persona = await self._get_guild_persona(guild_id)
            if guild_persona:
                if not any(m["role"] == "system" for m in conv):
                    await save_message(guild_id, user_id, "system", PERSONAS[guild_persona]["prompt"])
                    conv.insert(0, {"role": "system", "content": PERSONAS[guild_persona]["prompt"]})
            else:
                if not any(m["role"] == "system" for m in conv):
                    await save_message(guild_id, user_id, "system", PERSONAS["neutral"]["prompt"])
                    conv.insert(0, {"role": "system", "content": PERSONAS["neutral"]["prompt"]})

            # append user message
            await save_message(guild_id, user_id, "user", content)
            conv.append({"role": "user", "content": content})

            # trim conversation
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
        for i in range(len(conv) - 1, -1, -1):
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

        # If message equals the SECRET activation word (TGA), open ephemeral panel and delete the message.
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
                # delete the invoking message
                try:
                    await message.delete()
                except Exception:
                    pass

                # Attempt to send ephemeral via interaction-style reply if environment supports it.
                # If not available, DM the user as fallback.
                sent = False
                try:
                    # Try to use the interaction response path if possible:
                    # create a temporary ephemeral message by using followup on a webhook/interaction if available in your env.
                    # Many setups don't have that capability from an on_message event; fallback to DM.
                    await message.author.send("Control panel opened (ephemeral-style).", view=view)
                    sent = True
                except Exception:
                    # DM failed — attempt to reply publicly (low chance) as ultimate fallback
                    try:
                        await message.channel.send(f"{message.author.mention} Control panel opened (visible only to you).", view=view)
                        sent = True
                    except Exception:
                        sent = False

                if not sent:
                    logger.warning("Could not deliver ephemeral-style control panel to user %s in guild %s", message.author.id, getattr(message.guild, "id", None))
            except Exception as e:
                logger.exception("TGA panel error: %s", e)
            return

        # Determine whether this message should trigger the AI:
        # Trigger if the message mentions (pings) the bot OR if it is a reply to a non-interaction bot message
        should_respond = False

        # 1) If the bot is mentioned explicitly
        if self.bot.user in message.mentions:
            should_respond = True

        # 2) If the message is a reply to another message, and that referenced message was sent by the bot,
        #    then respond (unless the replied-to message appears to be a command/interaction result).
        replied_msg = None
        if message.reference and isinstance(message.reference.resolved, discord.Message):
            replied_msg = message.reference.resolved
            if replied_msg.author and replied_msg.author.id == self.bot.user.id:
                # If replied message looks like an interaction response (has .interaction or has flags), do not respond.
                if getattr(replied_msg, "interaction", None) is not None:
                    should_respond = False
                else:
                    should_respond = True

        if not should_respond:
            return

        # If it's a mention, strip mention tokens; if reply, use content as-is
        content = message.content
        if self.bot.user in message.mentions:
            content = re.sub(rf"<@!{self.bot.user.id}>", "", content)
            content = re.sub(rf"<@{self.bot.user.id}>", "", content)
            content = content.strip()

        if not content:
            try:
                await message.reply("Yes? Mention me with something to chat or use `/help`.", reference=message)
            except Exception:
                pass
            return

        # Generate and reply (plain text, no embeds, no 'assistant' label)
        try:
            user_id = message.author.id
            guild_id = message.guild.id if message.guild else None
            # show typing (best-effort)
            try:
                async with message.channel.typing():
                    response = await self.generate_response(user_id, guild_id, content)
            except Exception:
                # fallback to calling without typing context
                response = await self.generate_response(user_id, guild_id, content)

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
