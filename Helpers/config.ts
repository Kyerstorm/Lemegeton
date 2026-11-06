export interface BotConfig {
 discordToken:string; applicationId:string; anilistApiUrl:string; anilistTimeoutMs:number;
 tmdbBearerToken?:string; googleBooksApiKey?:string; igdbClientId?:string; igdbClientSecret?:string;
 steamApiKey?:string; archiveUploadMaxBytes:number; logLevel:"debug"|"info"|"warn"|"error";
}
function required(env:NodeJS.ProcessEnv,key:string):string{const value=env[key]?.trim();if(!value)throw new Error(`Missing required environment variable: ${key}`);return value;}
function positive(value:string|undefined,fallback:number,key:string):number{if(!value?.trim())return fallback;const n=Number(value);if(!Number.isSafeInteger(n)||n<1)throw new Error(`${key} must be a positive integer.`);return n;}
export function loadConfig(env:NodeJS.ProcessEnv=process.env):BotConfig{
 const discordToken=required(env,"DISCORD_TOKEN");const applicationId=env.DISCORD_CLIENT_ID?.trim()||required(env,"BOT_ID");
 if(!/^\d{17,20}$/.test(applicationId))throw new Error("BOT_ID / DISCORD_CLIENT_ID must be a valid Discord application ID.");
 const anilistApiUrl=env.ANILIST_API_URL?.trim()||"https://graphql.anilist.co";const parsed=new URL(anilistApiUrl);
 const local=["localhost","127.0.0.1","[::1]"].includes(parsed.hostname);
 if(parsed.protocol!=="https:"&&!(parsed.protocol==="http:"&&local))throw new Error("ANILIST_API_URL must use HTTPS (HTTP only for loopback development).");
 const logLevel=(env.LOG_LEVEL?.trim().toLowerCase()||"info") as BotConfig["logLevel"];
 if(!["debug","info","warn","error"].includes(logLevel))throw new Error("LOG_LEVEL must be debug, info, warn, or error.");
 if(Boolean(env.IGDB_CLIENT_ID?.trim())!==Boolean(env.IGDB_CLIENT_SECRET?.trim()))throw new Error("IGDB_CLIENT_ID and IGDB_CLIENT_SECRET must be configured together.");
 return {discordToken,applicationId,anilistApiUrl:parsed.toString(),anilistTimeoutMs:positive(env.ANILIST_API_TIMEOUT,10,"ANILIST_API_TIMEOUT")*1000,
 ...(env.TMDB_BEARER_TOKEN?.trim()?{tmdbBearerToken:env.TMDB_BEARER_TOKEN.trim()}:{}),
 ...(env.GOOGLE_BOOKS_API_KEY?.trim()?{googleBooksApiKey:env.GOOGLE_BOOKS_API_KEY.trim()}:{}),
 ...(env.IGDB_CLIENT_ID?.trim()?{igdbClientId:env.IGDB_CLIENT_ID.trim()}:{}),
 ...(env.IGDB_CLIENT_SECRET?.trim()?{igdbClientSecret:env.IGDB_CLIENT_SECRET.trim()}:{}),
 ...(env.STEAM_API_KEY?.trim()?{steamApiKey:env.STEAM_API_KEY.trim()}:{}),
 archiveUploadMaxBytes:Math.min(positive(env.ARCHIVE_UPLOAD_MAX_BYTES,20*1024*1024,"ARCHIVE_UPLOAD_MAX_BYTES"),20*1024*1024),logLevel};
}
