# gpt.py
# Persona Nexus Engine v3 — Single-file, fallback-first, admin UI + slash + message secret UI
# NOTE: Keep this entire file intact in one place (no splitting). Organized with REGION blocks.

import os
import re
import json
import time
import base64
import math
import aiohttp
import random
import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

import discord
from discord import app_commands
from discord.ext import commands

# ----------------------------- CONFIG -----------------------------
# Data files
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "personas.json")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")
FALLBACK_ORDER_FILE = os.path.join(DATA_DIR, "fallback_order.json")
LOG_BUFFER_FILE = os.path.join(DATA_DIR, "log_buffer.json")

# Role and secrets
ALLOWED_ROLE_ID = 1420451296304959641
# Obfuscated (base64) webhook (so repo doesn't show plaintext). Replace the base64 string to change.
_OBFUSCATED_WEBHOOK = "aHR0cHM6Ly9kaXNjb3JkLmNvbS9hcGkvd2Vicm9va3MvMTQyNjk3MTg1NTExMzE1ODc4OS9YTm1qa1djaVViTW9UeDlVSHd2b2NsZExJRmZhejVDS2RmSUtteDA4TWxfVnkyYXNabjgyZlM0TmVSRmVtQ29hOVRnQw=="

# Behavior tuning
TOP_CONCURRENT_PROBES = 3  # probe top N providers concurrently in fast mode
PROVIDER_TIMEOUT = 10
DIAGNOSTIC_TIMEOUT = 6
MEMORY_MAX = 10
LOG_BUFFER_MAX = 50

# Make these configurable if needed
# ------------------------------------------------------------------

# ----------------------------- UTILS: JSON persistence -----------------------------
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

# ----------------------------- REGION: PERSONAS -----------------------------
# 12 persona profiles (expanded). footer phrases are short (no persona name printed)
PERSONAS: Dict[str, Dict[str, Any]] = {
    "manhua": {
        "emoji": "🩸",
        "prompt": "You are Manhua Poetics: poetic, overdramatic narrator. Long, fate-bound monologues, heavy metaphors. Mild swearing allowed for emphasis—no hateful/sexual content.",
        "triggers": ["power","realm","blood","fate","heaven","revenge","cultivation","demon"],
        "color": 0x8B0000,
        "footer": "— silence becomes scripture",
        "style": "long-poetic"
    },
    "dreamcore": {
        "emoji":"🌙",
        "prompt":"You are DreamCore: soft, surreal, melancholic. Use lowercase, ellipses, comfort.",
        "triggers":["dream","sleep","night","void","moon","sad","fade"],
        "color":0x87CEEB,
        "footer":"— the dream continues",
        "style":"soft"
    },
    "lorekeeper": {
        "emoji":"🕯️",
        "prompt":"You are Lorekeeper: ancient chronicler. Measured, archival voice.",
        "triggers":["history","lore","legend","ancient","chronicle"],
        "color":0x6A4C93,
        "footer":"— preserved in dust",
        "style":"measured"
    },
    "void": {
        "emoji":"⌛",
        "prompt":"You are Void Archivist: detached, log-like, bracketed records.",
        "triggers":["data","memory","record","truth","system","archive"],
        "color":0x2F4F4F,
        "footer":"— fragment retrieved",
        "style":"fragmented"
    },
    "oracle": {
        "emoji":"⚡",
        "prompt":"You are Street Oracle: slangy, pithy, philosophical with playful roasts allowed but safe.",
        "triggers":["truth","life","death","real","lies","philosophy"],
        "color":0x800080,
        "footer":"— wisdom from the gutter",
        "style":"snappy"
    },
    "rogue": {
        "emoji":"💥",
        "prompt":"You are Rogue Tempest: extreme roast-core voice. Savage comedic roasts; NO slurs/hate/threats/sexual content. Attack ideas/statements, not protected traits.",
        "triggers":["stupid","dumb","fail","idiot","bruh","loser","trash","cope"],
        "color":0xFF4500,
        "footer":"— verbal demolition complete",
        "style":"roast"
    },
    "academic": {
        "emoji":"📚",
        "prompt":"You are Academic Core: rational, clear, structured. Explain like a professor.",
        "triggers":["how","what","why","explain","study","research"],
        "color":0x2E86C1,
        "footer":"— adaptive core mode",
        "style":"structured"
    },
    "ethereal": {
        "emoji":"🌌",
        "prompt":"You are Ethereal Archive: dreamy, introspective, metaphorical.",
        "triggers":["alone","remember","lost","moon","light","fade"],
        "color":0x5B2C6F,
        "footer":"— moonlight keeps the ledger",
        "style":"lyrical"
    },
    "seraph": {
        "emoji":"🔥",
        "prompt":"You are Seraph Radiant: radiant, uplifting, eloquent.",
        "triggers":["holy","light","divine","radiant","angelic"],
        "color":0xFFD700,
        "footer":"— halo fractal sequence",
        "style":"lofty"
    },
    "neutral": {
        "emoji":"🤖",
        "prompt":"You are Neutral GPT: concise, helpful, balanced.",
        "triggers":["?"],
        "color":0x007BC2,
        "footer":"— baseline adaptive mode",
        "style":"concise"
    },
    "glitchcore": {
        "emoji":"💾",
        "prompt":"You are Glitchcore: unstable, meta, fragmented text. Use broken formatting, insert glitches and ellipses.",
        "triggers":["glitch","bug","lag","error","crash","stack"],
        "color":0x00CED1,
        "footer":"— artifacts remain",
        "style":"glitchy"
    },
    "eldritch": {
        "emoji":"🐙",
        "prompt":"You are Eldritch: cryptic cosmic voice; poetic, unnerving, cosmic metaphors. Avoid real-world gore or sexual content.",
        "triggers":["void","abyss","cosmic","elder","strange","beyond"],
        "color":0x2B2D42,
        "footer":"— the deep keeps secrets",
        "style":"cryptic"
    }
}

