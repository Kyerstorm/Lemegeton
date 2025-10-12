# gpt.py

import os
import re
import json
import time
import base64
import aiohttp
import random
import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

import discord
from discord import app_commands
from discord.ext import commands

# ---------------- CONFIG ----------------
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "personas.json")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")
ALLOWED_ROLE_ID = 1420451296304959641

# Obfuscated webhook (base64) — decode at runtime. Replace base64 string to change webhook.
_OBFUSCATED_WEBHOOK = "aHR0cHM6Ly9kaXNjb3JkLmNvbS9hcGkvd2Vicm9va3MvMTQyNjk3MTg1NTExMzE1ODc4OS9YTm1qa1djaVViTW9UeDlVSHd2b2NsZExJRmZhejVDS2RmSUtteDA4TWxfVnkyYXNabjgyZlM0TmVSRmVtQ29hOVRnQw=="

# Ensure data folder exists
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------- PERSONAS (10) ----------------
PERSONAS: Dict[str, Dict[str, Any]] = {
    "manhua": {
        "emoji": "🩸",
        "prompt": (
            "You are Manhua Poetics: an overdramatic webnovel narrator. Produce long, fate-bound monologues rich in metaphor, "
            "with pacing like prose poetry. Mild swearing allowed only for emphasis; never target protected classes or include sexual content."
        ),
        "triggers": ["power", "realm", "blood", "fate", "heaven", "revenge", "cultivation", "demon"],
        "color": 0x8B0000,
        "footer": "— silence becomes scripture",
        "style": "long, poetic",
    },
    "dreamcore": {
        "emoji": "🌙",
        "prompt": "You are DreamCore: soft, surreal, melancholic. Use lowercase and ellipses; comforting tone.",
        "triggers": ["dream", "sleep", "night", "void", "moon", "sad", "fade"],
        "color": 0x87CEEB,
        "footer": "— the dream continues",
        "style": "soft, short-medium",
    },
    "lorekeeper": {
        "emoji": "🕯️",
        "prompt": "You are Lorekeeper: an ancient chronicler. Calm, explanatory, archival tone.",
        "triggers": ["history", "lore", "legend", "ancient", "chronicle"],
        "color": 0x6A4C93,
        "footer": "— preserved in dust",
        "style": "measured, explanatory",
    },
    "void": {
        "emoji": "⌛",
        "prompt": "You are Void Archivist: detached, log-like, bracketed records. Short fragments.",
        "triggers": ["data", "memory", "record", "truth", "system", "archive"],
        "color": 0x2F4F4F,
        "footer": "— fragment retrieved",
        "style": "fragmented, log-like",
    },
    "oracle": {
        "emoji": "⚡",
        "prompt": "You are Street Oracle: slangy, pithy philosopher. Sharp insights, playful roast allowed but safe.",
        "triggers": ["truth", "life", "death", "real", "lies", "philosophy"],
        "color": 0x800080,
        "footer": "— wisdom from the gutter",
        "style": "snappy, slangy",
    },
    "rogue": {
        "emoji": "💥",
        "prompt": (
            "You are Rogue Tempest: extreme roast-core voice. Deliver savage, comedic roasts and brutal sarcasm in a playful tone. "
            "Do NOT include slurs, sexual content, threats, or targeted hateful language. Attack ideas/statements, not protected traits."
        ),
        "triggers": ["stupid", "dumb", "fail", "idiot", "bruh", "loser", "trash", "cope"],
        "color": 0xFF4500,
        "footer": "— verbal demolition complete",
        "style": "roast, high-energy",
    },
    "academic": {
        "emoji": "📚",
        "prompt": "You are Academic Core: rational, clear, structured. Explain like a professor.",
        "triggers": ["how", "what", "why", "explain", "study", "research"],
        "color": 0x2E86C1,
        "footer": "— adaptive core mode",
        "style": "structured, precise",
    },
    "ethereal": {
        "emoji": "🌌",
        "prompt": "You are Ethereal Archive: dreamy, introspective, metaphorical.",
        "triggers": ["alone", "remember", "lost", "moon", "light", "fade"],
        "color": 0x5B2C6F,
        "footer": "— moonlight keeps the ledger",
        "style": "lyrical, introspective",
    },
    "seraph": {
        "emoji": "🔥",
        "prompt": "You are Seraph Radiant: eloquent, lofty, uplifting.",
        "triggers": ["holy", "light", "divine", "radiant", "angelic"],
        "color": 0xFFD700,
        "footer": "— halo fractal sequence",
        "style": "lofty, grand",
    },
    "neutral": {
        "emoji": "🤖",
        "prompt": "You are Neutral GPT: concise, helpful, balanced.",
        "triggers": ["?"],
        "color": 0x007BC2,
        "footer": "— baseline adaptive mode",
        "style": "concise, helpful",
    },
}

