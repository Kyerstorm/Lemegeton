export interface SteamProfile {
  steamId: string;
  personaName: string;
  profileUrl: string;
  avatar: string | null;
  visibility: "public" | "private" | "unknown";
  createdAt: number | null;
  gameCount: number | null;
  recentlyPlayed: Array<{ appId: number; name: string; minutes: number; icon: string | null }>;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
export function validateSteamId(value: string): string | null {
  const id = value.trim();
  return /^\d{17}$/.test(id) ? id : null;
}

export class SteamClient {
  constructor(private readonly apiKey?: string) {}

  async resolveSteamId(input: string): Promise<string> {
    const direct = validateSteamId(input);
    if (direct) return direct;
    if (!this.apiKey) throw new Error("Steam linking is unavailable because STEAM_API_KEY is not configured.");
    const vanity = input.trim().replace(/^https?:\/\/(www\.)?steamcommunity\.com\/id\//i, "").replace(/\/$/, "");
    if (!/^[A-Za-z0-9_-]{2,64}$/.test(vanity)) throw new Error("Enter a valid SteamID64 or Steam vanity name.");
    const url = new URL("https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/");
    url.searchParams.set("key", this.apiKey);
    url.searchParams.set("vanityurl", vanity);
    const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
    if (!response.ok) throw new Error(`Steam returned HTTP ${response.status} while resolving that profile.`);
    const result = record(record(await response.json())?.response);
    if (result?.success !== 1 || typeof result.steamid !== "string" || !validateSteamId(result.steamid)) {
      throw new Error("Steam could not resolve that vanity name.");
    }
    return result.steamid;
  }

  async getProfile(steamId: string): Promise<SteamProfile> {
    if (!this.apiKey) throw new Error("Steam profile lookup is unavailable because STEAM_API_KEY is not configured.");
    if (!validateSteamId(steamId)) throw new Error("SteamID64 is invalid.");
    const url = new URL("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/");
    url.searchParams.set("key", this.apiKey);
    url.searchParams.set("steamids", steamId);
    const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
    if (!response.ok) throw new Error(`Steam returned HTTP ${response.status}.`);
    const body = record(record(record(await response.json())?.response)?.players);
    const player = Array.isArray(body) ? record(body[0]) : null;
    if (!player || typeof player.steamid !== "string") throw new Error("Steam did not return a profile for that account.");
    const state = player.communityvisibilitystate;
    const visibility = state === 3 ? "public" : state === 1 || state === 2 ? "private" : "unknown";
    let gameCount: number | null = null;
    let recentlyPlayed: SteamProfile["recentlyPlayed"] = [];
    if (visibility === "public") {
      const [owned, recent] = await Promise.all([
        this.getService("IPlayerService/GetOwnedGames/v1/", steamId, true),
        this.getService("IPlayerService/GetRecentlyPlayedGames/v1/", steamId),
      ]);
      const ownedResponse = record(record(owned)?.response);
      const recentResponse = record(record(recent)?.response);
      gameCount = typeof ownedResponse?.game_count === "number" ? ownedResponse.game_count : null;
      recentlyPlayed = (Array.isArray(recentResponse?.games) ? recentResponse.games : []).flatMap((item) => {
        const game = record(item);
        if (!game || typeof game.appid !== "number" || typeof game.name !== "string") return [];
        return [{
          appId: game.appid,
          name: game.name,
          minutes: typeof game.playtime_2weeks === "number" ? game.playtime_2weeks : 0,
          icon: typeof game.img_icon_url === "string" && game.img_icon_url
            ? `https://media.steampowered.com/steamcommunity/public/images/apps/${game.appid}/${game.img_icon_url}.jpg`
            : null,
        }];
      }).slice(0, 5);
    }
    return {
      steamId: player.steamid,
      personaName: typeof player.personaname === "string" ? player.personaname : "Steam user",
      profileUrl: `https://steamcommunity.com/profiles/${player.steamid}`,
      avatar: typeof player.avatarfull === "string" && player.avatarfull.startsWith("https://") ? player.avatarfull : null,
      visibility,
      createdAt: typeof player.timecreated === "number" ? player.timecreated : null,
      gameCount,
      recentlyPlayed,
    };
  }

  private async getService(path: string, steamId: string, includeOwned = false): Promise<unknown> {
    const url = new URL(`https://api.steampowered.com/${path}`);
    url.searchParams.set("key", this.apiKey!);
    url.searchParams.set("steamid", steamId);
    if (includeOwned) {
      url.searchParams.set("include_appinfo", "1");
      url.searchParams.set("include_played_free_games", "1");
    } else {
      url.searchParams.set("count", "5");
    }
    const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
    if (!response.ok) return null;
    return response.json();
  }
}
