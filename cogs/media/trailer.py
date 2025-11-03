# trailer_cog.py
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import typing
import html
import logging
import traceback
import unicodedata
import urllib.parse
import re
from cogs_test.general_commands.dashboard import command_meta

ANILIST_API_URL = "https://graphql.anilist.co"

# --- logger setup (prints to terminal, includes timestamps) ---
logger = logging.getLogger("trailer_cog")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG)  # set to INFO in prod if too noisy

# --- helpers ---
def build_trailer_url(site: typing.Optional[str], trailer_id: typing.Optional[str]) -> typing.Optional[str]:
    if not site or not trailer_id:
        return None
    site_lower = site.lower()
    if "youtube" in site_lower or "yt" in site_lower:
        return f"https://youtu.be/{trailer_id}"
    if "dailymotion" in site_lower or "dm" in site_lower:
        return f"https://www.dailymotion.com/video/{trailer_id}"
    return None

def normalize_variants(title: str) -> typing.List[str]:
    """Return progressive variants to try for best matching (original, ascii, cleaned, short)."""
    title = title.strip()
    variants = []
    if title:
        variants.append(title)

    # NFKD normalize & strip diacritics (Pokémon -> Pokemon)
    nfkd = unicodedata.normalize("NFKD", title)
    ascii_title = "".join(c for c in nfkd if not unicodedata.combining(c))
    if ascii_title and ascii_title not in variants:
        variants.append(ascii_title)

    # remove common noise words like 'trailer', 'official', 'animated', etc.
    cleaned = re.sub(r"\b(trailer|teaser|pv|official|animated|animation|movie|ost)\b", " ", ascii_title, flags=re.I)
    cleaned = re.sub(r"[^0-9A-Za-z\s]", " ", cleaned)  # remove weird punctuation
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and cleaned not in variants:
        variants.append(cleaned)

    # also try cleaned form from original (in case ascii changed representation matters)
    cleaned2 = re.sub(r"\b(trailer|teaser|pv|official|animated|animation|movie|ost)\b", " ", title, flags=re.I)
    cleaned2 = re.sub(r"\s+", " ", cleaned2).strip()
    if cleaned2 and cleaned2 not in variants:
        variants.append(cleaned2)

    # short variant (first few words) as last resort
    words = title.split()
    if len(words) > 4:
        short = " ".join(words[:4])
        if short and short not in variants:
            variants.append(short)

    # ensure unique order preserved
    seen = set()
    out = []
    for v in variants:
        if v and v.lower() not in seen:
            out.append(v)
            seen.add(v.lower())
    return out