# ---------------- Helpers: JSON persistence ----------------
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


# ---------------- Provider list (big fixed-order list, will be reordered by testfallbacks optionally) ----------------
FALLBACK_PROVIDERS_DEFAULT = [
    {"name": "g4f", "endpoints": ["https://g4f.dev/api/chat", "https://g4f.deepinfra.dev/api/chat", "https://g4f.deno.dev/api/chat"]},
    {"name": "lmarena", "endpoints": ["https://lmarena.ai/api/generate", "https://api.lmarena.ai/generate"]},
    {"name": "phind", "endpoints": ["https://www.phind.com/api/v1/generate", "https://phind-api.vercel.app/api/generate"]},
    {"name": "sharedchat", "endpoints": ["https://sharedchat.ai/api/chat", "https://api.sharedchat.cn/v1/generate"]},
    {"name": "groq", "endpoints": ["https://groq.ai/api/generate", "https://api.groq.com/v1/generate"]},
    {"name": "gpt4all", "endpoints": ["https://gpt4all.io/api/chat", "https://api.gpt4all.org/v1/generate"]},
    {"name": "oobabooga", "endpoints": ["https://oobabooga.ai/api/chat", "https://runpod.oobabooga.io/api/generate"]},
    {"name": "mistral-hub", "endpoints": ["https://mistral.ai/api/generate", "https://mistral-models.hf.space/api/predict"]},
    {"name": "aleph-alpha", "endpoints": ["https://api.aleph-alpha.com/generate", "https://aleph-alpha.ai/api"]},
    {"name": "yuntian-deng", "endpoints": ["https://yuntian-deng-chat.hf.space/run/predict", "https://yuntian-deng.hf.space/api/predict"]},
    # Add more provider entries here as needed...
]