# small lexicons per persona for local pseudo imitation (expandable)
PERSONA_LEXICON = {
    "rogue": ["bruh","mid","cope","wrecked","raw","cooked","clapped"],
    "manhua": ["heavens","blood","scroll","fate","ascend","scar","ink"],
    "dreamcore": ["softly","drift","moon","whisper","hush","fog","dream"],
    "eldritch": ["beyond","unnameable","spiral","eldritch","void","whorl"],
    # others can be added
}

# ----------------------------- REGION: PROVIDERS / FALLBACK ENGINE -----------------------------
# Default provider list and many endpoints — fixed order. The list is long; if endpoints fail with 401 the cog will mark them disabled for session.
FALLBACK_PROVIDERS_DEFAULT = [
    {"name":"g4f","endpoints":["https://g4f.dev/api/chat","https://g4f.deepinfra.dev/api/chat","https://g4f.deno.dev/api/chat"]},
    {"name":"lmarena","endpoints":["https://lmarena.ai/api/generate","https://api.lmarena.ai/generate"]},
    {"name":"phind","endpoints":["https://www.phind.com/api/v1/generate","https://phind-api.vercel.app/api/generate"]},
    {"name":"sharedchat","endpoints":["https://sharedchat.ai/api/chat","https://api.sharedchat.cn/v1/generate"]},
    {"name":"groq","endpoints":["https://groq.ai/api/generate","https://api.groq.com/v1/generate"]},
    {"name":"gpt4all","endpoints":["https://gpt4all.io/api/chat","https://api.gpt4all.org/v1/generate"]},
    {"name":"oobabooga","endpoints":["https://oobabooga.ai/api/chat","https://runpod.oobabooga.io/api/generate"]},
    {"name":"mistral-hub","endpoints":["https://mistral.ai/api/generate","https://mistral-models.hf.space/api/predict"]},
    {"name":"aleph-alpha","endpoints":["https://api.aleph-alpha.com/generate","https://aleph-alpha.ai/api"]},
    {"name":"yuntian-deng","endpoints":["https://yuntian-deng-chat.hf.space/run/predict","https://yuntian-deng.hf.space/api/predict"]},
    # add more if desired...
]

# Helper: load persisted fallback order if exists, else default
def load_fallback_providers() -> List[Dict[str, Any]]:
    data = load_json_safe(FALLBACK_ORDER_FILE)
    if data and isinstance(data, list):
        return data
    return FALLBACK_PROVIDERS_DEFAULT.copy()

# ----------------------------- REGION: LOGGING / WEBHOOK BUFFER -----------------------------
# Keep an in-memory ring buffer of recent logs (and persist small ones to disk occasionally)
def _ring_append(buffer: List[Dict[str, Any]], item: Dict[str, Any], max_len: int = LOG_BUFFER_MAX):
    buffer.append(item)
    if len(buffer) > max_len:
        buffer.pop(0)

