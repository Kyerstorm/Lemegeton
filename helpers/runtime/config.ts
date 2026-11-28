export interface DatabaseConfig {
 path: string;
 primaryGuildId: string | null;
}
export interface TranslationConfig {
 madladUrl:string|null;
 madladApiKey?:string;
 deeplUrl:string|null;
 deeplApiKey?:string;
 googleTranslateApiKey?:string;
 nllbUrl:string|null;
 nllbApiKey?:string;
 nllbNonCommercialUseConfirmed:boolean;
 libreTranslateUrl:string|null;
 libreTranslateApiKey?:string;
 timeoutMs:number;
}
export interface BotConfig {
 discordToken:string; applicationId:string; anilistApiUrl:string; anilistTimeoutMs:number; botFeedbackChannelId:string|null; archiveGlobalModeratorIds:string[];
 database:DatabaseConfig; rocksDbPath:string; backupDirectory:string; translation:TranslationConfig; adminDiscordId:string|null; dashboardBridgeSecret:string; dashboardBridgeHost:string; dashboardBridgePort:number; dashboardAtlasBridgePort:number;
 customRolePickerEnabled:boolean; customRolePickerHost:string; customRolePickerPort:number;
 customRolesReconcileMinutes:number; customRolesMassArchiveThreshold:number; customRolePickerIdleTtl:number; customRolePickerMaxTtl:number; customRolesPublicUrl:string;
 customRolesTrustProxy:boolean; customRoleIconSourceMaxBytes:number; customRolesDebugPreviewEnhancedColors:boolean; customRolesDebugPreviewRoleIcons:boolean;
 tmdbBearerToken?:string; googleBooksApiKey?:string; igdbClientId?:string; igdbClientSecret?:string;
 steamApiKey?:string; spotifyClientId?:string; spotifyClientSecret?:string; youtubeApiKey?:string; soundcloudClientId?:string; soundcloudClientSecret?:string; lastFmApiKey?:string; setlistFmApiKey?:string; setlistFmNonCommercialConfirmed:boolean;
 myAnimeListClientId?:string; traktClientId?:string; tvdbApiKey?:string; tvdbSubscriberPin?:string; tvdbAccessEnabled:boolean; hardcoverApiToken?:string; comicVineApiKey?:string; comicVineNonCommercialConfirmed:boolean; redditClientId?:string; redditClientSecret?:string; redditApiAccessConfirmed:boolean; tvMazeAttributionConfirmed:boolean; comicBookHeraldRssNonCommercialConfirmed:boolean; mediaWikiEnabledSources:string[]; mediaSourceScrapeAllowlist:string[];
 musicPollIntervalMinutes:number; archiveUploadMaxBytes:number; logLevel:"debug"|"info"|"warn"|"error"; botModeratorGuildId:string|null; githubRepository:string; githubBranch:string; githubToken:string|null; githubPollIntervalMinutes:number; githubUpdateChannelId:string|null; expeditionAnswerSecret:string|null; casebookSolutionSecret:string|null;
}
function required(env:NodeJS.ProcessEnv,key:string):string{const value=env[key]?.trim();if(!value)throw new Error(`Missing required environment variable: ${key}`);return value;}
function booleanValue(value:string|undefined,key:string,fallback:boolean):boolean{
  if(!value?.trim())return fallback;
  const normalized=value.trim().toLowerCase();
  if(["1","true","yes","on"].includes(normalized))return true;
  if(["0","false","no","off"].includes(normalized))return false;
  throw new Error(key+" must be a boolean.");
}
function positive(value:string|undefined,fallback:number,key:string):number{if(!value?.trim())return fallback;const n=Number(value);if(!Number.isSafeInteger(n)||n<1)throw new Error(`${key} must be a positive integer.`);return n;}
function optionalSecret(env:NodeJS.ProcessEnv,key:string):string|null{const value=env[key]?.trim();if(!value)return null;if(Buffer.byteLength(value,"utf8")<32)throw new Error(key+" must contain at least 32 UTF-8 bytes.");return value;}
function sourceList(raw:string|undefined,key:string,allowed:readonly string[]):string[]{const values=[...new Set((raw??"").split(",").map(value=>value.trim().toLowerCase()).filter(Boolean))];const invalid=values.find(value=>!allowed.includes(value));if(invalid)throw new Error(key+" contains an unsupported source ID: "+invalid+".");return values;}
export function parseCustomRoleMassArchiveThreshold(raw:string|undefined):number{if(!raw?.trim())return 10;const value=Number(raw);return Number.isSafeInteger(value)?Math.max(0,value):10;}
function databaseConfig(env:NodeJS.ProcessEnv):DatabaseConfig {
 const path=env.LIBSQL_PATH?.trim()||env.DATABASE_PATH?.trim()||"./data/bot/lemegeton.db";
 if(path.includes("://"))throw new Error("LIBSQL_PATH must be a local file path, not a network URL.");
 const primaryGuildId=env.GUILD_ID?.trim()||env.PRIMARY_GUILD_ID?.trim()||null;
 if(primaryGuildId && !/^\d{17,20}$/.test(primaryGuildId))throw new Error("GUILD_ID / PRIMARY_GUILD_ID must be a valid Discord server ID.");
 return {path,primaryGuildId};
}
function optionalTranslationEndpoint(env:NodeJS.ProcessEnv,key:string):string|null{
 const value=env[key]?.trim();
 if(!value)return null;
 let parsed:URL;
 try{parsed=new URL(value);}catch{throw new Error(key+" must be a valid URL.");}
 const hostname=parsed.hostname.replace(/^\[|\]$/g,"").toLowerCase();
 const loopback=hostname==="localhost"||hostname==="127.0.0.1"||hostname==="::1";
 if(parsed.protocol!=="https:"&&!(parsed.protocol==="http:"&&loopback))throw new Error(key+" must use HTTPS (HTTP is allowed only for loopback development endpoints).");
 if(parsed.username||parsed.password||parsed.search||parsed.hash)throw new Error(key+" must not contain credentials, query parameters or fragments.");
 return parsed.toString();
}
function translationConfig(env:NodeJS.ProcessEnv):TranslationConfig{
 const madladUrl=optionalTranslationEndpoint(env,"MADLAD_TRANSLATION_URL");
 const deeplUrl=optionalTranslationEndpoint(env,"DEEPL_TRANSLATION_URL");
 const nllbUrl=optionalTranslationEndpoint(env,"NLLB_TRANSLATION_URL");
 const libreTranslateUrl=optionalTranslationEndpoint(env,"LIBRETRANSLATE_URL");
 const nllbConfirmed=booleanValue(env.NLLB_NONCOMMERCIAL_USE_CONFIRMED,"NLLB_NONCOMMERCIAL_USE_CONFIRMED",false);
 const production=env.ENVIRONMENT?.trim().toLowerCase()==="production"||env.NODE_ENV?.trim().toLowerCase()==="production";
 return {
  madladUrl,...(env.MADLAD_TRANSLATION_TOKEN?.trim()?{madladApiKey:env.MADLAD_TRANSLATION_TOKEN.trim()}:{}),
  deeplUrl,...(env.DEEPL_API_KEY?.trim()?{deeplApiKey:env.DEEPL_API_KEY.trim()}:{}),
  ...(env.GOOGLE_TRANSLATE_API_KEY?.trim()?{googleTranslateApiKey:env.GOOGLE_TRANSLATE_API_KEY.trim()}:{}),
  nllbUrl,...(env.NLLB_TRANSLATION_TOKEN?.trim()?{nllbApiKey:env.NLLB_TRANSLATION_TOKEN.trim()}:{}),
  nllbNonCommercialUseConfirmed:nllbConfirmed&&!production,
  libreTranslateUrl,...(env.LIBRETRANSLATE_API_KEY?.trim()?{libreTranslateApiKey:env.LIBRETRANSLATE_API_KEY.trim()}:{}),
  timeoutMs:Math.min(positive(env.TRANSLATION_TIMEOUT_MS,5000,"TRANSLATION_TIMEOUT_MS"),15000),
 };
}
export function loadConfig(env:NodeJS.ProcessEnv=process.env):BotConfig{
 const discordToken=required(env,"DISCORD_TOKEN");const applicationId=env.DISCORD_CLIENT_ID?.trim()||env.CLIENT_ID?.trim()||required(env,"BOT_ID");
 const expeditionAnswerSecret=optionalSecret(env,"EXPEDITION_ANSWER_SECRET");
 const casebookSolutionSecret=optionalSecret(env,"CASEBOOK_SOLUTION_SECRET");
 if(!/^\d{17,20}$/.test(applicationId))throw new Error("BOT_ID / CLIENT_ID / DISCORD_CLIENT_ID must be a valid Discord application ID.");
 const botModeratorGuildId=env.BOT_MODERATOR_GUILD_ID?.trim()||null;
 if(botModeratorGuildId&&!/^\d{17,20}$/.test(botModeratorGuildId))throw new Error("BOT_MODERATOR_GUILD_ID must be a valid 17–20 digit Discord server ID.");
 const adminDiscordId=env.ADMIN_DISCORD_ID?.trim()||null;
 const botFeedbackChannelId=env.BOT_FEEDBACK_CHANNEL_ID?.trim()||null;
 if(botFeedbackChannelId&&!/^\d{17,20}$/.test(botFeedbackChannelId))throw new Error("BOT_FEEDBACK_CHANNEL_ID must be a valid Discord channel ID.");
 const archiveGlobalModeratorIds=[...new Set((env.ARCHIVE_GLOBAL_MODERATOR_IDS??"").split(",").map(id=>id.trim()).filter(id=>/^\d{17,20}$/.test(id)))];
 if(adminDiscordId&&!/^\d{17,20}$/.test(adminDiscordId))throw new Error("ADMIN_DISCORD_ID must be a valid Discord user ID.");
 const githubRepository=env.GITHUB_REPO?.trim()||"Kyerstorm/Lemegeton";
 if(!/^[A-Za-z0-9_.-]{1,39}\/[A-Za-z0-9_.-]{1,100}$/.test(githubRepository))throw new Error("GITHUB_REPO must use owner/repository format.");
 const githubBranch=env.GITHUB_BRANCH?.trim()||"lemegeton-v3";
 if(!githubBranch||githubBranch.length>255||/[\s?#]/.test(githubBranch))throw new Error("GITHUB_BRANCH must be a non-empty branch name without whitespace, query strings or fragments.");
 const githubToken=env.GITHUB_TOKEN?.trim()||null;
 const githubPollIntervalMinutes=positive(env.GITHUB_POLL_MINUTES,10,"GITHUB_POLL_MINUTES");
 const githubUpdateChannelId=env.GITHUB_UPDATE_CHANNEL_ID?.trim()||null;
 if(githubUpdateChannelId&&!/^\d{17,20}$/.test(githubUpdateChannelId))throw new Error("GITHUB_UPDATE_CHANNEL_ID must be a valid Discord channel ID.");
 const database=databaseConfig(env);
 const rocksDbPath=env.ROCKSDB_PATH?.trim()||"./data/objects";
 const backupDirectory=env.BACKUP_DIRECTORY?.trim()||"./data/backups";
 const translation=translationConfig(env);
 const dashboardBridgeSecret=env.DASHBOARD_BRIDGE_SECRET?.trim()??"";
 const dashboardBridgeHostRaw=env.DASHBOARD_BRIDGE_HOST?.trim()||"127.0.0.1";
 const dashboardBridgeHost=dashboardBridgeHostRaw==="[::1]"?"::1":dashboardBridgeHostRaw;
 const bridgeHostParts=dashboardBridgeHost.split(".");
 const bridgeLoopbackV4=bridgeHostParts.length===4&&Number(bridgeHostParts[0])===127&&bridgeHostParts.every(part=>/^\d{1,3}$/.test(part)&&Number(part)>=0&&Number(part)<=255);
 if(!(dashboardBridgeHost==="localhost"||dashboardBridgeHost==="::1"||bridgeLoopbackV4))throw new Error("DASHBOARD_BRIDGE_HOST must be a loopback address.");
 const dashboardBridgePort=positive(env.DASHBOARD_BRIDGE_PORT,8091,"DASHBOARD_BRIDGE_PORT");
 if(dashboardBridgePort>65535)throw new Error("DASHBOARD_BRIDGE_PORT must be between 1 and 65535.");
 const dashboardAtlasBridgePort=positive(env.DASHBOARD_ATLAS_BRIDGE_PORT,8093,"DASHBOARD_ATLAS_BRIDGE_PORT");
 if(dashboardAtlasBridgePort>65535)throw new Error("DASHBOARD_ATLAS_BRIDGE_PORT must be between 1 and 65535.");
 const anilistApiUrl=env.ANILIST_API_URL?.trim()||"https://graphql.anilist.co";const parsed=new URL(anilistApiUrl);
 const local=["localhost","127.0.0.1","[::1]"].includes(parsed.hostname);
 if(parsed.protocol!=="https:"&&!(parsed.protocol==="http:"&&local))throw new Error("ANILIST_API_URL must use HTTPS (HTTP only for loopback development).");
 const pickerEnabled=(env.CUSTOM_ROLES_PICKER_ENABLED?.trim().toLowerCase()??"true");
 if(!["1","true","yes","on","0","false","no","off"].includes(pickerEnabled))throw new Error("CUSTOM_ROLES_PICKER_ENABLED must be a boolean.");
 const pickerHostRaw=env.DASHBOARD_PICKER_HOST?.trim()||"127.0.0.1";
 const pickerHost=pickerHostRaw==="[::1]"?"::1":pickerHostRaw;
 const hostParts=pickerHost.split(".");
 const loopbackV4=hostParts.length===4&&Number(hostParts[0])===127&&hostParts.every(part=>part.length>0&&[...part].every(char=>char>="0"&&char<="9")&&Number(part)>=0&&Number(part)<=255);
 const pickerHostAllowed=pickerHost==="localhost"||pickerHost==="::1"||pickerHost==="[::1]"||loopbackV4;
 if(!pickerHostAllowed)throw new Error("DASHBOARD_PICKER_HOST must be localhost or a loopback IPv4/IPv6 address.");
 let customRolesPublicUrl=env.CUSTOM_ROLES_PUBLIC_URL?.trim()||env.DASHBOARD_PUBLIC_URL?.trim()||"http://localhost:8080";
 if(customRolesPublicUrl.endsWith("/"))customRolesPublicUrl=customRolesPublicUrl.slice(0,-1);
 const pickerOrigin=new URL(customRolesPublicUrl);
 if(pickerOrigin.pathname!=="/"||pickerOrigin.search||pickerOrigin.hash||pickerOrigin.username||pickerOrigin.password)throw new Error("CUSTOM_ROLES_PUBLIC_URL must be an origin without a path, query or credentials.");
 if(env.NODE_ENV?.trim().toLowerCase()==="production"&&["1","true","yes","on"].includes(pickerEnabled)&&!env.CUSTOM_ROLES_PUBLIC_URL?.trim()&&!env.DASHBOARD_PUBLIC_URL?.trim())throw new Error("Set CUSTOM_ROLES_PUBLIC_URL to the public HTTPS dashboard origin before enabling the production picker.");
 const localPickerOrigin=["localhost","127.0.0.1","[::1]"].includes(pickerOrigin.hostname);
 if(pickerOrigin.protocol!=="https:"&&!(pickerOrigin.protocol==="http:"&&localPickerOrigin))throw new Error("CUSTOM_ROLES_PUBLIC_URL must use HTTPS (HTTP only for loopback development).");
 const pickerPort=positive(env.DASHBOARD_PICKER_PORT,8092,"DASHBOARD_PICKER_PORT");
 if(pickerPort>65535)throw new Error("DASHBOARD_PICKER_PORT must be between 1 and 65535.");
 const developmentMode=(env.ENVIRONMENT?.trim().toLowerCase()??"development")==="development" && env.NODE_ENV?.trim().toLowerCase()!=="production";
 const debugEnabled=(value:string|undefined)=>["1","true","yes","on"].includes(value?.trim().toLowerCase()??"");
 const customRolesDebugPreviewEnhancedColors=developmentMode&&debugEnabled(env.CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS);
 const customRolesDebugPreviewRoleIcons=developmentMode&&debugEnabled(env.CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS);
 const customRolesReconcileMinutes=positive(env.CUSTOM_ROLES_RECONCILE_MINUTES,30,"CUSTOM_ROLES_RECONCILE_MINUTES");
 const customRolesMassArchiveThreshold=parseCustomRoleMassArchiveThreshold(env.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD);
 const pickerIdleTtl=Math.max(60,positive(env.CUSTOM_ROLES_PICKER_IDLE_TTL,3600,"CUSTOM_ROLES_PICKER_IDLE_TTL"));
 const pickerMaxTtl=Math.max(pickerIdleTtl,positive(env.CUSTOM_ROLES_PICKER_MAX_TTL,10800,"CUSTOM_ROLES_PICKER_MAX_TTL"));
 const trustProxy=(env.CUSTOM_ROLES_TRUST_PROXY?.trim().toLowerCase()??"false");
 if(!["1","true","yes","on","0","false","no","off"].includes(trustProxy))throw new Error("CUSTOM_ROLES_TRUST_PROXY must be a boolean.");
 const logLevel=(env.LOG_LEVEL?.trim().toLowerCase()||"info") as BotConfig["logLevel"];
 if(!["debug","info","warn","error"].includes(logLevel))throw new Error("LOG_LEVEL must be debug, info, warn, or error.");
 if(Boolean(env.IGDB_CLIENT_ID?.trim())!==Boolean(env.IGDB_CLIENT_SECRET?.trim()))throw new Error("IGDB_CLIENT_ID and IGDB_CLIENT_SECRET must be configured together.");
 const spotifyClientId=env.SPOTIFY_CLIENT_ID?.trim()||undefined;
 const spotifyClientSecret=env.SPOTIFY_CLIENT_SECRET?.trim()||undefined;
 if(Boolean(spotifyClientId)!==Boolean(spotifyClientSecret))throw new Error("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be configured together.");
 const youtubeApiKey=env.YOUTUBE_API_KEY?.trim()||undefined;
 const soundcloudClientId=env.SOUNDCLOUD_CLIENT_ID?.trim()||undefined;
 const soundcloudClientSecret=env.SOUNDCLOUD_CLIENT_SECRET?.trim()||undefined;
 const lastFmApiKey=env.LASTFM_API_KEY?.trim()||undefined;
 const setlistFmApiKey=env.SETLISTFM_API_KEY?.trim()||undefined;
 const setlistFmNonCommercialConfirmed=booleanValue(env.SETLISTFM_NONCOMMERCIAL_CONFIRMED,"SETLISTFM_NONCOMMERCIAL_CONFIRMED",false);
 const tvdbApiKey=env.TVDB_API_KEY?.trim()||undefined;
 const tvdbSubscriberPin=env.TVDB_SUBSCRIBER_PIN?.trim()||undefined;
 const tvdbAccessEnabled=booleanValue(env.TVDB_ACCESS_ENABLED,"TVDB_ACCESS_ENABLED",false);
 const hardcoverApiToken=env.HARDCOVER_API_TOKEN?.trim()||undefined;
 const comicVineApiKey=env.COMIC_VINE_API_KEY?.trim()||undefined;
 const comicVineNonCommercialConfirmed=booleanValue(env.COMIC_VINE_NONCOMMERCIAL_CONFIRMED,"COMIC_VINE_NONCOMMERCIAL_CONFIRMED",false);
 const redditClientId=env.REDDIT_CLIENT_ID?.trim()||undefined;
 const redditClientSecret=env.REDDIT_CLIENT_SECRET?.trim()||undefined;
 const redditApiAccessConfirmed=booleanValue(env.REDDIT_API_ACCESS_CONFIRMED,"REDDIT_API_ACCESS_CONFIRMED",false);
 const tvMazeAttributionConfirmed=booleanValue(env.TVMAZE_SHAREALIKE_CONFIRMED,"TVMAZE_SHAREALIKE_CONFIRMED",false);
 const comicBookHeraldRssNonCommercialConfirmed=booleanValue(env.COMIC_BOOK_HERALD_RSS_NONCOMMERCIAL_CONFIRMED,"COMIC_BOOK_HERALD_RSS_NONCOMMERCIAL_CONFIRMED",false);
 if(Boolean(redditClientId)!==Boolean(redditClientSecret))throw new Error("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be configured together.");
 if(tvdbAccessEnabled&&!tvdbApiKey)throw new Error("TVDB_ACCESS_ENABLED requires TVDB_API_KEY and an active access plan.");
 if(comicVineNonCommercialConfirmed&&!comicVineApiKey)throw new Error("COMIC_VINE_NONCOMMERCIAL_CONFIRMED requires COMIC_VINE_API_KEY.");
 if(redditApiAccessConfirmed&&(!redditClientId||!redditClientSecret))throw new Error("REDDIT_API_ACCESS_CONFIRMED requires Reddit app credentials.");
 const mediaWikiEnabledSources=sourceList(env.MEDIAWIKI_ENABLED_SOURCES,"MEDIAWIKI_ENABLED_SOURCES",[
  "wookieepedia","memory-alpha","tardis-wiki","marvel-database","dc-database","tolkien-gateway","harry-potter-wiki",
  "a-song-of-ice-and-fire-wiki","witcher-wiki","narutopedia","dragon-ball-wiki","one-piece-wiki","jojos-bizarre-encyclopedia","pokemon-wiki","transformers-wiki",
 ]);
 const mediaSourceScrapeAllowlist=sourceList(env.MEDIA_SOURCE_SCRAPE_ALLOWLIST,"MEDIA_SOURCE_SCRAPE_ALLOWLIST",["comic-book-herald","novel-updates","novelfire","novel-archive","wuxia-click","noveli-to"]);
 const myAnimeListClientId=env.MAL_CLIENT_ID?.trim()||undefined;
 const traktClientId=env.TRAKT_CLIENT_ID?.trim()||undefined;
 const musicPollIntervalMinutes=positive(env.MUSIC_POLL_INTERVAL_MINUTES,10,"MUSIC_POLL_INTERVAL_MINUTES");
 return {discordToken,applicationId,botModeratorGuildId,adminDiscordId,botFeedbackChannelId,archiveGlobalModeratorIds,database,rocksDbPath,backupDirectory,translation,dashboardBridgeSecret,dashboardBridgeHost,dashboardBridgePort,dashboardAtlasBridgePort,githubRepository,githubBranch,githubToken,githubPollIntervalMinutes,githubUpdateChannelId,expeditionAnswerSecret,casebookSolutionSecret,anilistApiUrl:parsed.toString(),anilistTimeoutMs:positive(env.ANILIST_API_TIMEOUT,10,"ANILIST_API_TIMEOUT")*1000,
 ...(env.TMDB_BEARER_TOKEN?.trim()?{tmdbBearerToken:env.TMDB_BEARER_TOKEN.trim()}:{}),
 ...(env.GOOGLE_BOOKS_API_KEY?.trim()?{googleBooksApiKey:env.GOOGLE_BOOKS_API_KEY.trim()}:{}),
 ...(env.IGDB_CLIENT_ID?.trim()?{igdbClientId:env.IGDB_CLIENT_ID.trim()}:{}),
 ...(env.IGDB_CLIENT_SECRET?.trim()?{igdbClientSecret:env.IGDB_CLIENT_SECRET.trim()}:{}),
 ...(env.STEAM_API_KEY?.trim()?{steamApiKey:env.STEAM_API_KEY.trim()}:{}),
 ...(spotifyClientId?{spotifyClientId}:{}),...(spotifyClientSecret?{spotifyClientSecret}:{}),
 ...(youtubeApiKey?{youtubeApiKey}:{}),...(soundcloudClientId?{soundcloudClientId}:{}),...(soundcloudClientSecret?{soundcloudClientSecret}:{}),...(lastFmApiKey?{lastFmApiKey}:{}),...(setlistFmApiKey?{setlistFmApiKey}:{}),setlistFmNonCommercialConfirmed,
 ...(myAnimeListClientId?{myAnimeListClientId}:{}),...(traktClientId?{traktClientId}:{}),
 ...(tvdbApiKey?{tvdbApiKey}:{}),...(tvdbSubscriberPin?{tvdbSubscriberPin}:{}),tvdbAccessEnabled,
 ...(hardcoverApiToken?{hardcoverApiToken}:{}),...(comicVineApiKey?{comicVineApiKey}:{}),comicVineNonCommercialConfirmed,
 ...(redditClientId?{redditClientId}:{}),...(redditClientSecret?{redditClientSecret}:{}),redditApiAccessConfirmed,tvMazeAttributionConfirmed,
 mediaWikiEnabledSources,mediaSourceScrapeAllowlist,comicBookHeraldRssNonCommercialConfirmed,musicPollIntervalMinutes,
 archiveUploadMaxBytes:Math.min(positive(env.ARCHIVE_UPLOAD_MAX_BYTES,20*1024*1024,"ARCHIVE_UPLOAD_MAX_BYTES"),20*1024*1024),
 customRolePickerEnabled:["1","true","yes","on"].includes(pickerEnabled),customRolePickerHost:pickerHost,
 customRolePickerPort:pickerPort,
 customRolesReconcileMinutes,customRolesMassArchiveThreshold,customRolePickerIdleTtl:pickerIdleTtl,customRolePickerMaxTtl:pickerMaxTtl,
 customRolesPublicUrl:pickerOrigin.origin,customRolesTrustProxy:["1","true","yes","on"].includes(trustProxy),
 customRolesDebugPreviewEnhancedColors,customRolesDebugPreviewRoleIcons,
 customRoleIconSourceMaxBytes:Math.max(256*1024,positive(env.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES,8*1024*1024,"CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES")),
 logLevel};
}
