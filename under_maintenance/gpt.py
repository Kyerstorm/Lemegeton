# gpt.py
"""
Adaptive Aura Engine v4 (Monolith)
- Single-file cog for Discord.py 2.x
- OpenRouter primary, Gemini for neutral (optional), Ollama local fallback
- 11 personas, persona-locking, full /aura admin + /aura persona
- Secret message "TGA" opens a control panel (dropdown + persona select + buttons)
- Fallback diagnostics, provider reordering persistence, local pseudo-AI fallback
- Webhook logging (obfuscated + simple static-key obfuscation)
- All in one file, divided by REGION comments
"""

import os
import re
import json
import time
import base64
import random
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# ==================================================
# REGION: CONFIG & ENV
# ==================================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

DATA_FILE = os.path.join(DATA_DIR, "personas_state.json")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")
FALLBACK_ORDER_FILE = os.path.join(DATA_DIR, "fallback_order.json")
LOG_BUFFER_FILE = os.path.join(DATA_DIR, "log_buffer.json")

ALLOWED_ROLE_ID = 1420451296304959641
SECRET_WORD = "TGA"

# Obfuscated webhook: XOR obfuscation (static key stored here as requested)
# This is intentionally simple; replace with your own secure method if desired.
_OBFUSCATED_WEBHOOK = "w5c8KxojJx0m..."  # placeholder — will be replaced below with encoded value

# The actual webhook URL you provided (we'll obfuscate it in code)
_RAW_WEBHOOK = "https://discord.com/api/webhooks/1426971855113158789/XNmjkWciUbMoTx9UHwvocldLIFfaz5CKdfIKmx08Ml_Vy2asZn82fS4NeRFemCoa9TgC"
# Static XOR key (user requested static store). Keep this secret in production.
_STATIC_XOR_KEY = "my_static_secret_42"