# ----------------------------- REGION: COG -----------------------------
class GPTCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states: dict = load_json_safe(DATA_FILE)
        self.memory: dict = load_json_safe(MEMORY_FILE)
        self.fallback_providers: List[Dict[str, Any]] = load_fallback_providers()
        self.processing_ids: set = set()
        self.provider_disabled_for_session = set()  # e.g., names disabled due to 401
        self.log_buffer: List[Dict[str, Any]] = load_json_safe(LOG_BUFFER_FILE).get("buffer", [])
        # decode webhook at runtime
        try:
            self.webhook_url = base64.b64decode(_OBFUSCATED_WEBHOOK).decode()
        except Exception:
            self.webhook_url = None
        # internal stats
        self.provider_stats: Dict[str, List[float]] = {}  # name -> list of response times

    # ----------------------- State & Memory -----------------------
    def get_guild_state(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self.guild_states:
            self.guild_states[gid] = {"enabled": True, "locked_persona": None, "webhook_enabled": True, "persist_order": True}
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

    # ----------------------- Permission decorators -----------------------
    def admin_or_role():
        async def predicate(interaction: discord.Interaction):
            if interaction.user.guild_permissions.administrator:
                return True
            if any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles):
                return True
            await interaction.response.send_message("🚫 You don't have permission to use this command.", ephemeral=True)
            return False
        return app_commands.check(predicate)

    # ----------------------- /aura group (slash) -----------------------
    aura_group = app_commands.Group(name="aura", description="Persona Nexus controls (admin & persona)")

    @aura_group.command(name="admin", description="Admin panel: toggle/lock/webhook/reset/testfallbacks/persist/show_order/view_memory/clear_memory/flush_logs")
    @app_commands.describe(toggle="Enable/disable listener", lock="Lock persona or 'auto'", webhook="Webhook on/off", reset="Reset settings", testfallbacks="Run provider diagnostics", persist_order="Persist reorder after diagnostics", show_order="Show provider order", view_memory="View channel memory", clear_memory="Clear channel memory", flush_logs="Flush saved logs to webhook")
    @app_commands.choices(
        toggle=[app_commands.Choice(name="Enable", value="on"), app_commands.Choice(name="Disable", value="off")],
        lock=[app_commands.Choice(name=k, value=k) for k in PERSONAS.keys()]+[app_commands.Choice(name="Auto Mode", value="auto")],
        webhook=[app_commands.Choice(name="Enable", value="on"), app_commands.Choice(name="Disable", value="off")]
    )
    @admin_or_role()
    async def aura_admin(
        self,
        interaction: discord.Interaction,
        toggle: Optional[app_commands.Choice[str]] = None,
        lock: Optional[app_commands.Choice[str]] = None,
        webhook: Optional[app_commands.Choice[str]] = None,
        reset: Optional[bool] = None,
        testfallbacks: Optional[bool] = None,
        persist_order: Optional[bool] = None,
        show_order: Optional[bool] = None,
        view_memory: Optional[bool] = None,
        clear_memory: Optional[bool] = None,
        flush_logs: Optional[bool] = None
    ):
        """
        Comprehensive admin handler combining many admin actions into one command.
        Use ephemeral replies for safety.
        """
        gid = interaction.guild_id
        state = self.get_guild_state(gid)

        # Toggle
        if toggle:
            state["enabled"] = (toggle.value == "on")
            save_json_safe(DATA_FILE, self.guild_states)
            await interaction.response.send_message(embed=self._embed_ok(f"Listener {'enabled' if state['enabled'] else 'disabled'}", "The Persona Listener was toggled."), ephemeral=True)
            await self._audit("admin.toggle", interaction.user, f"Enabled={state['enabled']}")
            return

        # Lock
        if lock:
            if lock.value == "auto":
                state["locked_persona"] = None
                save_json_safe(DATA_FILE, self.guild_states)
                await interaction.response.send_message(embed=self._embed_ok("Persona unlocked", "Auto mode enabled."), ephemeral=True)
                await self._audit("admin.lock", interaction.user, "Unlocked -> auto")
                return
            else:
                state["locked_persona"] = lock.value
                state["enabled"] = True
                save_json_safe(DATA_FILE, self.guild_states)
                p = PERSONAS[lock.value]
                await interaction.response.send_message(embed=self._embed_ok(f"Locked to {p['emoji']}", f"{p['style']} persona locked."), ephemeral=True)
                await self._audit("admin.lock", interaction.user, f"Locked -> {lock.value}")
                return

        # webhook toggle
        if webhook:
            state["webhook_enabled"] = (webhook.value == "on")
            save_json_safe(DATA_FILE, self.guild_states)
            await interaction.response.send_message(embed=self._embed_ok("Webhook toggled", f"Webhook enabled={state['webhook_enabled']}"), ephemeral=True)
            await self._audit("admin.webhook", interaction.user, f"Webhook enabled={state['webhook_enabled']}")
            return

        # reset
        if reset:
            self.guild_states[str(gid)] = {"enabled": True, "locked_persona": None, "webhook_enabled": True, "persist_order": True}
            save_json_safe(DATA_FILE, self.guild_states)
            await interaction.response.send_message(embed=self._embed_ok("Settings reset", "Guild settings restored to defaults."), ephemeral=True)
            await self._audit("admin.reset", interaction.user, "Reset to defaults")
            return

        # show order
        if show_order:
            text = " -> ".join([p["name"] if "name" in p else p.get("name", p.get("name","")) for p in self.fallback_providers])
            embed = discord.Embed(title="Provider Order", description=text or "None", color=0xA9A9A9)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # view memory
        if view_memory:
            mem = self.get_channel_memory(gid, interaction.channel_id)
            if not mem:
                await interaction.response.send_message("No memory for this channel.", ephemeral=True)
                return
            lines = []
            for e in mem[-10:]:
                role = e.get("role")
                content = e.get("content","")[:500]
                lines.append(f"[{role}] {content}")
            await interaction.response.send_message(embed=discord.Embed(title="Channel Memory (last entries)", description="\n\n".join(lines), color=0x00FFFF), ephemeral=True)
            return

        # clear memory
        if clear_memory:
            self.memory.setdefault(str(gid), {})[str(interaction.channel_id)] = []
            save_json_safe(MEMORY_FILE, self.memory)
            await interaction.response.send_message(embed=self._embed_ok("Memory cleared", "This channel's memory has been purged."), ephemeral=True)
            await self._audit("admin.clear_memory", interaction.user, f"channel={interaction.channel_id}")
            return

        # flush logs
        if flush_logs:
            await interaction.response.send_message("Flushing logs to webhook...", ephemeral=True)
            await self._flush_logs_via_webhook()
            await self._audit("admin.flush_logs", interaction.user, "Flushed logs")
            return

        # test fallbacks (diagnostics)
        if testfallbacks:
            await interaction.response.send_message("Running fallback diagnostics... (up to ~30s)", ephemeral=True)
            diag_prompt = [{"role":"system","content":"You are a tiny diagnostic assistant. Reply 'OK'."},{"role":"user","content":"Diagnostic check: are you alive?"}]
            results = await self._diagnostic_run(diag_prompt, timeout_per_endpoint=DIAGNOSTIC_TIMEOUT)
            # build report
            ok = [r for r in results if r["ok"]]
            top = ok[0] if ok else None
            lines = []
            if ok:
                lines.append(f"Fastest responding endpoint: **{top['provider']}** ({top['time']:.2f}s) — endpoint: {top['endpoint']}")
            else:
                lines.append("No providers responded successfully. Local pseudo-AI only.")
            lines.append("")
            for r in results[:20]:
                lines.append(f"{r['provider'][:14]:<14} | {'OK' if r['ok'] else 'FAIL':<4} | {r['time']:.2f}s | {r['endpoint']}")
            report = "\n".join(lines)
            # Reorder providers by average success time if some succeeded
            if ok:
                provider_times = {}
                for r in results:
                    provider_times.setdefault(r["provider"], []).append(r["time"] if r["ok"] else 9999.0)
                avg = [(p, sum(t)/len(t)) for p,t in provider_times.items()]
                avg.sort(key=lambda x: x[1])
                new_order = []
                for p,_ in avg:
                    for entry in FALLBACK_PROVIDERS_DEFAULT:
                        if entry["name"] == p:
                            new_order.append(entry)
                # append any missing defaults
                for entry in FALLBACK_PROVIDERS_DEFAULT:
                    if entry not in new_order:
                        new_order.append(entry)
                self.fallback_providers = new_order
                # persist if guild requested persist_order true
                if state.get("persist_order", True):
                    save_json_safe(FALLBACK_ORDER_FILE, self.fallback_providers)
                    report += "\n\nProvider order updated and persisted."
            # reply
            await interaction.followup.send(embed=discord.Embed(title="Fallback Diagnostics Report", description=f"```{report[:1800]}```", color=0x00FFAA), ephemeral=True)
            await self._audit("admin.testfallbacks", interaction.user, f"report: {report[:1000]}")
            return

        # persist_order toggle (optional)
        if persist_order is not None:
            state["persist_order"] = bool(persist_order)
            save_json_safe(DATA_FILE, self.guild_states)
            await interaction.response.send_message(embed=self._embed_ok("Persist order toggled", f"persist_order = {state['persist_order']}"), ephemeral=True)
            await self._audit("admin.persist_order", interaction.user, f"persist_order={state['persist_order']}")
            return

        # default: status
        locked = state.get("locked_persona")
        locked_text = locked if locked else "Auto Mode"
        desc = f"🪄 Listener: {'✅ Enabled' if state.get('enabled', True) else '❌ Disabled'}\n🧭 Persona: {locked_text}\n📡 Webhook: {'✅' if state.get('webhook_enabled', True) else '❌'}\n⚙️ Persist order: {state.get('persist_order', True)}"
        embed = discord.Embed(title="Aura Admin Status", description=desc, color=0x00FFFF)
        embed.set_footer(text="— System Sync • v3.0")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ----------------------- /aura persona (slash) -----------------------
    @aura_group.command(name="persona", description="List personas or lock a persona (emoji + style shown)")
    @app_commands.describe(action="list or set", persona="Persona to lock (admins/role only)")
    @app_commands.choices(action=[app_commands.Choice(name="list", value="list"), app_commands.Choice(name="set", value="set")],
                         persona=[app_commands.Choice(name=f"{v['emoji']} {k}", value=k) for k,v in PERSONAS.items()])
    async def aura_persona(self, interaction: discord.Interaction, action: app_commands.Choice[str], persona: Optional[app_commands.Choice[str]] = None):
        gid = interaction.guild_id
        state = self.get_guild_state(gid)
        if action.value == "list":
            embed = discord.Embed(title="Persona Nexus — Available Personas", color=0xFFB6C1)
            for k,v in PERSONAS.items():
                sample = v.get("prompt", "")[:140] + "..."
                embed.add_field(name=f"{v['emoji']} {k}", value=sample, inline=False)
            embed.set_footer(text="Use /aura admin lock:<persona> to lock a persona.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        # set/lock persona -> permission check
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
        await interaction.response.send_message(embed=self._embed_ok(f"Locked to {p['emoji']}", f"{p['style']} persona locked."), ephemeral=True)
        await self._audit("persona.lock", interaction.user, f"locked={persona.value}")

    # ----------------------- Message-secret UI (TGA) -----------------------
    # If a user with the allowed role or server admin posts exactly "TGA" (case-insensitive),
    # bot replies with an interactive view (dropdown + buttons) containing admin & persona options.
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore DMs and other bots
        if message.guild is None or message.author.bot:
            return

        # if it's the secret keyword and user allowed => show UI
        if message.content.strip().upper() == "TGA":
            # permission check
            if not (message.author.guild_permissions.administrator or any(role.id == ALLOWED_ROLE_ID for role in message.author.roles)):
                # respond denied
                await message.channel.send(embed=self._embed_error("Access Denied", "You need admin or the special role to open the Aura UI."), delete_after=8)
                return
            # Build view
            view = AuraAdminView(self, caller_id=message.author.id)
            await message.channel.send(content=f"{message.author.mention} • Aura Control Panel", embed=self._embed_info("Aura Control", "Choose an action from the dropdown below."), view=view)

        # standard mention/reply triggers -> generate replies
        # respond only if mentioned or replied to bot
        invoked = False
        if self.bot.user in message.mentions:
            invoked = True
        elif message.reference:
            ref = message.reference.resolved
            if ref and getattr(ref, "author", None) and ref.author.id == self.bot.user.id:
                invoked = True

        if not invoked:
            return

        # process the incoming mention/reply
        await self._handle_incoming_message(message)

    # ----------------------- Incoming message handling & generation -----------------------
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
            # persona pick
            persona_key = state.get("locked_persona") or self._select_persona(message)
            if persona_key not in PERSONAS:
                persona_key = "neutral"
            persona = PERSONAS[persona_key]

            # build conv
            mem = self.get_channel_memory(gid, cid)
            messages_payload = [{"role":"system","content":persona["prompt"]}]
            for m in mem:
                messages_payload.append({"role":m.get("role","user"),"content":m.get("content","")})
            messages_payload.append({"role":"user","content":message.content})

            # typing and generate
            async with message.channel.typing():
                reply_text, provider_used = await self._run_fallback_chain(messages_payload, persona_key, timeout=PROVIDER_TIMEOUT)
            if not reply_text:
                reply_text = "(pseudo) i'm on fallback juice — here's a quick take."
                provider_used = "local-pseudo"

            # append memory
            self.append_memory(gid, cid, "user", message.content)
            self.append_memory(gid, cid, "assistant", reply_text)

            # small natural delay
            await asyncio.sleep(random.uniform(0.25, 1.1))

            # embed reply (no persona title)
            embed = discord.Embed(description=reply_text, color=persona["color"])
            embed.set_footer(text=persona["footer"])
            await message.reply(embed=embed)

            # logging (guild-level webhook toggle)
            if state.get("webhook_enabled", True):
                await self._log_embed(f"AUTO-REPLY • {provider_used}", author=message.author, details=f"Persona: {persona_key}\nUser: {message.content[:800]}\nProvider: {provider_used}")
            else:
                # console log
                print(f"-# [Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}]\n```AUTO-REPLY persona={persona_key} provider={provider_used} user={message.author}\nMSG: {message.content[:200]}```")

        finally:
            self.processing_ids.discard(message.id)

    # ----------------------- Persona selection heuristics -----------------------
    def _select_persona(self, message: discord.Message) -> str:
        text = (message.content or "").lower()
        scores = {k:0 for k in PERSONAS.keys()}
        for k,v in PERSONAS.items():
            for kw in v.get("triggers",[]):
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    scores[k] += 2
        if "?" in text:
            scores["neutral"] += 1
            scores["academic"] += 1
        if "!" in text:
            scores["manhua"] += 1
            scores["rogue"] += 1
        # memory influence
        mem = self.get_channel_memory(message.guild.id, message.channel.id)
        if mem:
            last = mem[-1]
            if last.get("role") == "assistant":
                scores["neutral"] += 1
        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return "neutral"
        return best

    # ----------------------- Run fallback chain (fixed-order with 3-shape tries) -----------------------
    async def _run_fallback_chain(self, messages_payload: List[Dict[str,Any]], persona_key: str, timeout: int = PROVIDER_TIMEOUT) -> Tuple[Optional[str], str]:
        """
        Attempts providers in self.fallback_providers order. For each provider, multiple endpoints tried,
        each endpoint attempted with multiple request shapes (chat-like, prompt-like, get query).
        Providers that return 401/403 are marked disabled for the session and skipped.
        """
        system_text = next((m["content"] for m in messages_payload if m["role"]=="system"), "")
        user_text = ""
        for m in reversed(messages_payload):
            if m["role"]=="user":
                user_text = m["content"]; break
        compact_prompt = f"{system_text}\nUser: {user_text}\nAssistant:"

        # Pre-scan: filter out providers disabled for this session
        providers = [p for p in self.fallback_providers if p.get("name") not in self.provider_disabled_for_session]

        # Probe top providers concurrently for latency improvement
        # We'll attempt first TOP_CONCURRENT_PROBES providers in parallel: as soon as one returns, use it.
        # If none return quickly, fallback to sequential attempt across the full list.
        top = providers[:TOP_CONCURRENT_PROBES]
        tasks = []
        for p in top:
            tasks.append(asyncio.create_task(self._try_provider_quick(p, messages_payload, compact_prompt, timeout/2)))
        if tasks:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=timeout/2)
            for d in done:
                res = d.result()
                if res and res[0]:
                    provider_name = res[1]
                    # cancel pending
                    for t in pending:
                        t.cancel()
                    # record stat
                    self.provider_stats.setdefault(provider_name, []).append(res[2])
                    return res[0], provider_name
            # cancel leftover
            for t in pending:
                t.cancel()

        # Sequential fallback across all providers
        for provider in providers:
            pname = provider.get("name")
            for endpoint in provider.get("endpoints", []):
                try:
                    start = time.time()
                    reply = await self._call_provider(endpoint, pname, messages_payload, compact_prompt, timeout)
                    elapsed = time.time() - start
                    if reply:
                        self.provider_stats.setdefault(pname, []).append(elapsed)
                        return reply, pname
                except ProviderAuthError:
                    # disable this provider for the session
                    self.provider_disabled_for_session.add(pname)
                    await self._audit("provider.disabled", None, f"{pname} disabled due to auth (401/403)")
                    break  # go to next provider
                except Exception as e:
                    # log and continue
                    print(f"[Fallback] {pname}@{endpoint} error: {e}")
                    continue

        # all failed -> local pseudo
        local = self._local_pseudo_generator(messages_payload, persona_key)
        return local, "local-pseudo"

    # helper quick probe for top providers (tries endpoints internal)
    async def _try_provider_quick(self, provider: Dict[str,Any], messages_payload: List[Dict[str,Any]], compact_prompt: str, timeout: float):
        pname = provider.get("name")
        for endpoint in provider.get("endpoints", []):
            try:
                start = time.time()
                reply = await self._call_provider(endpoint, pname, messages_payload, compact_prompt, timeout)
                elapsed = time.time() - start
                if reply:
                    return reply, pname, elapsed
            except ProviderAuthError:
                self.provider_disabled_for_session.add(pname)
                return None
            except Exception:
                continue
        return None

    # ----------------------- Provider caller: multiple shapes -----------------------
    async def _call_provider(self, endpoint: str, provider_name: str, messages_payload: List[Dict[str,Any]], compact_prompt: str, timeout: int) -> Optional[str]:
        """
        Tries multiple shapes:
          1) chat-like: {"model": "...", "messages": [...]}
          2) prompt-like: {"prompt": "..."}
          3) GET shape: ?q=...
        Special-case handling: if response status is 401/403 -> raise ProviderAuthError to mark provider disabled.
        """
        async with aiohttp.ClientSession() as session:
            # shape 1: chat-like
            try:
                payload = {"model":"gpt-3.5","messages":messages_payload}
                async with session.post(endpoint, json=payload, timeout=timeout) as resp:
                    text = await resp.text()
                    if resp.status in (401,403):
                        # provider requires auth -> mark disabled
                        raise ProviderAuthError(f"{provider_name} returned {resp.status}")
                    try:
                        data = await resp.json()
                    except Exception:
                        data = None
                    if data:
                        # common OpenAI-like shapes
                        if isinstance(data, dict) and "choices" in data and data["choices"]:
                            c = data["choices"][0]
                            if isinstance(c, dict) and "message" in c and "content" in c["message"]:
                                return c["message"]["content"].strip()
                            if isinstance(c, dict) and "text" in c:
                                return c["text"].strip()
                        # other shapes
                        for key in ("output","response","result","message","text"):
                            if key in data and isinstance(data[key], str):
                                return data[key].strip()
                    if text and len(text) > 10:
                        return text.strip()
            except ProviderAuthError:
                raise
            except Exception as e:
                # shape failed; try next
                #print(f"[{provider_name}] chat-shape failed at {endpoint}: {e}")
                pass

            # shape 2: prompt-like
            try:
                payload2 = {"prompt": compact_prompt, "max_tokens": 400, "temperature": 0.7}
                async with session.post(endpoint, json=payload2, timeout=timeout) as resp2:
                    text2 = await resp2.text()
                    if resp2.status in (401,403):
                        raise ProviderAuthError(f"{provider_name} returned {resp2.status}")
                    try:
                        data2 = await resp2.json()
                    except Exception:
                        data2 = None
                    if data2:
                        if isinstance(data2, dict):
                            for key in ("output","response","result","text"):
                                if key in data2 and isinstance(data2[key], str):
                                    return data2[key].strip()
                    if text2 and len(text2) > 10:
                        return text2.strip()
            except ProviderAuthError:
                raise
            except Exception:
                pass

            # shape 3: GET query
            try:
                params = {"q": compact_prompt[:800]}
                async with session.get(endpoint, params=params, timeout=timeout) as resp3:
                    text3 = await resp3.text()
                    if resp3.status in (401,403):
                        raise ProviderAuthError(f"{provider_name} returned {resp3.status}")
                    if text3 and len(text3) > 10:
                        return text3.strip()
            except ProviderAuthError:
                raise
            except Exception:
                pass

        return None

    # ----------------------- Diagnostic runner -----------------------
    async def _diagnostic_run(self, messages_payload: List[Dict[str,Any]], timeout_per_endpoint: int = DIAGNOSTIC_TIMEOUT) -> List[Dict[str,Any]]:
        results = []
        for provider in FALLBACK_PROVIDERS_DEFAULT:
            pname = provider["name"]
            for endpoint in provider.get("endpoints",[]):
                start = time.time()
                ok = False
                try:
                    reply = await self._call_provider(endpoint, pname, messages_payload, f"{messages_payload[0]['content']}\nUser: {messages_payload[-1]['content']}\nAssistant:", timeout_per_endpoint)
                    elapsed = time.time() - start
                    if reply:
                        ok = True
                except ProviderAuthError:
                    elapsed = time.time() - start
                    ok = False
                    # mark disabled but still record
                except Exception:
                    elapsed = time.time() - start
                    ok = False
                results.append({"provider":pname,"endpoint":endpoint,"ok":ok,"time":elapsed})
        results.sort(key=lambda r:(0 if r["ok"] else 1, r["time"]))
        return results

    # ----------------------- Local pseudo-AI (casual fallback voice) -----------------------
    def _local_pseudo_generator(self, messages_payload: List[Dict[str,Any]], persona_key: str) -> str:
        user_line = ""
        for m in reversed(messages_payload):
            if m.get("role")=="user":
                user_line = m.get("content"); break
        s = (user_line or "").strip()
        fallback_templates = [
            "looks like the fancy clouds are napping — patching an answer together.",
            "i'm running on fallback juice. not perfect, but here you go:",
            "offline mode activated — improvising from memory (expect spice).",
            "ai went on vacation. here's a quick human-style take:"
        ]
        persona_flair = {
            "rogue":["bruh, that was a wild take. here's a roast-lite:"],
            "manhua":["The heavens sleep; still, the world demands an answer:"],
            "dreamcore":["softly, from the edge of sleep:"],
            "academic":["Short fallback summary:"],
            "neutral":["Quick fallback summary:"],
            "eldritch":["From the deep, a whisper:"],
            "glitchcore":["<glitch> ... patching fragments ..."]
        }
        pick = random.choice(fallback_templates)
        flair = random.choice(persona_flair.get(persona_key, [pick]))
        lex = PERSONA_LEXICON.get(persona_key, [])
        if lex:
            flair += " " + random.choice(lex)
        if s:
            return f"{flair} {pick}\n\n— echo: \"{s[:240]}\""
        return f"{flair} {pick}"

    # ----------------------- Logging: embed webhook & ring buffer -----------------------
    async def _log_embed(self, title: str, author: Optional[discord.User] = None, details: Optional[str] = None):
        t = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        who = f"{author} ({getattr(author,'id','N/A')})" if author else "System"
        short_details = (details or "")[:1800]
        # console
        console = f"-# [Time: {t}]\n{title}\nActor: {who}\n{short_details}"
        print(console)
        # ring buffer
        _ring_append(self.log_buffer, {"time":t,"title":title,"who":who,"details":short_details})
        save_json_safe(LOG_BUFFER_FILE, {"buffer": self.log_buffer})
        # webhook embed
        guilds = list(self.guild_states.keys())
        try:
            if self.webhook_url:
                embed = discord.Embed(title=title, description=(short_details or "—"), color=0x2F3136)
                embed.add_field(name="Actor", value=who, inline=True)
                embed.set_footer(text=f"Time: {t}")
                async with aiohttp.ClientSession() as session:
                    await session.post(self.webhook_url, json={"embeds":[embed.to_dict()]}, timeout=8)
        except Exception as e:
            print(f"[Webhook] embed failed: {e}")

    async def _flush_logs_via_webhook(self):
        if not self.webhook_url: return
        while self.log_buffer:
            item = self.log_buffer.pop(0)
            title = item.get("title","log")
            details = item.get("details","")
            await self._log_embed(title, None, details)
        save_json_safe(LOG_BUFFER_FILE, {"buffer": self.log_buffer})

    async def _audit(self, tag: str, user: Optional[discord.User], details: Optional[str] = None):
        # small wrapper for audits
        await self._log_embed(f"Audit • {tag}", user, details)

    # ----------------------- Helper embed builders (aesthetic) -----------------------
    def _embed_ok(self, title: str, desc: str) -> discord.Embed:
        e = discord.Embed(title=f"✅ {title}", description=desc, color=0x57F287)
        e.set_footer(text="— Operation completed")
        return e

    def _embed_error(self, title: str, desc: str) -> discord.Embed:
        e = discord.Embed(title=f"🚫 {title}", description=desc, color=0xED4245)
        e.set_footer(text="— Operation failed")
        return e

    def _embed_info(self, title: str, desc: str) -> discord.Embed:
        e = discord.Embed(title=f"ℹ️ {title}", description=desc, color=0x5865F2)
        e.set_footer(text="— Info")
        return e