# --- Cog ---
class TrailerCog(commands.Cog):
    """Trailer command: fetches AniList trailers for anime/manga, with robust fallback and terminal tracebacks"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        try:
            asyncio.create_task(self.session.close())
        except RuntimeError:
            pass

    # Primary GraphQL query
    async def query_anilist(self, title: str, mtype: str, limit: int = 5):
        query = """
        query ($search: String, $type: MediaType, $limit: Int) {
          Page(perPage: $limit) {
            media(search: $search, type: $type) {
              id
              title { romaji english native }
              siteUrl
              isAdult
              popularity
              trailer { id site }
            }
          }
        }
        """
        variables = {"search": title, "type": mtype.upper(), "limit": limit}
        try:
            async with self.session.post(ANILIST_API_URL, json={"query": query, "variables": variables}, timeout=15) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logger.error("GraphQL non-200 response for search '%s' (type=%s): %s", title, mtype, resp.status)
                    logger.debug("Response body: %s", text[:1000])
                    return None
                try:
                    data = await self.session._loop.run_in_executor(None, lambda: __import__("json").loads(text))
                except Exception:
                    # fallback json loads if library can't parse via resp.json
                    data = None
                if data is None:
                    # attempt resp.json() safely
                    try:
                        data = await (await self.session.post(ANILIST_API_URL, json={"query": query, "variables": variables})).json()
                    except Exception as e:
                        logger.error("Failed to decode JSON for GraphQL response: %s", e)
                        logger.debug("Raw response: %s", text[:2000])
                        return None
                media = data.get("data", {}).get("Page", {}).get("media", [])
                logger.debug("GraphQL returned %d items for query '%s'", len(media) if media else 0, title)
                return media
        except Exception:
            logger.error("Exception while querying AniList GraphQL for '%s' (type=%s):", title, mtype)
            traceback.print_exc()
            return None

    # fallback: scrape AniList search page for first ID, then fetch Media by id
    async def fallback_parse(self, title: str, mtype: str):
        try:
            encoded = urllib.parse.quote_plus(title)
            search_url = f"https://anilist.co/search/{mtype.lower()}?search={encoded}"
            logger.info("Fallback: fetching AniList search page: %s", search_url)
            async with self.session.get(search_url, timeout=15) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logger.error("Fallback search page returned status %s for URL %s", resp.status, search_url)
                    logger.debug("Fallback page snippet: %s", text[:1000])
                    return None
                # parse for /anime/<id> or /manga/<id>
                match = re.search(rf"/{mtype.lower()}/(\d+)", text)
                if not match:
                    logger.debug("Fallback parse: no id match for title '%s' on search page", title)
                    return None
                anilist_id = match.group(1)
                logger.info("Fallback parse: got ID %s for title '%s'", anilist_id, title)

                # fetch Media by ID (GraphQL)
                query = """
                query ($id: Int) {
                  Media(id: $id) {
                    id
                    title { romaji english native }
                    siteUrl
                    isAdult
                    popularity
                    trailer { id site url }
                  }
                }
                """
                variables = {"id": int(anilist_id)}
                async with self.session.post(ANILIST_API_URL, json={"query": query, "variables": variables}, timeout=15) as resp2:
                    text2 = await resp2.text()
                    if resp2.status != 200:
                        logger.error("Fallback GraphQL by ID returned %s for id %s", resp2.status, anilist_id)
                        logger.debug("Response body: %s", text2[:1000])
                        return None
                    try:
                        data = await resp2.json()
                    except Exception:
                        logger.error("Failed to parse JSON for fallback GraphQL response (id=%s).", anilist_id)
                        logger.debug("Raw body: %s", text2[:2000])
                        return None
                    media = data.get("data", {}).get("Media")
                    if media:
                        logger.debug("Fallback GraphQL returned media id %s", media.get("id"))
                        return [media]
                    return None
        except Exception:
            logger.error("Exception in fallback_parse for title '%s' (type=%s):", title, mtype)
            traceback.print_exc()
            return None

    # tries multiple normalized variants and uses GraphQL first then fallback_parse
    async def search_with_fallback(self, title: str, mtype: str, debug: bool = False):
        variants = normalize_variants(title)
        logger.debug("Normalized variants to try: %s", variants)
        for variant in variants:
            logger.info("Trying GraphQL for '%s' (type=%s)", variant, mtype)
            try:
                media_list = await self.query_anilist(variant, mtype, limit=6)
            except Exception:
                logger.error("Exception during query_anilist for '%s'", variant)
                traceback.print_exc()
                media_list = None

            # GraphQL returned non-empty list -> done
            if media_list:
                logger.info("GraphQL found %d results for '%s'", len(media_list), variant)
                return media_list, "GraphQL", variant

            # If GraphQL explicitly failed (None) or empty list, try fallback parse
            logger.info("GraphQL returned no results for '%s' — trying fallback parse", variant)
            try:
                fb = await self.fallback_parse(variant, mtype)
            except Exception:
                logger.error("Exception during fallback_parse for '%s'", variant)
                traceback.print_exc()
                fb = None
            if fb:
                logger.info("Fallback parse returned %d result(s) for '%s'", len(fb), variant)
                return fb, "Fallback Web Parse", variant

        # nothing found
        logger.info("No results found after trying all variants for '%s'", title)
        return None, None, None

    # autocomplete respects type
    async def autocomplete_titles(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
        if not current:
            return []
        selected_type = "ANIME"
        try:
            ns = getattr(interaction, "namespace", {})
            if ns and "type" in ns and ns["type"]:
                selected_type = ns["type"].value
        except Exception:
            pass
        results = await self.query_anilist(current, selected_type, limit=5)
        if not results:
            return []
        choices = []
        for m in results[:5]:
            t = m.get("title", {})
            eng = t.get("english")
            romaji = t.get("romaji")
            display = eng if eng else romaji if romaji else "Unknown"
            if eng and romaji and eng != romaji:
                display = f"{eng} ({romaji})"
            choices.append(app_commands.Choice(name=display[:100], value=display))
        return choices

    @app_commands.command(name="trailer", description="🎬 Get the trailer for an anime/manga from AniList")
    @command_meta(section="Media", name="Trailer")
    @app_commands.describe(
        type="Choose whether it's anime or manga",
        title="The title to search for",
        debug="Show extra info (AniList link, method used, etc.)",
        allow_nsfw="Include NSFW results (off by default)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="anime", value="ANIME"),
        app_commands.Choice(name="manga", value="MANGA"),
    ])
    @app_commands.autocomplete(title=autocomplete_titles)
    async def trailer(self, interaction: discord.Interaction, type: app_commands.Choice[str], title: str, debug: bool = False, allow_nsfw: bool = False):
        # note: we defer early so we can use followup.send later
        await interaction.response.defer(thinking=True)

        # search (GraphQL first, fallback web parse otherwise) and which variant was used
        media_list, method_used, used_query = await self.search_with_fallback(title, type.value, debug=debug)

        if not media_list:
            # simple, no-type message (user requested removing the "type: anime" bit)
            await interaction.followup.send(f"⚠️ No results found for **{title}**.", ephemeral=True)
            return

        # filter NSFW if not allowed
        filtered = [m for m in media_list if (allow_nsfw or not m.get("isAdult"))]
        if not filtered:
            await interaction.followup.send(f"⚠️ No results found for **{title}** (NSFW filtered).", ephemeral=True)
            return

        # multiple matches -> show a select menu (ephemeral so channel isn't spammed)
        if len(filtered) > 1:
            options = []
            for m in filtered[:6]:
                t = m.get("title", {})
                eng = t.get("english")
                romaji = t.get("romaji")
                pretty = eng if eng else romaji if romaji else "Unknown"
                options.append(discord.SelectOption(label=pretty[:100], description=f"AniList ID: {m.get('id')}", value=str(m.get("id"))))

            parent_interaction = interaction  # preserve original interaction to post the final trailer publicly

            class SelectMenu(discord.ui.View):
                def __init__(self, parent_cog: "TrailerCog", media_list: typing.List[dict], debug_flag: bool, allow_nsfw_flag: bool, parent_inter: discord.Interaction, method_used_str: str):
                    super().__init__(timeout=30)
                    self.parent_cog = parent_cog
                    self.media_map = {str(m["id"]): m for m in media_list}
                    self.debug = debug_flag
                    self.allow_nsfw = allow_nsfw_flag
                    self.parent_interaction = parent_inter
                    self.method_used = method_used_str

                @discord.ui.select(placeholder="Choose the correct title…", options=options, min_values=1, max_values=1)
                async def select_callback(self, interaction2: discord.Interaction, select: discord.ui.Select):
                    # acknowledge the select
                    try:
                        await interaction2.response.defer(thinking=True, ephemeral=True)
                    except Exception:
                        # fallback: print traceback but continue
                        logger.exception("Failed to defer select interaction")
                    selected_id = select.values[0]
                    chosen_m = self.media_map.get(selected_id)
                    if not chosen_m:
                        await interaction2.followup.send("⚠️ Selected item not found (internal).", ephemeral=True)
                        return
                    # send trailer publicly via the original parent_interaction (so channel receives the raw URL)
                    await self.parent_cog.send_trailer(public_interaction=self.parent_interaction, chosen=chosen_m, debug=self.debug, method=self.method_used)

            view = SelectMenu(self, filtered, debug, allow_nsfw, parent_interaction, method_used or "GraphQL/Fallback")
            await interaction.followup.send("🔎 Multiple results found. Choose the correct entry (only you can see this):", view=view, ephemeral=True)
            return

        # only one match — post trailer
        chosen = filtered[0]
        await self.send_trailer(public_interaction=interaction, chosen=chosen, debug=debug, method=method_used or "GraphQL/Fallback")

    async def send_trailer(self, public_interaction: discord.Interaction, chosen: dict, debug: bool, method: str):
        """Sends the trailer via public_interaction.followup.send (public unless ephemeral=True passed)."""
        try:
            trailer = chosen.get("trailer")
            trailer_url = (trailer.get("url") if trailer else None) or build_trailer_url((trailer.get("site") if trailer else None), (trailer.get("id") if trailer else None))
            if not trailer_url:
                # ephemeral failure
                await public_interaction.followup.send("⚠️ No trailer found.", ephemeral=True)
                return

            if debug:
                title_obj = chosen.get("title", {})
                pretty_title = title_obj.get("english") or title_obj.get("romaji") or title_obj.get("native") or "Unknown"
                site_url = chosen.get("siteUrl")
                embed = discord.Embed(
                    title=f"🎬 Trailer — {html.unescape(pretty_title)}",
                    description=f"[AniList Page]({site_url})\n\n📺 Method used: **{method}**",
                    color=0xE75480
                )
                # show embed publicly (then raw URL publicly)
                await public_interaction.followup.send(embed=embed)
            # send raw URL publicly so Discord auto-embeds the player
            await public_interaction.followup.send(trailer_url)
        except Exception:
            logger.error("Exception while sending trailer message:")
            traceback.print_exc()
            # send ephemeral error to user so channel isn't spammed
            try:
                await public_interaction.followup.send("⚠️ Error sending trailer.", ephemeral=True)
            except Exception:
                logger.exception("Also failed to send ephemeral error followup.")

async def setup(bot: commands.Bot):
    await bot.add_cog(TrailerCog(bot))
