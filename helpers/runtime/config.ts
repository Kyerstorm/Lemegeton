export interface DatabaseConfig {
 connectionString?:string; host:string; port:number; database:string; user:string; password:string;
 ssl:boolean; sslCaFile?:string; poolSize:number; primaryGuildId:string|null;
}
export interface BotConfig {
 discordToken:string; applicationId:string; anilistApiUrl:string; anilistTimeoutMs:number; botFeedbackChannelId:string|null; archiveGlobalModeratorIds:string[];
 database:DatabaseConfig; adminDiscordId:string|null; dashboardBridgeSecret:string; dashboardBridgeHost:string; dashboardBridgePort:number; dashboardAtlasBridgePort:number;
 customRolePickerEnabled:boolean; customRolePickerHost:string; customRolePickerPort:number;
 customRolesReconcileMinutes:number; customRolesMassArchiveThreshold:number; customRolePickerIdleTtl:number; customRolePickerMaxTtl:number; customRolesPublicUrl:string;
 customRolesTrustProxy:boolean; customRoleIconSourceMaxBytes:number; customRolesDebugPreviewEnhancedColors:boolean; customRolesDebugPreviewRoleIcons:boolean;
 tmdbBearerToken?:string; googleBooksApiKey?:string; igdbClientId?:string; igdbClientSecret?:string;
 steamApiKey?:string; archiveUploadMaxBytes:number; s3EndpointUrl?:string; s3Region:string; s3AccessKeyId?:string; s3SecretAccessKey?:string; s3Bucket:string|null; s3SignedUrlTtlSeconds:number; logLevel:"debug"|"info"|"warn"|"error"; botModeratorGuildId:string|null;
}
function required(env:NodeJS.ProcessEnv,key:string):string{const value=env[key]?.trim();if(!value)throw new Error(`Missing required environment variable: ${key}`);return value;}
function positive(value:string|undefined,fallback:number,key:string):number{if(!value?.trim())return fallback;const n=Number(value);if(!Number.isSafeInteger(n)||n<1)throw new Error(`${key} must be a positive integer.`);return n;}
export function parseCustomRoleMassArchiveThreshold(raw:string|undefined):number{if(!raw?.trim())return 10;const value=Number(raw);return Number.isSafeInteger(value)?Math.max(0,value):10;}
function loopbackDatabaseHost(host:string):boolean {
 const normalized=host.trim().toLowerCase().replace(/^\[|\]$/g,"");
 return normalized==="localhost"||normalized==="127.0.0.1"||normalized==="::1";
}
function databaseBoolean(value:string|undefined,key:string,defaultValue:boolean):boolean {
 if(!value?.trim())return defaultValue;
 const normalized=value.trim().toLowerCase();
 if(["1","true","yes","on","require","required","verify-ca","verify-full"].includes(normalized))return true;
 if(["0","false","no","off","disable","disabled"].includes(normalized))return false;
 throw new Error(key+" must be a boolean value.");
}
function databaseConfig(env:NodeJS.ProcessEnv):DatabaseConfig {
 const rawDsn=env.DATABASE_URL?.trim()||env.POSTGRES_DSN?.trim()||env.POSTGRES_URL?.trim();
 let parsedDsn:URL|undefined;
 if(rawDsn){
  try{parsedDsn=new URL(rawDsn.replace(/^postgres:/,"postgresql:"));}
  catch{throw new Error("DATABASE_URL / POSTGRES_DSN / POSTGRES_URL must be a valid PostgreSQL connection URL.");}
  if(!["postgresql:","postgres:"].includes(parsedDsn.protocol)||!parsedDsn.hostname)
   throw new Error("DATABASE_URL / POSTGRES_DSN / POSTGRES_URL must use PostgreSQL and include a host.");
 }
 const host=parsedDsn?.hostname??env.POSTGRES_HOST?.trim()??"127.0.0.1";
 const port=parsedDsn?.port?Number(parsedDsn.port):positive(env.POSTGRES_PORT,5432,"POSTGRES_PORT");
 if(!Number.isInteger(port)||port<1||port>65535)throw new Error("POSTGRES_PORT must be between 1 and 65535.");
 if(parsedDsn&&!parsedDsn.port)parsedDsn.port=String(port);
 const environment=(env.ENVIRONMENT??"").trim().toLowerCase();
 const ssl=databaseBoolean(env.POSTGRES_SSL,"POSTGRES_SSL",environment==="production"||!loopbackDatabaseHost(host));
 if(!ssl&&environment==="production")throw new Error("PostgreSQL TLS cannot be disabled in production.");
 if(!ssl&&!loopbackDatabaseHost(host))throw new Error("PostgreSQL TLS may only be disabled for loopback development databases.");
 const primaryGuildId=env.GUILD_ID?.trim()||env.PRIMARY_GUILD_ID?.trim()||null;
 if(primaryGuildId&&!/^\d{17,20}$/.test(primaryGuildId))throw new Error("GUILD_ID / PRIMARY_GUILD_ID must be a valid Discord server ID.");
 return {
  ...(parsedDsn?{connectionString:parsedDsn.toString()}:{}),
  host,port,database:env.POSTGRES_DB?.trim()||env.POSTGRES_DATABASE?.trim()||"postgres",
  user:env.POSTGRES_USER?.trim()||"postgres",password:env.POSTGRES_PASSWORD??"",
  ssl,...(env.POSTGRES_SSL_CA_FILE?.trim()?{sslCaFile:env.POSTGRES_SSL_CA_FILE.trim()}:{}),
  poolSize:positive(env.POSTGRES_POOL_SIZE??env.DB_CONNECTION_POOL_SIZE,5,"POSTGRES_POOL_SIZE"),
  primaryGuildId,
 };
}
export function loadConfig(env:NodeJS.ProcessEnv=process.env):BotConfig{
 const discordToken=required(env,"DISCORD_TOKEN");const applicationId=env.DISCORD_CLIENT_ID?.trim()||env.CLIENT_ID?.trim()||required(env,"BOT_ID");
 if(!/^\d{17,20}$/.test(applicationId))throw new Error("BOT_ID / CLIENT_ID / DISCORD_CLIENT_ID must be a valid Discord application ID.");
 const botModeratorGuildId=env.BOT_MODERATOR_GUILD_ID?.trim()||null;
 if(botModeratorGuildId&&!/^\d{17,20}$/.test(botModeratorGuildId))throw new Error("BOT_MODERATOR_GUILD_ID must be a valid 17–20 digit Discord server ID.");
 const adminDiscordId=env.ADMIN_DISCORD_ID?.trim()||null;
 const botFeedbackChannelId=env.BOT_FEEDBACK_CHANNEL_ID?.trim()||null;
 if(botFeedbackChannelId&&!/^\d{17,20}$/.test(botFeedbackChannelId))throw new Error("BOT_FEEDBACK_CHANNEL_ID must be a valid Discord channel ID.");
 const archiveGlobalModeratorIds=[...new Set((env.ARCHIVE_GLOBAL_MODERATOR_IDS??"").split(",").map(id=>id.trim()).filter(id=>/^\d{17,20}$/.test(id)))];
 if(adminDiscordId&&!/^\d{17,20}$/.test(adminDiscordId))throw new Error("ADMIN_DISCORD_ID must be a valid Discord user ID.");
 const database=databaseConfig(env);
 const s3EndpointUrl=env.S3_ENDPOINT_URL?.trim()||undefined;
 const s3Region=env.S3_REGION?.trim()||"us-east-1";
 const s3AccessKeyId=env.S3_ACCESS_KEY_ID?.trim()||undefined;
 const s3SecretAccessKey=env.S3_SECRET_ACCESS_KEY?.trim()||undefined;
 if(Boolean(s3AccessKeyId)!==Boolean(s3SecretAccessKey))throw new Error("S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be configured together.");
 const s3Bucket=env.S3_BUCKET?.trim()||null;
 const s3SignedUrlTtlSeconds=Math.max(60,Math.min(3600,positive(env.S3_SIGNED_URL_TTL_SECONDS,900,"S3_SIGNED_URL_TTL_SECONDS")));
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
 return {discordToken,applicationId,botModeratorGuildId,adminDiscordId,botFeedbackChannelId,archiveGlobalModeratorIds,database,dashboardBridgeSecret,dashboardBridgeHost,dashboardBridgePort,dashboardAtlasBridgePort,anilistApiUrl:parsed.toString(),anilistTimeoutMs:positive(env.ANILIST_API_TIMEOUT,10,"ANILIST_API_TIMEOUT")*1000,
 ...(env.TMDB_BEARER_TOKEN?.trim()?{tmdbBearerToken:env.TMDB_BEARER_TOKEN.trim()}:{}),
 ...(env.GOOGLE_BOOKS_API_KEY?.trim()?{googleBooksApiKey:env.GOOGLE_BOOKS_API_KEY.trim()}:{}),
 ...(env.IGDB_CLIENT_ID?.trim()?{igdbClientId:env.IGDB_CLIENT_ID.trim()}:{}),
 ...(env.IGDB_CLIENT_SECRET?.trim()?{igdbClientSecret:env.IGDB_CLIENT_SECRET.trim()}:{}),
 ...(env.STEAM_API_KEY?.trim()?{steamApiKey:env.STEAM_API_KEY.trim()}:{}),
 archiveUploadMaxBytes:Math.min(positive(env.ARCHIVE_UPLOAD_MAX_BYTES,20*1024*1024,"ARCHIVE_UPLOAD_MAX_BYTES"),20*1024*1024),
 s3EndpointUrl,s3Region,...(s3AccessKeyId?{s3AccessKeyId}:{}),...(s3SecretAccessKey?{s3SecretAccessKey}:{}),s3Bucket,s3SignedUrlTtlSeconds,
 customRolePickerEnabled:["1","true","yes","on"].includes(pickerEnabled),customRolePickerHost:pickerHost,
 customRolePickerPort:pickerPort,
 customRolesReconcileMinutes,customRolesMassArchiveThreshold,customRolePickerIdleTtl:pickerIdleTtl,customRolePickerMaxTtl:pickerMaxTtl,
 customRolesPublicUrl:pickerOrigin.origin,customRolesTrustProxy:["1","true","yes","on"].includes(trustProxy),
 customRolesDebugPreviewEnhancedColors,customRolesDebugPreviewRoleIcons,
 customRoleIconSourceMaxBytes:Math.max(256*1024,positive(env.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES,8*1024*1024,"CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES")),
 logLevel};
}