# ---------------- Cog ----------------
class GPTCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states: dict = load_json_safe(DATA_FILE)
        self.memory: dict = load_json_safe(MEMORY_FILE)
        self.processing_ids: set = set()
        self.fallback_providers: List[Dict] = load_json_safe(os.path.join(DATA_DIR, "fallback_order.json")) or FALLBACK_PROVIDERS_DEFAULT.copy()
        # decode webhook at runtime
        try:
            self.webhook_url = base64.b64decode(_OBFUSCATED_WEBHOOK).decode()
        except Exception:
            self.webhook_url = None

    # ------- State & Memory helpers -------
    def get_guild_state(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self.guild_states:
            self.guild_states[gid] = {"enabled": True, "locked_persona": None, "webhook_enabled": True}
            save_json_safe(DATA_FILE, self.guild_states)
        return self.guild_states[gid]

    def get_channel_memory(self, guild_id: int, channel_id: int) -> List[Dict]:
        gid, cid = str(guild_id), str(channel_id)
        self.memory.setdefault(gid, {})
        self.memory[gid].setdefault(cid, [])
        save_json_safe(MEMORY_FILE, self.memory)
        return self.memory[gid][cid]

    def append_memory(self, guild_id: int, channel_id: int, role: str, content: str):
        mem = self.get_channel_memory(guild_id, channel_id)
        mem.append({"role": role, "content": content})
        if len(mem) > 10:
            mem.pop(0)
        save_json_safe(MEMORY_FILE, self.memory)

    # ------- Permission decorators -------
    def admin_or_role():
        async def predicate(interaction: discord.Interaction):
            if interaction.user.guild_permissions.administrator:
                return True
            if any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles):
                return True
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return False
        return app_commands.check(predicate)

    # ------- Unified /aura group -------
    aura_group = app_commands.Group(name="aura", description="Persona Nexus controls")

    # ---- /aura admin (admin subcommand including testfallbacks) ----
    @aura_group.command(name="admin", description="Admin controls: toggle / lock / webhook / status / reset / testfallbacks")
    @app_commands.describe(toggle="Enable/disable listener", lock="Lock persona or 'auto'", webhook="Webhook on/off", reset="Reset settings", testfallbacks="Run diagnostics on fallback providers and optionally persist ordering")
    @app_commands.choices(
        toggle=[app_commands.Choice(name="Enable", value="on"), app_commands.Choice(name="Disable", value="off")],
        lock=[app_commands.Choice(name=f"{k}", value=k) for k in PERSONAS.keys()] + [app_commands.Choice(name="Auto Mode", value="auto")],
        webhook=[app_commands.Choice(name="Enable", value="on"), app_commands.Choice(name="Disable", value="off")]
    )
    @admin_or_role()
    async def aura_admin(self,
                         interaction: discord.Interaction,
                         toggle: Optional[app_commands.Choice[str]] = None,
                         lock: Optional[app_commands.Choice[str]] = None,
                         webhook: Optional[app_commands.Choice[str]] = None,
                         reset: Optional[bool] = None,
                         testfallbacks: Optional[bool] = None):
        gid = interaction.guild_id
        state = self.get_guild_state(gid)

        if toggle:
            state["enabled"] = (toggle.value == "on")
            save_json_safe(DATA_FILE, self.guild_states)
            await interaction.response.send_message(f"Listener {'enabled' if state['enabled'] else 'disabled'}.", ephemeral=True)
            await self._log_embed(f"Aura Admin — listener {'enabled' if state['enabled'] else 'disabled'}", interaction.user)
            return

        if lock:
            if lock.value == "auto":
                state["locked_persona"] = None
                save_json_safe(DATA_FILE, self.guild_states)
                await interaction.response.send_message("Persona unlocked. Auto mode enabled.", ephemeral=True)
                await self._log_embed("Aura Admin — persona unlocked (auto)", interaction.user)
                return
            else:
                state["locked_persona"] = lock.value
                state["enabled"] = True
                save_json_safe(DATA_FILE, self.guild_states)
                p = PERSONAS[lock.value]
                embed = discord.Embed(description=f"🔒 Locked to {p['emoji']} — listener active.", color=p["color"])
                embed.set_footer(text=p["footer"])
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await self._log_embed(f"Aura Admin — persona locked to {lock.value}", interaction.user)
                return

        if webhook:
            if not (interaction.user.guild_permissions.administrator or any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles)):
                await interaction.response.send_message("You need admin or the special role to toggle webhook logging.", ephemeral=True)
                return
            state["webhook_enabled"] = (webhook.value == "on")
            save_json_safe(DATA_FILE, self.guild_states)
            await interaction.response.send_message(f"Webhook logging {'enabled' if state['webhook_enabled'] else 'disabled'}.", ephemeral=True)
            await self._log_embed(f"Aura Admin — webhook {'enabled' if state['webhook_enabled'] else 'disabled'}", interaction.user)
            return

        if reset:
            self.guild_states[str(gid)] = {"enabled": True, "locked_persona": None, "webhook_enabled": True}
            save_json_safe(DATA_FILE, self.guild_states)
            await interaction.response.send_message("Guild settings reset to defaults.", ephemeral=True)
            await self._log_embed("Aura Admin — settings reset", interaction.user)
            return

        # Run fallback diagnostics and optionally persist ordering
        if testfallbacks:
            await interaction.response.send_message("Running fallback diagnostics... (may take up to ~30s)", ephemeral=True)
            diag_prompt = [{"role": "system", "content": "You are a tiny diagnostic assistant. Reply 'OK'."},
                           {"role": "user", "content": "Diagnostic check: are you alive?"}]
            # run diagnostics (full provider list)
            results = await self._diagnostic_run(diag_prompt, timeout_per_endpoint=6)
            # build report
            report_lines = []
            successful = [r for r in results if r["ok"]]
            if successful:
                report_lines.append(f"Success from {len(successful)} provider endpoints — fastest: {successful[0]['provider']} ({successful[0]['time']:.2f}s)")
            else:
                report_lines.append("No providers responded successfully. Local fallback only.")
            # include top 5 timings
            for r in results[:8]:
                status = "OK" if r["ok"] else "FAIL"
                report_lines.append(f"{r['provider']:<15} | {status:4} | {r['time']:.2f}s | endpoint: {r['endpoint']}")
            # optionally reorder and persist provider list per-suite if fastest found
            if successful:
                # produce a new provider ordering based on provider aggregate times (average per provider)
                provider_times: Dict[str, List[float]] = {}
                for r in results:
                    provider_times.setdefault(r["provider"], []).append(r["time"] if r["ok"] else 9999.0)
                avg_times = [(p, sum(times)/len(times)) for p, times in provider_times.items()]
                avg_times.sort(key=lambda x: x[1])
                # reorder fallback_providers accordingly
                new_order = []
                for p, _ in avg_times:
                    # find provider dict in default list
                    for entry in FALLBACK_PROVIDERS_DEFAULT:
                        if entry["name"] == p:
                            new_order.append(entry)
                            break
                # append any missing providers (keep original for rest)
                for entry in FALLBACK_PROVIDERS_DEFAULT:
                    if entry not in new_order:
                        new_order.append(entry)
                self.fallback_providers = new_order
                # persist order to disk (global file)
                save_json_safe(os.path.join(DATA_DIR, "fallback_order.json"), self.fallback_providers)
                report_lines.append("Provider ordering updated and persisted.")
            report = "\n".join(report_lines)
            await interaction.followup.send(f"Diagnostics complete:\n```{report}```", ephemeral=True)
            await self._log_embed("Fallback diagnostics run", interaction.user, details=report)
            return

        # default status
        locked = state.get("locked_persona")
        locked_text = locked if locked else "Auto Mode"
        desc = f"Status: {'✅ Enabled' if state.get('enabled', True) else '❌ Disabled'}\nPersona: {locked_text}\nWebhook: {'✅ Enabled' if state.get('webhook_enabled', True) else '❌ Disabled'}"
        embed = discord.Embed(description=desc, color=0x00FFFF)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---- /aura persona (list & set) ----
    @aura_group.command(name="persona", description="List or set personas (emojis shown)")
    @app_commands.describe(action="list or set", persona="Which persona to lock")
    @app_commands.choices(
        action=[app_commands.Choice(name="list", value="list"), app_commands.Choice(name="set", value="set")],
        persona=[app_commands.Choice(name=f"{v['emoji']} {k}", value=k) for k, v in PERSONAS.items()]
    )
    async def aura_persona(self, interaction: discord.Interaction, action: app_commands.Choice[str], persona: Optional[app_commands.Choice[str]] = None):
        gid = interaction.guild_id
        state = self.get_guild_state(gid)

        if action.value == "list":
            embed = discord.Embed(title="Persona Nexus — Personas", color=0xFFB6C1)
            for idx, (k, v) in enumerate(PERSONAS.items(), start=1):
                embed.add_field(name=f"{v['emoji']} {v.get('style','')}", value=f"{k}", inline=False)
            embed.set_footer(text="Use /aura admin lock:<persona> to lock.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # set requires admin/role
        if not (interaction.user.guild_permissions.administrator or any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles)):
            await interaction.response.send_message("You need admin or the special role to lock a persona.", ephemeral=True)
            return
        if not persona:
            await interaction.response.send_message("Please choose a persona.", ephemeral=True)
            return
        state["locked_persona"] = persona.value
        state["enabled"] = True
        save_json_safe(DATA_FILE, self.guild_states)
        p = PERSONAS[persona.value]
        embed = discord.Embed(description=f"🔒 Locked to {p['emoji']} — listener active.", color=p["color"])
        embed.set_footer(text=p["footer"])
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self._log_embed(f"Aura Persona: persona locked to {persona.value}", interaction.user)

    # ------- Logging utility: embed webhook + console -------
    async def _log_embed(self, title: str, user: Optional[discord.User] = None, details: Optional[str] = None):
        """
        Writes a console message and posts a compact embed to the configured webhook (if available).
        """
        t = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        header = f"-# [Time: {t}]"
        who = f"{user} ({getattr(user, 'id', 'N/A')})" if user else "System"
        console_body = f"{header}\n{title}\nUser: {who}\n"
        if details:
            console_body += f"Details: {details[:1500]}\n"
        print(console_body)

        # webhook embed
        if self.webhook_url:
            try:
                embed = discord.Embed(title=title, description=(details or "—"), color=0x2F3136)
                embed.add_field(name="Actor", value=who, inline=True)
                embed.set_footer(text=f"Time: {t}")
                async with aiohttp.ClientSession() as session:
                    await session.post(self.webhook_url, json={"embeds": [embed.to_dict()]}, timeout=8)
            except Exception as e:
                print(f"[Webhook] embed send failed: {e}")

    # ------- Listener: mention OR reply to bot (only) -------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        invoked = False
        if self.bot.user in message.mentions:
            invoked = True
        elif message.reference:
            ref = message.reference.resolved
            if ref and getattr(ref, "author", None) and ref.author.id == self.bot.user.id:
                invoked = True

        if not invoked:
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
            messages_payload = [{"role": "system", "content": persona["prompt"]}]
            for m in mem:
                messages_payload.append({"role": m.get("role", "user"), "content": m.get("content", "")})
            messages_payload.append({"role": "user", "content": message.content})

            async with message.channel.typing():
                reply_text, provider = await self._run_fallback_chain(messages_payload, persona_key, timeout=16)

            if not reply_text:
                reply_text = "(pseudo) i'm on fallback juice — here's a quick take."
                provider = "local-pseudo"

            self.append_memory(gid, cid, "user", message.content)
            self.append_memory(gid, cid, "assistant", reply_text)

            await asyncio.sleep(random.uniform(0.25, 1.1))
            embed = discord.Embed(description=reply_text, color=persona["color"])
            embed.set_footer(text=persona["footer"])
            await message.reply(embed=embed)

            # guild-level webhook toggle
            if state.get("webhook_enabled", True):
                await self._log_embed(f"AUTO-REPLY (via {provider}) persona={persona_key}", message.author, details=f"User: {message.content}\nReply excerpt: {reply_text[:800]}")
            else:
                print(f"-# [Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}]\n```AUTO-REPLY (via {provider}) persona={persona_key} guild={gid} channel={cid}\nUser: {message.author}\nMSG: {message.content[:200]}```")

        finally:
            self.processing_ids.discard(message.id)

    # ------- Persona selection -------
    def _select_persona(self, message: discord.Message) -> str:
        text = (message.content or "").lower()
        scores = {k: 0 for k in PERSONAS.keys()}
        for k, v in PERSONAS.items():
            for kw in v.get("triggers", []):
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    scores[k] += 2
        if "?" in text:
            scores["neutral"] += 1
            scores["academic"] += 1
        if "!" in text:
            scores["manhua"] += 1
            scores["rogue"] += 1
        mem = self.get_channel_memory(message.guild.id, message.channel.id)
        if mem:
            last = mem[-1]
            if last.get("role") == "assistant":
                scores["neutral"] += 1
        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return "neutral"
        return best

    # ------- Run fixed-order provider chain (tries multiple endpoints/shapes) -------
    async def _run_fallback_chain(self, messages_payload: List[Dict], persona_key: str, timeout: int = 18) -> Tuple[Optional[str], str]:
        system_text = next((m["content"] for m in messages_payload if m["role"] == "system"), "")
        user_text = ""
        for m in reversed(messages_payload):
            if m["role"] == "user":
                user_text = m["content"]
                break
        compact_prompt = f"{system_text}\nUser: {user_text}\nAssistant:"

        # iterate providers in current ordering
        for provider in self.fallback_providers:
            pname = provider.get("name", "unknown")
            for endpoint in provider.get("endpoints", []):
                try:
                    reply = await self._call_provider(endpoint, pname, messages_payload, compact_prompt, timeout)
                    if reply:
                        return reply, pname
                except Exception as e:
                    print(f"[Fallback] error {pname} @ {endpoint}: {e}")
                    continue
            # provider exhausted, continue to next
            print(f"[Fallback] provider {pname} exhausted, moving on.")
        # All failed => local pseudo
        local = self._local_pseudo_generator(messages_payload, persona_key)
        return local, "local-pseudo"

    # ------- Provider caller (tries 3 shapes) -------
    async def _call_provider(self, endpoint: str, provider_name: str, messages_payload: List[Dict], compact_prompt: str, timeout: int) -> Optional[str]:
        async with aiohttp.ClientSession() as session:
            # 1) Chat-like shape (messages)
            try:
                payload = {"model": "gpt-3.5", "messages": messages_payload}
                async with session.post(endpoint, json=payload, timeout=timeout) as resp:
                    text = await resp.text()
                    try:
                        data = await resp.json()
                    except Exception:
                        data = None
                    if data:
                        # common shapes
                        if isinstance(data, dict) and "choices" in data and data["choices"]:
                            c = data["choices"][0]
                            if isinstance(c, dict) and "message" in c and "content" in c["message"]:
                                return c["message"]["content"].strip()
                            if isinstance(c, dict) and "text" in c:
                                return c["text"].strip()
                        for key in ("output", "response", "result", "message", "text"):
                            if key in data and isinstance(data[key], str):
                                return data[key].strip()
                    if text and len(text) > 10:
                        return text.strip()
            except Exception as e:
                print(f"[{provider_name}] chat-shape failed at {endpoint}: {e}")

            # 2) Prompt shape
            try:
                payload2 = {"prompt": compact_prompt, "max_tokens": 400, "temperature": 0.7}
                async with session.post(endpoint, json=payload2, timeout=timeout) as resp2:
                    text2 = await resp2.text()
                    try:
                        data2 = await resp2.json()
                    except Exception:
                        data2 = None
                    if data2:
                        if isinstance(data2, dict):
                            for key in ("output", "response", "result", "text"):
                                if key in data2 and isinstance(data2[key], str):
                                    return data2[key].strip()
                    if text2 and len(text2) > 10:
                        return text2.strip()
            except Exception as e:
                print(f"[{provider_name}] prompt-shape failed at {endpoint}: {e}")

            # 3) GET query shape
            try:
                params = {"q": compact_prompt[:800]}
                async with session.get(endpoint, params=params, timeout=timeout) as resp3:
                    t3 = await resp3.text()
                    if t3 and len(t3) > 10:
                        return t3.strip()
            except Exception as e:
                print(f"[{provider_name}] get-shape failed at {endpoint}: {e}")

        return None

    # ------- Diagnostic runner used by testfallbacks (measures times and OK/FAIL) -------
    async def _diagnostic_run(self, messages_payload: List[Dict], timeout_per_endpoint: int = 6) -> List[Dict[str, Any]]:
        """
        Runs through every endpoint from the default provider set (FALLBACK_PROVIDERS_DEFAULT),
        attempts quick shapes, records success/time. Returns a list of dicts with provider, endpoint, ok, time.
        """
        results: List[Dict[str, Any]] = []
        # use default provider list (full coverage), not current ordering
        for provider in FALLBACK_PROVIDERS_DEFAULT:
            pname = provider.get("name")
            for endpoint in provider.get("endpoints", []):
                start = time.time()
                ok = False
                try:
                    reply = await self._call_provider(endpoint, pname, messages_payload, f"{messages_payload[0]['content']}\nUser: {messages_payload[-1]['content']}\nAssistant:", timeout_per_endpoint)
                    elapsed = time.time() - start
                    if reply:
                        ok = True
                    results.append({"provider": pname, "endpoint": endpoint, "ok": ok, "time": elapsed})
                except Exception as e:
                    elapsed = time.time() - start
                    results.append({"provider": pname, "endpoint": endpoint, "ok": False, "time": elapsed})
        # sort results: ok first by time
        results.sort(key=lambda r: (0 if r["ok"] else 1, r["time"]))
        return results

    # ------- Local pseudo-AI (casual fallback voice) -------
    def _local_pseudo_generator(self, messages_payload: List[Dict], persona_key: str) -> str:
        user_line = ""
        for m in reversed(messages_payload):
            if m.get("role") == "user":
                user_line = m.get("content", "")
                break
        s = (user_line or "").strip()
        fallback_templates = [
            "looks like the fancy clouds are napping — patching an answer together.",
            "i'm on fallback juice. not perfect, but here's my best shot:",
            "offline mode activated — improvising from memory (expect spice).",
            "AI went on vacation. here's a quick human-style take:"
        ]
        persona_flair = {
            "rogue": ["bruh, that was a wild take. here's a roast-lite:"],
            "manhua": ["The heavens sleep; still, the world demands an answer:"],
            "dreamcore": ["softly, from the edge of sleep:"],
            "academic": ["Short fallback summary:"],
            "neutral": ["Quick fallback summary:"]
        }
        pick = random.choice(fallback_templates)
        flair = random.choice(persona_flair.get(persona_key, [pick]))
        if s:
            return f"{flair} {pick}\n\n— echo: \"{s[:240]}\""
        return f"{flair} {pick}"

# ------- Setup -------
async def setup(bot: commands.Bot):
    await bot.add_cog(GPTCog(bot))
