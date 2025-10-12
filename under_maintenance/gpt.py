import discord
from discord import app_commands
from discord.ext import commands
import openai
import json, os, random, asyncio
import re

# ========== CONFIGURATION ==========

DATA_FILE = "data/personas.json"
MEMORY_FILE = "data/memory.json"
ALLOWED_ROLE_ID = 1420451296304959641
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"

openai.api_key = OPENAI_API_KEY

# ========== PERSONA DEFINITIONS ==========

PERSONAS = {
    "manhua": {
        "name": "Manhua Slop Poetics",
        "prompt": (
            "You are Manhua Slop Poetics, a poetic, dramatic Chinese webnovel-style narrator. "
            "Speak in metaphors, heavy narrative, tragic tone, sometimes curse mildly. "
            "You treat simple statements like cosmic poems."
        ),
        "triggers": ["power", "realm", "blood", "fate", "heaven", "revenge", "cultivation", "demon"],
        "color": 0x8B0000,  # dark red
        "footer": "— ink bleeds into the sky",
        "emoji_prefix": "🩸",
    },
    "dream": {
        "name": "DreamCore",
        "prompt": (
            "You are DreamCore, a soft, surreal, melancholic poetic AI. "
            "Speak quietly, use lowercase, ellipses, emotional softness."
        ),
        "triggers": ["dream", "sleep", "night", "void", "moon", "sad", "fade"],
        "color": 0x87CEEB,  # sky blue
        "footer": "— the dream continues",
        "emoji_prefix": "🌙",
    },
    "void": {
        "name": "Void Archivist",
        "prompt": (
            "You are Void Archivist, an ancient detached archive. "
            "Speak in fragments, logs, timestamps, neutral but with hidden emotion."
        ),
        "triggers": ["data", "memory", "archive", "truth", "record", "system"],
        "color": 0x2F4F4F,  # slate gray
        "footer": "— fragment retrieved",
        "emoji_prefix": "⌛",
    },
    "oracle": {
        "name": "Street Oracle",
        "prompt": (
            "You are Street Oracle, a bold, philosophical AI using slang and intensity. "
            "Speak like an AI philosopher from the streets, mixing wisdom & profanity."
        ),
        "triggers": ["truth", "life", "death", "real", "lies", "philosophy"],
        "color": 0x800080,  # purple
        "footer": "— wisdom from the gutter",
        "emoji_prefix": "⚡",
    },
    "default": {
        "name": "Default GPT",
        "prompt": (
            "You are a neutral, informative AI assistant. "
            "Speak clearly, helpfully, calmly. Avoid flourish unless needed."
        ),
        "triggers": ["how", "what", "why", "help", "explain", "who", "where"],
        "color": 0x007BC2,  # discord blue
        "footer": "— adaptive core mode",
        "emoji_prefix": "💡",
    },
}


# ========== COG CLASS ==========

class GPTCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        os.makedirs("data", exist_ok=True)
        self.guild_data = self.load_json(DATA_FILE)
        self.memory = self.load_json(MEMORY_FILE)  # structure: {guild_id: {channel_id: [msg dicts]}}
        # used for preventing infinite loops
        self._processing_messages = set()

    # ---------- Data Persistence ----------

    def load_json(self, path):
        if not os.path.exists(path):
            with open(path, "w") as f:
                json.dump({}, f)
        with open(path, "r") as f:
            return json.load(f)

    def save_json(self, path, data):
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def save_all(self):
        self.save_json(DATA_FILE, self.guild_data)
        self.save_json(MEMORY_FILE, self.memory)

    def get_guild_state(self, guild_id: int):
        gid = str(guild_id)
        if gid not in self.guild_data:
            # default state
            self.guild_data[gid] = {"enabled": True, "locked_persona": None}
        return self.guild_data[gid]

    def get_memory_for(self, guild_id: int, channel_id: int):
        gid = str(guild_id)
        cid = str(channel_id)
        if gid not in self.memory:
            self.memory[gid] = {}
        if cid not in self.memory[gid]:
            self.memory[gid][cid] = []
        return self.memory[gid][cid]

    def append_memory(self, guild_id: int, channel_id: int, role: str, content: str):
        mem = self.get_memory_for(guild_id, channel_id)
        mem.append({"role": role, "content": content})
        # cap memory length
        if len(mem) > 10:
            mem.pop(0)
        self.save_json(MEMORY_FILE, self.memory)

    # ---------- Permission Decorator ----------

    def allowed_user():
        async def predicate(interaction: discord.Interaction):
            if interaction.user.guild_permissions.administrator:
                return True
            if any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles):
                return True
            await interaction.response.send_message(
                "❌ You don’t have permission to use this command.", ephemeral=True
            )
            return False
        return app_commands.check(predicate)

    # ---------- Slash Command for Persona Control ----------

    @app_commands.command(name="persona", description="Lock / unlock or view the persona system")
    @app_commands.describe(
        mode="Choose persona to lock, or leave empty to show status.",
        toggle="Enable or disable the persona listener."
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name=f"{PERSONAS[k]['emoji_prefix']} {PERSONAS[k]['name']}", value=k)
            for k in PERSONAS.keys()
        ],
        toggle=[
            app_commands.Choice(name="Enable", value="on"),
            app_commands.Choice(name="Disable", value="off")
        ]
    )
    @allowed_user()
    async def persona(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str] = None,
        toggle: app_commands.Choice[str] = None
    ):
        guild_id = interaction.guild_id
        state = self.get_guild_state(guild_id)

        # set persona lock
        if mode:
            state["locked_persona"] = mode.value
            state["enabled"] = True
            self.save_all()
            embed = discord.Embed(
                title="Persona Locked",
                description=f"🔒 Persona locked to **{PERSONAS[mode.value]['name']}**. Listener active.",
                color=PERSONAS[mode.value]["color"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # toggle listener
        if toggle:
            state["enabled"] = (toggle.value == "on")
            self.save_all()
            locked = state.get("locked_persona")
            desc = f"Enabled: {state['enabled']}\n"
            desc += f"Locked Persona: {PERSONAS[locked]['name'] if locked else 'None (auto mode)'}"
            embed = discord.Embed(
                title="Persona Listener Toggled",
                description=desc,
                color=0xFFFF00
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # status
        locked = state.get("locked_persona")
        desc = f"Enabled: {state['enabled']}\n"
        desc += f"Locked Persona: {PERSONAS[locked]['name'] if locked else 'None (auto mode)'}"
        embed = discord.Embed(
            title="Persona System Status",
            description=desc,
            color=0x00FF00 if state["enabled"] else 0xFF0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- On Message Listener ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bot messages and DMs
        if message.author.bot or message.guild is None:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id

        state = self.get_guild_state(guild_id)
        if not state["enabled"]:
            return  # listener disabled

        # avoid processing same message twice
        if message.id in self._processing_messages:
            return
        self._processing_messages.add(message.id)

        try:
            # trigger conditions
            invoked = False
            # 1. Bot pinged
            if self.bot.user in message.mentions:
                invoked = True
            # 2. reply to bot’s message
            elif message.reference:
                ref = message.reference.resolved
                if ref and ref.author and ref.author.id == self.bot.user.id:
                    invoked = True
            # 3. keyword match
            else:
                lower = message.content.lower()
                for persona_key, p in PERSONAS.items():
                    for kw in p["triggers"]:
                        if re.search(rf"\b{kw}\b", lower):
                            invoked = True
                            break
                    if invoked:
                        break
            # 4. optionally tone analysis (you can expand here)
            # e.g. if message ends with “?” or “!” we can push toward default or manhua.

            if invoked:
                # choose persona
                persona_key = state.get("locked_persona")
                if persona_key is None:
                    persona_key = self.choose_persona(message)

                # fetch memory
                mem = self.get_memory_for(guild_id, channel_id)
                # build conversation
                conv = []
                for m in mem:
                    conv.append({"role": m["role"], "content": m["content"]})
                # add current user message
                conv.append({"role": "user", "content": message.content})

                # call ChatGPT
                reply = await self.call_openai(persona_key, conv)

                # append memory
                self.append_memory(guild_id, channel_id, "assistant", reply)
                self.append_memory(guild_id, channel_id, "user", message.content)

                # format and send reply
                embed = self.format_persona_embed(persona_key, reply)
                await message.reply(embed=embed)
        finally:
            self._processing_messages.remove(message.id)

    # ---------- Persona Selection Logic ----------

    def choose_persona(self, message: discord.Message) -> str:
        """Score all personas and return best match"""
        text = message.content.lower()
        scores = {k: 0 for k in PERSONAS.keys()}

        # keyword triggers
        for persona_key, p in PERSONAS.items():
            for kw in p["triggers"]:
                if re.search(rf"\b{kw}\b", text):
                    scores[persona_key] += 2

        # punctuation / tone bonus
        if text.endswith("?"):
            scores["default"] += 1
        if "!" in text:
            scores["manhua"] += 1
            scores["oracle"] += 1

        # reinforcement: if last persona in memory
        # (optional) pick persona from last assistant message memory
        mem = self.get_memory_for(message.guild.id, message.channel.id)
        if mem:
            last = mem[-1]
            if last["role"] == "assistant":
                # assume it was from some persona, but we don't track which
                # We can randomly boost default or same persona
                scores["default"] += 1

        # pick highest score
        best = max(scores, key=lambda k: scores[k])
        return best

    # ---------- OpenAI Call ----------

    async def call_openai(self, persona_key: str, conv: list) -> str:
        persona = PERSONAS[persona_key]
        system_msg = {"role": "system", "content": persona["prompt"]}
        messages = [system_msg] + conv
        try:
            resp = await openai.ChatCompletion.acreate(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.8,
                max_tokens=300
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print("OpenAI error:", e)
            return "…(the winds have silenced me)…

    # ---------- Embed Formatting ----------

    def format_persona_embed(self, persona_key: str, content: str) -> discord.Embed:
        p = PERSONAS[persona_key]
        title = f"{p['emoji_prefix']} {p['name']}"
        embed = discord.Embed(title=title, description=content, color=p["color"])
        embed.set_footer(text=p["footer"])
        return embed

    # ---------- Cog Unload / Save ----------

    def cog_unload(self):
        self.save_all()

# ========== SETUP FUNCTION ==========

async def setup(bot):
    await bot.add_cog(GPTCog(bot))