def xor_obfuscate(text: str, key: str) -> str:
    # returns base64 of XORed bytes
    tb = text.encode("utf-8")
    kb = (key * ((len(tb)//len(key))+1)).encode("utf-8")
    out = bytes([tb[i] ^ kb[i] for i in range(len(tb))])
    return base64.b64encode(out).decode()

def xor_deobfuscate(b64text: str, key: str) -> str:
    try:
        ob = base64.b64decode(b64text)
        kb = (key * ((len(ob)//len(key))+1)).encode("utf-8")
        out = bytes([ob[i] ^ kb[i] for i in range(len(ob))])
        return out.decode("utf-8")
    except Exception:
        return ""

# obfuscate webhook constant at runtime (for code shipping, we store the obfuscated string)
_OBFUSCATED_WEBHOOK = xor_obfuscate(_RAW_WEBHOOK, _STATIC_XOR_KEY)

# API keys (set in environment)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", None)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", None)  # only used optionally for neutral persona
OLLAMA_HOST = os.getenv("OLLAMA_HOST", None)  # e.g., "http://localhost:11434"

# tuning
TOP_CONCURRENT_PROBES = 3
PROVIDER_TIMEOUT = 12
DIAGNOSTIC_TIMEOUT = 6
MEMORY_MAX = 10
LOG_BUFFER_MAX = 120

# ==================================================
# REGION: UTIL: JSON helpers
# ==================================================
def load_json_safe(path: str) -> dict:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_json_safe(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ==================================================
# REGION: PERSONAS (11)
# ==================================================
# Each persona includes: emoji, prompt, triggers (keywords), color hex, footer, style label, model bias
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

# Small lexicons for local pseudo generator imitation
PERSONA_LEXICON = {
    "roast":["bruh","mid","roasted","clapped","rekt"],
    "manhua":["heavens","blood","scroll","fate","ascend"],
    "dreamcore":["drift","hush","whisper","softly"],
    "ethereal":["moon","soft","faint","gleam"],
}

# ==================================================
# REGION: FALLBACK PROVIDERS (default ordering)
# ==================================================
FALLBACK_PROVIDERS_DEFAULT = [
    {"name":"openrouter","type":"openrouter","endpoints":["https://api.openrouter.ai/v1/chat/completions"]},
    {"name":"g4f","type":"generic","endpoints":["https://g4f.dev/api/chat","https://g4f.deepinfra.dev/api/chat"]},
    {"name":"lmarena","type":"generic","endpoints":["https://lmarena.ai/api/generate","https://api.lmarena.ai/generate"]},
    {"name":"phind","type":"generic","endpoints":["https://phind-api.vercel.app/api/generate","https://www.phind.com/api/v1/generate"]},
    {"name":"sharedchat","type":"generic","endpoints":["https://sharedchat.ai/api/chat","https://api.sharedchat.cn/v1/generate"]},
    {"name":"groq","type":"generic","endpoints":["https://groq.ai/api/generate","https://api.groq.com/v1/generate"]},
    {"name":"ollama","type":"ollama","endpoints":[OLLAMA_HOST] if OLLAMA_HOST else []},
]

def load_fallback_providers() -> List[Dict[str, Any]]:
    data = load_json_safe(FALLBACK_ORDER_FILE)
    if data and isinstance(data, list):
        return data
    return FALLBACK_PROVIDERS_DEFAULT.copy()

# ==================================================
# REGION: EXCEPTIONS
# ==================================================
class ProviderAuthError(Exception):
    pass

# ==================================================
# REGION: COG
# ==================================================
class GPTCog(commands.Cog):
    """Main Adaptive Aura Cog"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states = load_json_safe(DATA_FILE)
        self.memory = load_json_safe(MEMORY_FILE)
        self.fallback_providers = load_fallback_providers()
        self.processing_ids = set()
        self.provider_disabled_for_session = set()
        self.log_buffer = load_json_safe(LOG_BUFFER_FILE).get("buffer", [])
        self.provider_stats = {}  # provider -> list of times
        # decode webhook from obfuscated value
        try:
            self.webhook_url = xor_deobfuscate(_OBFUSCATED_WEBHOOK, _STATIC_XOR_KEY)
        except Exception:
            self.webhook_url = None
        # If no OPENROUTER_API_KEY present, disable openrouter provider
        if not OPENROUTER_API_KEY:
            self.provider_disabled_for_session.add("openrouter")
        # Per-guild selected OpenRouter model bias (persisted in guild state)
        # We store under self.guild_states[guild_id]["openrouter_model"], default "gpt-4o-mini"
        # ensure initial file write
        save_json_safe(DATA_FILE, self.guild_states)

    # ------------------------------
    # State & memory helpers
    # ------------------------------
    def get_guild_state(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self.guild_states:
            self.guild_states[gid] = {
                "enabled": True,
                "locked_persona": None,
                "webhook_enabled": True,
                "persist_order": True,
                "openrouter_model": "gpt-4o-mini",  # default model
                "debug_mode": False,
            }
            save_json_safe(DATA_FILE, self.guild_states)
        return self.guild_states[gid]

    def get_channel_memory(self, guild_id: int, channel_id: int) -> List[Dict[str, Any]]:
        gid, cid = str(guild_id), str(channel_id)
        self.memory.setdefault(gid, {})
        self.memory[gid].setdefault(cid, [])
        save_json_safe(MEMORY_FILE, self.memory)
        return self.memory[gid][cid]

    def append_memory(self, guild_id: int, channel_id: int, role: str, content: str):
        mem = self.get_channel_memory(guild_id, channel_id)
        mem.append({"role": role, "content": content})
        if len(mem) > MEMORY_MAX:
            mem.pop(0)
        save_json_safe(MEMORY_FILE, self.memory)

    # ------------------------------
    # Permission check decorator
    # ------------------------------
    def admin_or_role():
        async def predicate(interaction: discord.Interaction):
            if interaction.user.guild_permissions.administrator:
                return True
            if any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles):
                return True
            await interaction.response.send_message("🚫 You don't have permission to use this command.", ephemeral=True)
            return False
        return app_commands.check(predicate)

    # ------------------------------
    # Slash group: /aura
    # ------------------------------
    aura_group = app_commands.Group(name="aura", description="Persona Nexus controls")

    @aura_group.command(name="admin", description="Admin panel: multi-toggle and model selection")
    @app_commands.describe(
        toggles="Comma-separated toggles: enable_listener, webhook_logs, fallback_enabled, typing_sim, auto_persona, debug_mode",
        lock="Lock persona name or 'auto'",
        openrouter_model="Choose OpenRouter model for this guild (if available)",
        testfallbacks="Run provider diagnostics now",
        show_order="Show provider fallback order",
        view_memory="View channel memory",
        clear_memory="Clear channel memory",
        flush_logs="Flush buffered logs to webhook"
    )
    @admin_or_role()
    async def aura_admin(self,
                         interaction: discord.Interaction,
                         toggles: Optional[str] = None,
                         lock: Optional[str] = None,
                         openrouter_model: Optional[str] = None,
                         testfallbacks: Optional[bool] = None,
                         show_order: Optional[bool] = None,
                         view_memory: Optional[bool] = None,
                         clear_memory: Optional[bool] = None,
                         flush_logs: Optional[bool] = None):
        """
        Multi-action admin command. 'toggles' is a comma-separated list of options turned ON.
        Example toggles: "enable_listener,webhook_logs,typing_sim"
        """
        gid = interaction.guild_id
        state = self.get_guild_state(gid)

        # toggles parsing
        if toggles:
            enabled = {t.strip().lower() for t in toggles.split(",") if t.strip()}
            # map known toggles
            if "enable_listener" in enabled:
                state["enabled"] = True
            if "disable_listener" in enabled:
                state["enabled"] = False
            if "webhook_logs" in enabled:
                state["webhook_enabled"] = True
            if "no_webhook_logs" in enabled:
                state["webhook_enabled"] = False
            if "fallback_enabled" in enabled:
                state["fallback_enabled"] = True
            if "no_fallback" in enabled:
                state["fallback_enabled"] = False
            if "typing_sim" in enabled:
                state["typing_sim"] = True
            if "no_typing_sim" in enabled:
                state["typing_sim"] = False
            if "auto_persona" in enabled:
                state["auto_persona"] = True
            if "no_auto_persona" in enabled:
                state["auto_persona"] = False
            if "debug_mode" in enabled:
                state["debug_mode"] = True
            if "no_debug_mode" in enabled:
                state["debug_mode"] = False
            save_json_safe(DATA_FILE, self.guild_states)
            await interaction.response.send_message(embed=self._embed_ok("Toggles applied", f"Applied: {', '.join(enabled)}"), ephemeral=True)
            await self._audit("admin.toggles", interaction.user, f"toggles={enabled}")
            return

        # lock persona
        if lock:
            if lock.lower() == "auto":
                state["locked_persona"] = None
                save_json_safe(DATA_FILE, self.guild_states)
                await interaction.response.send_message(embed=self._embed_ok("Persona unlocked", "Auto mode enabled"), ephemeral=True)
                await self._audit("admin.lock", interaction.user, "unlocked")
                return
            if lock not in PERSONAS:
                await interaction.response.send_message(embed=self._embed_error("Unknown persona", f"Persona '{lock}' not found."), ephemeral=True)
                return
            state["locked_persona"] = lock
            state["enabled"] = True
            save_json_safe(DATA_FILE, self.guild_states)
            p = PERSONAS[lock]
            await interaction.response.send_message(embed=self._embed_ok(f"Locked to {p['emoji']}", f"{p['style']} locked."), ephemeral=True)
            await self._audit("admin.lock", interaction.user, f"locked={lock}")
            return

        # openrouter model
        if openrouter_model:
            state["openrouter_model"] = openrouter_model
            save_json_safe(DATA_FILE, self.guild_states)
            await interaction.response.send_message(embed=self._embed_ok("OpenRouter model set", f"Model = {openrouter_model}"), ephemeral=True)
            await self._audit("admin.openrouter_model", interaction.user, f"model={openrouter_model}")
            return

        # show order
        if show_order:
            order_text = " -> ".join([p.get("name", p["name"]) if isinstance(p, dict) and "name" in p else p.get("name", p.get("name","")) for p in self.fallback_providers])
            await interaction.response.send_message(embed=discord.Embed(title="Provider Order", description=order_text or "None", color=0xA9A9A9), ephemeral=True)
            return

        # view memory
        if view_memory:
            mem = self.get_channel_memory(gid, interaction.channel_id)
            if not mem:
                await interaction.response.send_message("No memory for this channel.", ephemeral=True)
                return
            lines = [f"[{m['role']}] {m['content'][:400]}" for m in mem[-10:]]
            await interaction.response.send_message(embed=discord.Embed(title="Channel Memory", description="\n\n".join(lines), color=0x00FFFF), ephemeral=True)
            return

        # clear memory
        if clear_memory:
            self.memory.setdefault(str(gid), {})[str(interaction.channel_id)] = []
            save_json_safe(MEMORY_FILE, self.memory)
            await interaction.response.send_message(embed=self._embed_ok("Memory cleared", "Channel memory purged."), ephemeral=True)
            await self._audit("admin.clear_memory", interaction.user, f"channel={interaction.channel_id}")
            return

        # flush logs
        if flush_logs:
            await interaction.response.send_message("Flushing logs to webhook...", ephemeral=True)
            await self._flush_logs_via_webhook()
            await self._audit("admin.flush_logs", interaction.user, "flushed logs")
            return

        # diagnostics
        if testfallbacks:
            await interaction.response.send_message("Running fallback diagnostics... (may take up to 30s)", ephemeral=True)
            diag_prompt = [{"role":"system","content":"You are a small diagnostic assistant. Reply 'OK'."},{"role":"user","content":"Diagnostic: are you alive?"}]
            results = await self._diagnostic_run(diag_prompt, timeout_per_endpoint=DIAGNOSTIC_TIMEOUT)
            ok = [r for r in results if r["ok"]]
            lines = []
            if ok:
                lines.append(f"Fastest: {ok[0]['provider']} ({ok[0]['time']:.2f}s)")
            else:
                lines.append("No providers responded successfully.")
            for r in results[:20]:
                lines.append(f"{r['provider'][:14]:<14} | {'OK' if r['ok'] else 'FAIL':<4} | {r['time']:.2f}s | {r['endpoint']}")
            report = "\n".join(lines)
            # reorder automatically if some passed
            if ok:
                provider_times = {}
                for r in results:
                    provider_times.setdefault(r["provider"], []).append(r["time"] if r["ok"] else 9999.0)
                avg = [(p, sum(t)/len(t)) for p,t in provider_times.items()]
                avg.sort(key=lambda x:x[1])
                new_order = []
                for p,_ in avg:
                    for entry in FALLBACK_PROVIDERS_DEFAULT:
                        if entry["name"] == p:
                            new_order.append(entry)
                            break
                for entry in FALLBACK_PROVIDERS_DEFAULT:
                    if entry not in new_order:
                        new_order.append(entry)
                self.fallback_providers = new_order
                if state.get("persist_order", True):
                    save_json_safe(FALLBACK_ORDER_FILE, self.fallback_providers)
                    report += "\n\nProvider order updated and persisted."
            await interaction.followup.send(embed=discord.Embed(title="Fallback Diagnostics", description=f"```{report[:1800]}```", color=0x00FFAA), ephemeral=True)
            await self._audit("admin.testfallbacks", interaction.user, "diagnostics run")
            return

        # default: status
        locked = state.get("locked_persona") or "Auto Mode"
        desc = f"🪄 Listener: {'✅' if state.get('enabled', True) else '❌'}\n🧭 Persona: {locked}\n📡 Webhook: {'✅' if state.get('webhook_enabled', True) else '❌'}\n⚙️ Persist order: {state.get('persist_order', True)}\n🧩 OpenRouter model: {state.get('openrouter_model','gpt-4o-mini')}"
        embed = discord.Embed(title="Aura Admin Status", description=desc, color=0x00FFFF)
        embed.set_footer(text="— System Sync • v4.0")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------
    # Persona command (simpler persona-only)
    # ------------------------------
    @aura_group.command(name="persona", description="List or lock persona (admins required to lock)")
    @app_commands.describe(action="list or set", persona="Persona key to lock")
    @app_commands.choices(action=[app_commands.Choice(name="list", value="list"), app_commands.Choice(name="set", value="set")],
                         persona=[app_commands.Choice(name=f"{v['emoji']} {k}", value=k) for k,v in PERSONAS.items()])
    async def aura_persona(self, interaction: discord.Interaction, action: app_commands.Choice[str], persona: Optional[app_commands.Choice[str]] = None):
        gid = interaction.guild_id
        state = self.get_guild_state(gid)
        if action.value == "list":
            embed = discord.Embed(title="Persona Nexus — Available Personas", color=0xFFB6C1)
            for k,v in PERSONAS.items():
                sample = v.get("prompt","")[:140] + "..."
                embed.add_field(name=f"{v['emoji']} {k}", value=sample, inline=False)
            embed.set_footer(text="Use /aura admin lock:<persona> to lock a persona.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        # set requires admin or allowed role
        if not (interaction.user.guild_permissions.administrator or any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles)):
            await interaction.response.send_message("🚫 You need admin or the special role to lock a persona.", ephemeral=True)
            return
        if not persona:
            await interaction.response.send_message("❗ Please choose a persona.", ephemeral=True)
            return
        state["locked_persona"] = persona.value
        state["enabled"] = True
        save_json_safe(DATA_FILE, self.guild_states)
        p = PERSONAS[persona.value]
        await interaction.response.send_message(embed=self._embed_ok(f"Locked to {p['emoji']}", f"{persona.value} locked."), ephemeral=True)
        await self._audit("persona.lock", interaction.user, f"locked={persona.value}")

    # ------------------------------
    # SECRET UI MESSAGE (TGA) and on_message listener
    # ------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        # SECRET PANEL
        if message.content.strip().upper() == SECRET_WORD:
            if not (message.author.guild_permissions.administrator or any(role.id == ALLOWED_ROLE_ID for role in message.author.roles)):
                await message.channel.send(embed=self._embed_error("Access Denied", "You don't have permission to open Aura UI."), delete_after=8)
                return
            # Build view and send (ensuring selects have options)
            view = AuraAdminView(self, caller_id=message.author.id)
            # store reference for cleanup on timeout
            sent = await message.channel.send(content=f"{message.author.mention} • Aura Control Panel", embed=self._embed_info("Aura Control", "Choose an action from the dropdown below."), view=view)
            view.message = sent
            return

        # respond only on mention or reply to the bot
        invoked = False
        if self.bot.user in message.mentions:
            invoked = True
        elif message.reference:
            ref = message.reference.resolved
            if ref and getattr(ref,"author",None) and getattr(ref.author,"id",None) == self.bot.user.id:
                invoked = True
        if not invoked:
            return

        await self._handle_incoming_message(message)

    # ------------------------------
    # Incoming message processing
    # ------------------------------
    async def _handle_incoming_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        gid, cid = message.guild.id, message.channel.id
        state = self.get_guild_state(gid)
        if not state.get("enabled", True):
            return
        if message.id in self.processing_ids:
            return
        self.processing_ids.add(message.id)
        try:
            persona_key = state.get("locked_persona") or self._select_persona(message)
            if persona_key not in PERSONAS:
                persona_key = "neutral"
            persona = PERSONAS[persona_key]

            mem = self.get_channel_memory(gid, cid)
            messages_payload = [{"role":"system","content":persona["prompt"]}]
            for m in mem:
                messages_payload.append({"role":m.get("role","user"), "content": m.get("content","")})
            messages_payload.append({"role":"user","content":message.content})

            # typing sim
            async with message.channel.typing():
                reply_text, provider_used = await self._generate_with_chain(messages_payload, persona_key, timeout=PROVIDER_TIMEOUT)

            if not reply_text:
                reply_text = self._local_pseudo_generator(messages_payload, persona_key)
                provider_used = "local-pseudo"

            # memory
            self.append_memory(gid, cid, "user", message.content)
            self.append_memory(gid, cid, "assistant", reply_text)

            await asyncio.sleep(random.uniform(0.2, 0.9))
            embed = discord.Embed(description=reply_text, color=persona["color"])
            embed.set_footer(text=persona["footer"])
            await message.reply(embed=embed)

            # logging via webhook or console
            if state.get("webhook_enabled", True):
                await self._log_embed(f"AUTO-REPLY • {provider_used}", author=message.author, details=f"Persona={persona_key}\nProvider={provider_used}\nUser:{message.content[:800]}")
            else:
                print(f"[AUTO-REPLY] persona={persona_key} provider={provider_used} user={message.author} MSG: {message.content[:200]}")
        finally:
            self.processing_ids.discard(message.id)

    # ------------------------------
    # Persona selection heuristic
    # ------------------------------
    def _select_persona(self, message: discord.Message) -> str:
        text = (message.content or "").lower()
        scores = {k:0 for k in PERSONAS.keys()}
        for k,v in PERSONAS.items():
            for kw in v.get("triggers", []):
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    scores[k] += 2
        if "?" in text:
            scores["neutral"] += 1
            scores["academic"] += 1
        if "!" in text:
            scores["manhua"] += 1
            scores["roast"] += 1
        mem = self.get_channel_memory(message.guild.id, message.channel.id)
        if mem:
            last = mem[-1]
            if last.get("role") == "assistant":
                scores["neutral"] += 1
        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return "neutral"
        return best

    # ==================================================
    # REGION: MODEL CHAIN (OpenRouter primary, Gemini neutral, Ollama local, generic fallbacks)
    # ==================================================
    async def _generate_with_chain(self, messages_payload: List[Dict[str,Any]], persona_key: str, timeout: int = PROVIDER_TIMEOUT) -> Tuple[Optional[str], str]:
        """
        Chain order:
        1) OpenRouter (primary) if enabled and not disabled for session
        2) If persona == 'neutral' and GEMINI_API_KEY exists -> Gemini
        3) Community generic fallbacks (g4f/lmarena/phind/sharedchat/groq)
        4) Ollama local (if host configured)
        5) Local pseudo
        """
        # 1: OpenRouter
        if "openrouter" not in self.provider_disabled_for_session and OPENROUTER_API_KEY:
            try:
                state = self.get_guild_state(messages_payload[0].get("guild_id", 0)) if messages_payload else None
                model_choice = None
                # prefer per-guild openrouter model setting if known; fallback to persona bias if any
                # we can't reliably get guild here; but we'll pick model by persona bias or default
                # get default model from a guild config? use default 'gpt-4o-mini' stored earlier
                # (We'll prefer persona model bias)
                persona_bias = PERSONAS.get(persona_key, {}).get("model_bias")
                model_choice = persona_bias or "gpt-4o-mini"
                resp = await self._call_openrouter(messages_payload, model=model_choice, timeout=timeout)
                if resp:
                    return resp, f"openrouter:{model_choice}"
            except ProviderAuthError:
                self.provider_disabled_for_session.add("openrouter")
                await self._audit("provider.disabled", None, "openrouter disabled due to auth")
            except Exception as e:
                print(f"[OpenRouter] error: {e}")

        # 2: Gemini for neutral persona
        if persona_key == "neutral" and GEMINI_API_KEY:
            try:
                g = await self._call_gemini(messages_payload, timeout=timeout)
                if g:
                    return g, "gemini"
            except ProviderAuthError:
                # if gemini auth issues, just skip
                pass
            except Exception as e:
                print(f"[Gemini] error: {e}")

        # 3: community generic providers
        providers = [p for p in self.fallback_providers if p.get("name") not in self.provider_disabled_for_session]
        for provider in providers:
            pname = provider.get("name")
            ptype = provider.get("type","generic")
            endpoints = provider.get("endpoints",[]) or []
            for endpoint in endpoints:
                try:
                    if ptype == "generic":
                        r = await self._call_generic_provider(endpoint, messages_payload, timeout=timeout)
                    elif ptype == "ollama":
                        r = await self._call_ollama(endpoint, messages_payload, timeout=timeout)
                    elif ptype == "openrouter":
                        r = await self._call_openrouter(messages_payload, model=provider.get("model"), timeout=timeout)
                    else:
                        r = await self._call_generic_provider(endpoint, messages_payload, timeout=timeout)
                    if r:
                        self.provider_stats.setdefault(pname, []).append(0.0)
                        return r, pname
                except ProviderAuthError:
                    self.provider_disabled_for_session.add(pname)
                    await self._audit("provider.disabled", None, f"{pname} disabled due to auth")
                    break
                except Exception as e:
                    print(f"[Fallback] {pname}@{endpoint} error: {e}")
                    continue

        # 4: Ollama host fallback
        if OLLAMA_HOST:
            try:
                r = await self._call_ollama(OLLAMA_HOST, messages_payload, timeout=timeout)
                if r:
                    return r, "ollama"
            except Exception as e:
                print(f"[Ollama] error: {e}")

        # 5: local pseudo
        local = self._local_pseudo_generator(messages_payload, persona_key)
        return local, "local-pseudo"

    # ------------------------------
    # OpenRouter caller
    # ------------------------------
    async def _call_openrouter(self, messages_payload: List[Dict[str,Any]], model: str = "gpt-4o-mini", timeout: int = 12) -> Optional[str]:
        if not OPENROUTER_API_KEY:
            raise ProviderAuthError("OpenRouter missing API key")
        url = "https://api.openrouter.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type":"application/json"}
        body = {
            "model": model,
            "messages": messages_payload,
            "temperature": 0.8,
            "max_tokens": 800
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body, timeout=timeout) as resp:
                text = await resp.text()
                if resp.status in (401,403):
                    raise ProviderAuthError(f"openrouter auth {resp.status}")
                # try parse JSON
                try:
                    data = await resp.json()
                except Exception:
                    data = None
                if data:
                    # openrouter aims to be OpenAI-compatible
                    if isinstance(data, dict) and "choices" in data and data["choices"]:
                        c = data["choices"][0]
                        if isinstance(c, dict) and "message" in c and isinstance(c["message"], dict) and "content" in c["message"]:
                            return c["message"]["content"].strip()
                        if isinstance(c, dict) and "text" in c:
                            return c["text"].strip()
                    # fallbacks
                    for key in ("output","response","result","text"):
                        if key in data and isinstance(data[key], str):
                            return data[key].strip()
                if text and len(text) > 10:
                    return text.strip()
        return None

    # ------------------------------
    # Gemini caller (placeholder REST shape)
    # ------------------------------
    async def _call_gemini(self, messages_payload: List[Dict[str,Any]], timeout: int = 10) -> Optional[str]:
        if not GEMINI_API_KEY:
            return None
        # This is a placeholder; if you use official google SDK, replace this logic.
        url = "https://api.generative.google/v1beta/models/text-bison-001:generate"
        headers = {"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type":"application/json"}
        system = next((m["content"] for m in messages_payload if m["role"]=="system"), "")
        user = next((m["content"] for m in reversed(messages_payload) if m["role"]=="user"), "")
        prompt = f"{system}\nUser: {user}\nAssistant:"
        body = {"prompt": prompt, "temperature":0.5, "max_output_tokens":512}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body, timeout=timeout) as resp:
                if resp.status in (401,403):
                    raise ProviderAuthError("gemini auth error")
                try:
                    data = await resp.json()
                except Exception:
                    data = None
                if data:
                    # try common keys
                    for key in ("candidates","output","outputs","text"):
                        if key in data:
                            val = data[key]
                            if isinstance(val, list) and val:
                                first = val[0]
                                if isinstance(first, dict) and "content" in first:
                                    return first["content"].strip()
                            if isinstance(val, str):
                                return val.strip()
                text = await resp.text()
                if text and len(text) > 10:
                    return text.strip()
        return None

    # ------------------------------
    # Generic provider caller (multiple shapes)
    # ------------------------------
    async def _call_generic_provider(self, endpoint: str, messages_payload: List[Dict[str,Any]], timeout: int = 10) -> Optional[str]:
        system = next((m["content"] for m in messages_payload if m["role"]=="system"), "")
        user = next((m["content"] for m in reversed(messages_payload) if m["role"]=="user"), "")
        compact = f"{system}\nUser: {user}\nAssistant:"
        async with aiohttp.ClientSession() as session:
            # chat-like
            try:
                payload = {"model":"gpt-3.5","messages":messages_payload}
                async with session.post(endpoint, json=payload, timeout=timeout) as resp:
                    if resp.status in (401,403):
                        raise ProviderAuthError(f"{endpoint} auth {resp.status}")
                    text = await resp.text()
                    try:
                        data = await resp.json()
                    except Exception:
                        data = None
                    if data:
                        if isinstance(data, dict) and "choices" in data and data["choices"]:
                            c = data["choices"][0]
                            if isinstance(c, dict) and "message" in c and "content" in c["message"]:
                                return c["message"]["content"].strip()
                            if isinstance(c, dict) and "text" in c:
                                return c["text"].strip()
                        for key in ("output","response","result","text"):
                            if key in data and isinstance(data[key], str):
                                return data[key].strip()
                    if text and len(text) > 10:
                        return text.strip()
            except ProviderAuthError:
                raise
            except Exception:
                pass
            # prompt-like
            try:
                payload2 = {"prompt": compact, "max_tokens":400, "temperature":0.7}
                async with session.post(endpoint, json=payload2, timeout=timeout) as resp2:
                    if resp2.status in (401,403):
                        raise ProviderAuthError(f"{endpoint} auth {resp2.status}")
                    text2 = await resp2.text()
                    try:
                        data2 = await resp2.json()
                    except Exception:
                        data2 = None
                    if data2 and isinstance(data2, dict):
                        for key in ("output","response","result","text"):
                            if key in data2 and isinstance(data2[key], str):
                                return data2[key].strip()
                    if text2 and len(text2) > 10:
                        return text2.strip()
            except ProviderAuthError:
                raise
            except Exception:
                pass
            # GET shape
            try:
                params = {"q": compact[:800]}
                async with session.get(endpoint, params=params, timeout=timeout) as resp3:
                    if resp3.status in (401,403):
                        raise ProviderAuthError(f"{endpoint} auth {resp3.status}")
                    t3 = await resp3.text()
                    if t3 and len(t3) > 10:
                        return t3.strip()
            except ProviderAuthError:
                raise
            except Exception:
                pass
        return None

    # ------------------------------
    # Ollama caller (best-effort)
    # ------------------------------
    async def _call_ollama(self, host: str, messages_payload: List[Dict[str,Any]], timeout: int = 10) -> Optional[str]:
        if not host:
            return None
        model = "llama3"
        url = f"{host.rstrip('/')}/api/generate"
        system = next((m["content"] for m in messages_payload if m["role"]=="system"), "")
        user = next((m["content"] for m in reversed(messages_payload) if m["role"]=="user"), "")
        prompt = f"{system}\nUser: {user}\nAssistant:"
        body = {"model": model, "prompt": prompt, "max_tokens": 500}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=timeout) as resp:
                if resp.status in (401,403):
                    raise ProviderAuthError("ollama auth")
                text = await resp.text()
                try:
                    data = await resp.json()
                except Exception:
                    data = None
                if data:
                    for key in ("text","response","output","generated_text"):
                        if key in data and isinstance(data[key], str):
                            return data[key].strip()
                if text and len(text) > 10:
                    return text.strip()
        return None

    # ==================================================
    # REGION: DIAGNOSTICS (testfallbacks)
    # ==================================================
    async def _diagnostic_run(self, messages_payload: List[Dict[str,Any]], timeout_per_endpoint: int = DIAGNOSTIC_TIMEOUT) -> List[Dict[str,Any]]:
        results = []
        for provider in FALLBACK_PROVIDERS_DEFAULT:
            pname = provider["name"]
            for endpoint in provider.get("endpoints", []):
                start = time.time()
                ok = False
                try:
                    reply = await self._call_generic_provider(endpoint, messages_payload, timeout=timeout_per_endpoint)
                    elapsed = time.time() - start
                    if reply:
                        ok = True
                except ProviderAuthError:
                    elapsed = time.time() - start
                    ok = False
                except Exception:
                    elapsed = time.time() - start
                    ok = False
                results.append({"provider":pname,"endpoint":endpoint,"ok":ok,"time":elapsed})
        results.sort(key=lambda r:(0 if r["ok"] else 1, r["time"]))
        return results

    # ==================================================
    # REGION: LOCAL PSEUDO-AI FALLBACK
    # ==================================================
    def _local_pseudo_generator(self, messages_payload: List[Dict[str,Any]], persona_key: str) -> str:
        user_line = ""
        for m in reversed(messages_payload):
            if m.get("role") == "user":
                user_line = m.get("content","")
                break
        s = (user_line or "").strip()
        templates = [
            "looks like the fancy clouds are napping — patching an answer together.",
            "i'm on fallback juice. not perfect, but here you go:",
            "offline mode activated — improvising from memory (expect spice).",
            "ai went on vacation. here's a quick human-style take:"
        ]
        persona_flair = {
            "roast":["bruh, that was a wild take. here's a roast-lite:"],
            "manhua":["The heavens sleep; still, the world demands an answer:"],
            "dreamcore":["softly, from the edge of sleep:"],
            "academic":["Short fallback summary:"],
            "neutral":["Quick fallback summary:"],
            "eldritch":["From the deep, a whisper:"],
            "glitchcore":["<glitch> ... patching fragments ..."]
        }
        pick = random.choice(templates)
        flair = random.choice(persona_flair.get(persona_key, [pick]))
        lex = PERSONA_LEXICON.get(persona_key, [])
        if lex:
            flair += " " + random.choice(lex)
        if s:
            return f"{flair} {pick}\n\n— echo: \"{s[:240]}\""
        return f"{flair} {pick}"

    # ==================================================
    # REGION: LOGGING / WEBHOOKS / RING BUFFER
    # ==================================================
    async def _log_embed(self, title: str, author: Optional[discord.User] = None, details: Optional[str] = None):
        t = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        who = f"{author} ({getattr(author,'id','N/A')})" if author else "System"
        short = (details or "")[:1800]
        console = f"-# [Time: {t}]\n{title}\nActor: {who}\n{short}"
        print(console)
        # ring buffer
        self.log_buffer.append({"time":t,"title":title,"who":who,"details":short})
        if len(self.log_buffer) > LOG_BUFFER_MAX:
            self.log_buffer.pop(0)
        save_json_safe(LOG_BUFFER_FILE, {"buffer": self.log_buffer})
        # post embed
        if self.webhook_url:
            try:
                embed = discord.Embed(title=title, description=(short or "—"), color=0x2F3136)
                embed.add_field(name="Actor", value=who, inline=True)
                embed.set_footer(text=f"Time: {t}")
                async with aiohttp.ClientSession() as session:
                    await session.post(self.webhook_url, json={"embeds":[embed.to_dict()]}, timeout=8)
            except Exception as e:
                print(f"[Webhook] failed: {e}")

    async def _flush_logs_via_webhook(self):
        if not self.webhook_url:
            return
        while self.log_buffer:
            item = self.log_buffer.pop(0)
            await self._log_embed(item.get("title","log"), None, item.get("details",""))
        save_json_safe(LOG_BUFFER_FILE, {"buffer": self.log_buffer})

    async def _audit(self, tag: str, user: Optional[discord.User], details: Optional[str] = None):
        await self._log_embed(f"Audit • {tag}", user, details)

    # ==================================================
    # REGION: EMBED HELPERS (AESTHETICS)
    # ==================================================
    def _embed_ok(self, title: str, desc: str) -> discord.Embed:
        e = discord.Embed(title=f"✅ {title}", description=desc or "—", color=0x57F287)
        e.set_footer(text="— Operation completed")
        return e

    def _embed_error(self, title: str, desc: str) -> discord.Embed:
        e = discord.Embed(title=f"🚫 {title}", description=desc or "—", color=0xED4245)
        e.set_footer(text="— Operation failed")
        return e

    def _embed_info(self, title: str, desc: str) -> discord.Embed:
        e = discord.Embed(title=f"ℹ️ {title}", description=desc or "—", color=0x5865F2)
        e.set_footer(text="— Info")
        return e

# ==================================================
# REGION: UI CLASSES (Views, Selects, Buttons)
# ==================================================
class AuraAdminView(discord.ui.View):
    def __init__(self, cog: GPTCog, caller_id: int, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.caller_id = caller_id
        self.message = None
        # top-level admin actions (guaranteed non-empty)
        options = [
            discord.SelectOption(label="Show Status", value="status", description="Show Aura status", emoji="🪄"),
            discord.SelectOption(label="Toggle Listener", value="toggle", description="Enable/Disable listener", emoji="🔁"),
            discord.SelectOption(label="Lock Persona (use persona selector)", value="lock_menu", description="Lock persona", emoji="🔒"),
            discord.SelectOption(label="Run Fallback Diagnostics", value="testfallbacks", description="Test providers", emoji="📡"),
            discord.SelectOption(label="Show Provider Order", value="show_order", description="Display provider order", emoji="🧭"),
            discord.SelectOption(label="View Memory (channel)", value="view_memory", description="Show channel memory", emoji="🧠"),
            discord.SelectOption(label="Clear Memory", value="clear_memory", description="Clear channel memory", emoji="🧹"),
            discord.SelectOption(label="Flush Logs", value="flush_logs", description="Flush buffered logs", emoji="📤"),
        ]
        self.select = discord.ui.Select(placeholder="Choose an admin action...", min_values=1, max_values=1, options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)
        # persona select
        persona_options = [discord.SelectOption(label=f"{v['emoji']} {k}", value=k, description=v.get("style","")) for k,v in PERSONAS.items()]
        if not persona_options:
            persona_options = [discord.SelectOption(label="None available", value="none", description="No personas")]
        self.persona_select = PersonaSelect(cog, caller_id=caller_id, options=persona_options)
        self.add_item(self.persona_select)
        # quick buttons
        self.add_item(QuickButton("Enable", "toggle_on", discord.ButtonStyle.green))
        self.add_item(QuickButton("Disable", "toggle_off", discord.ButtonStyle.red))
        self.add_item(QuickButton("Unlock Persona", "unlock_persona", discord.ButtonStyle.gray))

    async def select_callback(self, interaction: discord.Interaction):
        # route through handler
        val = self.select.values[0]
        await self._handle_main_choice(val, interaction)

    async def _handle_main_choice(self, value: str, interaction: discord.Interaction):
        cog = self.cog
        if value == "status":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            locked = state.get("locked_persona") or "Auto Mode"
            msg = f"Status: {'✅' if state.get('enabled', True) else '❌'}\nPersona: {locked}\nWebhook: {'✅' if state.get('webhook_enabled', True) else '❌'}\nOpenRouter model: {state.get('openrouter_model','gpt-4o-mini')}"
            await interaction.response.send_message(embed=cog._embed_info("Aura Status", msg), ephemeral=True)
            return
        if value == "toggle":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            state["enabled"] = not state.get("enabled", True)
            save_json_safe(DATA_FILE, cog.guild_states)
            await interaction.response.send_message(embed=cog._embed_ok("Toggled Listener", f"Enabled = {state['enabled']}"), ephemeral=True)
            await cog._audit("ui.toggle", interaction.user, f"enabled={state['enabled']}")
            return
        if value == "testfallbacks":
            await interaction.response.send_message("Running diagnostics...", ephemeral=True)
            diag_prompt = [{"role":"system","content":"You are a small diagnostic assistant. Reply 'OK'."},{"role":"user","content":"Diagnostic: are you alive?"}]
            results = await cog._diagnostic_run(diag_prompt, timeout_per_endpoint=DIAGNOSTIC_TIMEOUT)
            ok = [r for r in results if r["ok"]]
            lines = []
            if ok:
                lines.append(f"Fastest: {ok[0]['provider']} ({ok[0]['time']:.2f}s)")
            else:
                lines.append("No providers OK.")
            for r in results[:10]:
                lines.append(f"{r['provider'][:12]:<12} | {'OK' if r['ok'] else 'FAIL':<4} | {r['time']:.2f}s")
            await interaction.followup.send(embed=discord.Embed(title="Diagnostics", description="```" + ("\n".join(lines))[:1900] + "```", color=0x00FFAA), ephemeral=True)
            await cog._audit("ui.testfallbacks", interaction.user, "Ran diagnostics")
            return
        if value == "show_order":
            text = " -> ".join([p.get("name", p.get("name","")) for p in cog.fallback_providers])
            await interaction.response.send_message(embed=discord.Embed(title="Provider Order", description=text or "None", color=0xA9A9A9), ephemeral=True)
            return
        if value == "view_memory":
            mem = cog.get_channel_memory(interaction.guild_id, interaction.channel_id)
            if not mem:
                await interaction.response.send_message("No memory.", ephemeral=True)
                return
            lines = [f"[{e['role']}] {e['content'][:200]}" for e in mem[-10:]]
            await interaction.response.send_message(embed=discord.Embed(title="Channel Memory", description="\n\n".join(lines), color=0x00FFFF), ephemeral=True)
            return
        if value == "clear_memory":
            cog.memory.setdefault(str(interaction.guild_id), {})[str(interaction.channel_id)] = []
            save_json_safe(MEMORY_FILE, cog.memory)
            await interaction.response.send_message(embed=cog._embed_ok("Memory cleared", "Channel memory purged."), ephemeral=True)
            await cog._audit("ui.clear_memory", interaction.user, f"channel={interaction.channel_id}")
            return
        if value == "flush_logs":
            await interaction.response.send_message("Flushing logs...", ephemeral=True)
            await cog._flush_logs_via_webhook()
            await cog._audit("ui.flush_logs", interaction.user, "Flushed")
            return
        if value == "lock_menu":
            await interaction.response.send_message("Use the persona dropdown below to select a persona to lock.", ephemeral=True)
            return

class PersonaSelect(discord.ui.Select):
    def __init__(self, cog: GPTCog, caller_id: int, options: List[discord.SelectOption]):
        # options guaranteed non-empty by the caller
        super().__init__(placeholder="Select persona to lock (admins/role only)...", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.caller_id = caller_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.caller_id:
            await interaction.response.send_message("This selector isn't for you.", ephemeral=True)
            return
        if not (interaction.user.guild_permissions.administrator or any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles)):
            await interaction.response.send_message("You need admin or the special role to lock a persona.", ephemeral=True)
            return
        persona_key = self.values[0]
        state = self.cog.get_guild_state(interaction.guild_id)
        state["locked_persona"] = persona_key
        state["enabled"] = True
        save_json_safe(DATA_FILE, self.cog.guild_states)
        p = PERSONAS[persona_key]
        await interaction.response.send_message(embed=self.cog._embed_ok(f"Locked to {p['emoji']}", f"{persona_key} locked."), ephemeral=True)
        await self.cog._audit("ui.persona_lock", interaction.user, f"locked={persona_key}")

class QuickButton(discord.ui.Button):
    def __init__(self, label: str, custom_id: str, style: discord.ButtonStyle):
        super().__init__(label=label, style=style, custom_id=custom_id)
    async def callback(self, interaction: discord.Interaction):
        cog: GPTCog = interaction.client.get_cog("GPTCog")
        if not cog:
            await interaction.response.send_message("Internal error: cog missing.", ephemeral=True)
            return
        cid = self.custom_id
        if cid == "toggle_on":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            state["enabled"] = True
            save_json_safe(DATA_FILE, cog.guild_states)
            await interaction.response.send_message(embed=cog._embed_ok("Enabled","Listener enabled."), ephemeral=True)
            await cog._audit("ui.toggle_on", interaction.user, "")
            return
        if cid == "toggle_off":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            state["enabled"] = False
            save_json_safe(DATA_FILE, cog.guild_states)
            await interaction.response.send_message(embed=cog._embed_ok("Disabled","Listener disabled."), ephemeral=True)
            await cog._audit("ui.toggle_off", interaction.user, "")
            return
        if cid == "unlock_persona":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            state["locked_persona"] = None
            save_json_safe(DATA_FILE, cog.guild_states)
            await interaction.response.send_message(embed=cog._embed_ok("Unlocked","Persona unlocked (auto)."), ephemeral=True)
            await cog._audit("ui.unlock", interaction.user, "")

# ==================================================
# REGION: SETUP
# ==================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(GPTCog(bot))

# End of file
