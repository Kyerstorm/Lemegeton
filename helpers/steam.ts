export interface SteamProfile {
  steamId: string;
  personaName: string;
  profileUrl: string;
  avatar: string | null;
  visibility: "public" | "private" | "unknown";
  createdAt: number | null;
  gameCount: number | null;
  totalPlaytimeMinutes:number|null;
  topGames:Array<{appId:number;name:string;minutes:number;icon:string|null}>;
  recentlyPlayed: Array<{ appId: number; name: string; minutes: number; icon: string | null }>;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
export function validateSteamId(value: string): string | null {
  const id = value.trim();
  return /^\d{17}$/.test(id) ? id : null;
}

export interface SteamStoreGame {
  appId:number;title:string;shortDescription:string;headerImage:string|null;isFree:boolean;
  price:{initial:string;final:string;discountPercent:number}|null;releaseDate:string|null;comingSoon:boolean;
  genres:string[];categories:string[];developers:string[];publishers:string[];platforms:string[];
}

export function parseSteamStoreGame(value:unknown):SteamStoreGame|null{
 const item=record(value);
 if(!item||typeof item.steam_appid!=="number"||!Number.isSafeInteger(item.steam_appid)||item.steam_appid<1||typeof item.name!=="string"||!item.name.trim())return null;
 const price=record(item.price_overview);
 const release=record(item.release_date);
 const strings=(input:unknown,key:"description"|"name"):string[]=>Array.isArray(input)?input.flatMap(entry=>{const obj=record(entry);return typeof obj?.[key]==="string"&&obj[key].trim()?[obj[key].trim()]:[]}).slice(0,12):[];
 const platforms=record(item.platforms);
 return {
  appId:item.steam_appid,title:item.name.trim().slice(0,200),
  shortDescription:typeof item.short_description==="string"?item.short_description.replace(/<[^>]*>/g," ").replace(/\s+/g," ").trim().slice(0,500):"",
  headerImage:typeof item.header_image==="string"&&item.header_image.startsWith("https://")?item.header_image:null,
  isFree:item.is_free===true,
  price:price&&typeof price.initial_formatted==="string"&&typeof price.final_formatted==="string"?{initial:price.initial_formatted,final:price.final_formatted,discountPercent:typeof price.discount_percent==="number"?Math.max(0,Math.min(100,price.discount_percent)):0}:null,
  releaseDate:typeof release?.date==="string"?release.date.slice(0,80):null,
  comingSoon:release?.coming_soon===true,
  genres:strings(item.genres,"description"),categories:strings(item.categories,"description"),
  developers:Array.isArray(item.developers)?item.developers.filter((x):x is string=>typeof x==="string").slice(0,8):[],
  publishers:Array.isArray(item.publishers)?item.publishers.filter((x):x is string=>typeof x==="string").slice(0,8):[],
  platforms:platforms?Object.entries(platforms).filter(([,enabled])=>enabled===true).map(([name])=>name):[],
 };
}

export function parseOwnedSteamGames(value:unknown):{totalPlaytimeMinutes:number;topGames:Array<{appId:number;name:string;minutes:number;icon:string|null}>}{
 const rows=Array.isArray(value)?value:[];
 const games=rows.flatMap(raw=>{
  const game=record(raw);
  if(!game||typeof game.appid!=="number"||!Number.isSafeInteger(game.appid)||game.appid<1||typeof game.name!=="string"||!game.name.trim())return[];
  if(game.playtime_forever!==undefined&&(typeof game.playtime_forever!=="number"||!Number.isFinite(game.playtime_forever)||game.playtime_forever<0))return[];
  const minutes=typeof game.playtime_forever==="number"?Math.floor(game.playtime_forever):0;
  const icon=typeof game.img_icon_url==="string"&&game.img_icon_url?"https://media.steampowered.com/steamcommunity/public/images/apps/"+game.appid+"/"+game.img_icon_url+".jpg":null;
  return[{appId:game.appid,name:game.name.trim().slice(0,120),minutes,icon}];
 });
 return{totalPlaytimeMinutes:games.reduce((sum,game)=>sum+game.minutes,0),topGames:games.sort((a,b)=>b.minutes-a.minutes).slice(0,5)};
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
    let totalPlaytimeMinutes:number|null=null;
    let topGames:SteamProfile["topGames"]=[];
    let recentlyPlayed: SteamProfile["recentlyPlayed"] = [];
    if (visibility === "public") {
      const [owned, recent] = await Promise.all([
        this.getService("IPlayerService/GetOwnedGames/v1/", steamId, true),
        this.getService("IPlayerService/GetRecentlyPlayedGames/v1/", steamId),
      ]);
      const ownedResponse = record(record(owned)?.response);
      const recentResponse = record(record(recent)?.response);
      gameCount = typeof ownedResponse?.game_count === "number" ? ownedResponse.game_count : null;
      const ownedSummary=parseOwnedSteamGames(ownedResponse?.games);
      totalPlaytimeMinutes=Array.isArray(ownedResponse?.games)?ownedSummary.totalPlaytimeMinutes:null;
      topGames=ownedSummary.topGames;
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
      totalPlaytimeMinutes,
      topGames,
      recentlyPlayed,
    };
  }

  async getStoreGameDetails(appId:number):Promise<SteamStoreGame|null>{
    if(!Number.isSafeInteger(appId)||appId<1)throw new Error("Steam app ID is invalid.");
    const url=new URL("https://store.steampowered.com/api/appdetails");
    url.searchParams.set("appids",String(appId));url.searchParams.set("cc","us");url.searchParams.set("l","english");
    const response=await fetch(url,{signal:AbortSignal.timeout(10_000)});
    if(!response.ok)throw new Error(`Steam Store returned HTTP ${response.status}.`);
    const body=record(await response.json());
    const result=record(body?.[String(appId)]);
    if(result?.success!==true)return null;
    return parseSteamStoreGame(result.data);
  }

  async searchStoreGames(query:string,maxResults=5):Promise<SteamStoreGame[]>{
    const clean=query.replace(/[\u0000-\u001f]/g," ").replace(/\s+/g," ").trim().slice(0,100);
    if(clean.length<2)return[];
    const limit=Math.max(1,Math.min(5,Math.trunc(maxResults)||5));
    const url=new URL(`https://steamcommunity.com/actions/SearchApps/${encodeURIComponent(clean)}`);
    const response=await fetch(url,{signal:AbortSignal.timeout(10_000),headers:{Accept:"application/json"}});
    if(!response.ok)throw new Error(`Steam search returned HTTP ${response.status}.`);
    const raw:unknown=await response.json();
    const candidates=Array.isArray(raw)?raw.slice(0,limit).flatMap(value=>{
      const row=record(value);const id=Number(row?.appid);
      return Number.isSafeInteger(id)&&id>0?[id]:[];
    }):[];
    const results=await Promise.allSettled(candidates.map(id=>this.getStoreGameDetails(id)));
    return results.flatMap(result=>result.status==="fulfilled"&&result.value?[result.value]:[]);
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