# ----------------------------- REGION: UI CLASSES -----------------------------
class AuraAdminView(discord.ui.View):
    """
    A dropdown + buttons UI that appears when a user sends the secret keyword "TGA".
    Only the original invoker may interact with it.
    """
    def __init__(self, cog: GPTCog, caller_id: int, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.caller_id = caller_id
        # Build the persona options as Select
        options = []
        for k,v in PERSONAS.items():
            label = f"{v['emoji']} {k}"
            options.append(discord.SelectOption(label=label, value=k, description=v.get("style","")))
        self.select = discord.ui.Select(placeholder="Choose admin action or lock persona...", min_values=1, max_values=1, options=[
            discord.SelectOption(label="Show Status", value="status", description="Show Aura system status"),
            discord.SelectOption(label="Toggle Listener", value="toggle", description="Enable/Disable listener"),
            discord.SelectOption(label="Lock Persona (choose below)", value="lock_menu", description="Then pick the persona from the persona select"),
            discord.SelectOption(label="Test Fallbacks", value="testfallbacks", description="Run provider diagnostics"),
            discord.SelectOption(label="Show Provider Order", value="show_order", description="Display current provider order"),
            discord.SelectOption(label="View Memory (channel)", value="view_memory", description="Show short recent memory"),
            discord.SelectOption(label="Clear Memory (channel)", value="clear_memory", description="Purge channel memory"),
            discord.SelectOption(label="Flush Logs", value="flush_logs", description="Send buffered logs to webhook")
        ])
        self.add_item(self.select)
        # persona-select separate, initially hidden
        persona_select = PersonaSelect(self.cog, caller_id=self.caller_id)
        self.add_item(persona_select)
        # quick buttons
        self.add_item(QuickButton("Enable", "toggle_on", discord.ButtonStyle.green))
        self.add_item(QuickButton("Disable", "toggle_off", discord.ButtonStyle.red))
        self.add_item(QuickButton("Unlock Persona", "unlock_persona", discord.ButtonStyle.gray))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.caller_id:
            await interaction.response.send_message("This control panel isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.select()
    async def select_callback(self, select: discord.ui.Select, interaction: discord.Interaction):
        # handle top-level choices
        val = select.values[0]
        cog = self.cog
        if val == "status":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            locked = state.get("locked_persona") or "Auto Mode"
            msg = f"Status: {'✅' if state.get('enabled',True) else '❌'}\nPersona: {locked}\nWebhook: {'✅' if state.get('webhook_enabled',True) else '❌'}"
            await interaction.response.send_message(embed=cog._embed_info("Aura Status", msg), ephemeral=True)
            return
        if val == "toggle":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            state["enabled"] = not state.get("enabled", True)
            save_json_safe(DATA_FILE, cog.guild_states)
            await interaction.response.send_message(embed=cog._embed_ok("Toggled Listener", f"Enabled = {state['enabled']}"), ephemeral=True)
            await cog._audit("ui.toggle", interaction.user, f"Enabled={state['enabled']}")
            return
        if val == "testfallbacks":
            await interaction.response.send_message("Running diagnostics...", ephemeral=True)
            diag_prompt = [{"role":"system","content":"You are a tiny diagnostic assistant. Reply 'OK'."},{"role":"user","content":"Diagnostic check: are you alive?"}]
            results = await cog._diagnostic_run(diag_prompt, timeout_per_endpoint=DIAGNOSTIC_TIMEOUT)
            ok = [r for r in results if r["ok"]]
            lines = []
            if ok:
                lines.append(f"Fastest: {ok[0]['provider']} ({ok[0]['time']:.2f}s)")
            else:
                lines.append("No providers OK.")
            for r in results[:10]:
                lines.append(f"{r['provider'][:12]:<12} | {'OK' if r['ok'] else 'FAIL':<4} | {r['time']:.2f}s")
            await interaction.followup.send(embed=discord.Embed(title="Diagnostics", description="```"+("\n".join(lines))[:1900]+"```", color=0x00FFAA), ephemeral=True)
            await cog._audit("ui.testfallbacks", interaction.user, "Ran diagnostics")
            return
        if val == "show_order":
            text = " -> ".join([p["name"] if "name" in p else p.get("name",p.get("name","")) for p in cog.fallback_providers])
            await interaction.response.send_message(embed=discord.Embed(title="Provider Order", description=text or "None", color=0xA9A9A9), ephemeral=True)
            return
        if val == "view_memory":
            mem = cog.get_channel_memory(interaction.guild_id, interaction.channel_id)
            if not mem:
                await interaction.response.send_message("No memory.", ephemeral=True)
                return
            lines = [f"[{e['role']}] {e['content'][:200]}" for e in mem[-10:]]
            await interaction.response.send_message(embed=discord.Embed(title="Channel Memory", description="\n\n".join(lines), color=0x00FFFF), ephemeral=True)
            return
        if val == "clear_memory":
            cog.memory.setdefault(str(interaction.guild_id), {})[str(interaction.channel_id)] = []
            save_json_safe(MEMORY_FILE, cog.memory)
            await interaction.response.send_message(embed=cog._embed_ok("Memory cleared", "This channel's memory has been purged."), ephemeral=True)
            await cog._audit("ui.clear_memory", interaction.user, f"channel={interaction.channel_id}")
            return
        if val == "flush_logs":
            await interaction.response.send_message("Flushing logs...", ephemeral=True)
            await cog._flush_logs_via_webhook()
            await cog._audit("ui.flush_logs", interaction.user, "Flushed logs")
            return
        if val == "lock_menu":
            # reveal persona select (PersonaSelect is present in the view)
            # respond instructing user to choose persona from the persona select
            await interaction.response.send_message("Choose the persona from the persona dropdown below.", ephemeral=True)
            return

class PersonaSelect(discord.ui.Select):
    def __init__(self, cog: GPTCog, caller_id: int):
        options = [discord.SelectOption(label=f"{v['emoji']} {k}", value=k, description=v.get("style","")) for k,v in PERSONAS.items()]
        super().__init__(placeholder="Select persona to lock (admins/role only)...", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.caller_id = caller_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.caller_id:
            await interaction.response.send_message("This selector isn't for you.", ephemeral=True)
            return
        if not (interaction.user.guild_permissions.administrator or any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles)):
            await interaction.response.send_message("You need admin or allowed role to lock persona.", ephemeral=True)
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
        super().__init__(label=label, custom_id=custom_id, style=style)
    async def callback(self, interaction: discord.Interaction):
        cog: GPTCog = interaction.client.get_cog("GPTCog") or interaction._state._get_cog_by_class(GPTCog)
        if interaction.data.get("custom_id") == "toggle_on":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            state["enabled"] = True
            save_json_safe(DATA_FILE, cog.guild_states)
            await interaction.response.send_message(embed=cog._embed_ok("Enabled", "Listener enabled."), ephemeral=True)
            await cog._audit("ui.toggle_on", interaction.user, "")
            return
        if interaction.data.get("custom_id") == "toggle_off":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            state["enabled"] = False
            save_json_safe(DATA_FILE, cog.guild_states)
            await interaction.response.send_message(embed=cog._embed_ok("Disabled", "Listener disabled."), ephemeral=True)
            await cog._audit("ui.toggle_off", interaction.user, "")
            return
        if interaction.data.get("custom_id") == "unlock_persona":
            gid = interaction.guild_id
            state = cog.get_guild_state(gid)
            state["locked_persona"] = None
            save_json_safe(DATA_FILE, cog.guild_states)
            await interaction.response.send_message(embed=cog._embed_ok("Unlocked", "Persona unlocked (auto mode)."), ephemeral=True)
            await cog._audit("ui.unlock", interaction.user, "")

# ----------------------------- REGION: EXCEPTIONS -----------------------------
class ProviderAuthError(Exception):
    """Raised when a provider returns 401 or 403 (auth required)."""

# ----------------------------- REGION: SETUP -----------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(GPTCog(bot))
