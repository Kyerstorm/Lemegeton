import {ActionRowBuilder,AuditLogEvent,ButtonBuilder,ButtonStyle,Client,Events,GatewayIntentBits,MessageFlags,type Guild,type Interaction,type TextChannel} from "discord.js";
import { emoji } from "./helpers/emoji.js";
import { withFakeLoading } from "./helpers/runtime/fake-loading.js";
import {createServer, type Server} from "node:http";
import {timingSafeEqual} from "node:crypto";
import {findAtlasGraph,normalizeAtlasCategory,safeAtlasUrl,recordAtlasRelationship} from "./helpers/integration/atlas.js";
import {loadConfig} from "./helpers/runtime/config.js";
import {configureTranslation,translateGuildUiText} from "./helpers/integration/translation.js";
import {configureLogger,logger} from "./helpers/runtime/logger.js";
import type {FeatureCommand} from "./helpers/commands/command.js";
import {handleArchiveUploadMessage} from "./helpers/archive/archive.js";
import {configureArchiveAccess} from "./helpers/archive/archive-access.js";
import {findDepartedGuildProfileIds,getGuildProfileUserIds,removeGuildMemberProfileData} from "./helpers/runtime/profile.js";
import {AniListClient} from "./helpers/integration/anilist.js";
import {TmdbClient} from "./helpers/integration/tmdb.js";
import {IgdbClient} from "./helpers/integration/igdb.js";
import {handleAniListLinkMessage} from "./src/integrations/anilist-embed.js";
import {handleSocialLinkMessage} from "./src/integrations/social-embed.js";
import {SteamClient} from "./helpers/integration/steam.js";
import {closeDatabase,initDatabase} from "./database.js";
import {claimDueMediaNightResults,dueDailyDeliveries,dueDailySchedules,markDailyDelivery,markMediaNightResultPublished,prepareDailyDelivery,rankingResults,dueReleaseDeliveries,dueReleaseSchedules,markReleaseDelivery,prepareReleaseDelivery,upcomingProviderReleases} from "./helpers/community/community.js";
import {claimDueReadingReminders,markReadingReminderSent} from "./helpers/community/community-reading.js";
import {claimDueMediaAutomationRules,claimDueMediaAutomationDeliveries,createMediaAutomationDiscussion,markMediaAutomationDelivery,queueMediaAutomationRelease,releaseMediaAutomationRuleClaim} from "./helpers/community/community-automation.js";
import {createCommandRegistry} from "./src/registry.js";
import {isFeatureEnabled} from "./helpers/runtime/settings.js";
import {initCommandAccessSchema,isCommandAccessAllowed} from "./helpers/runtime/command-access.js";
import {deleteGuildData,ensureGuildRetentionSettings,getGuildRetentionSettings,isGuildRetentionConfigured,isGuildSetupComplete,recordGuildInviter,retryDepartedGuildDeletions} from "./helpers/runtime/guild-retention.js";
import {isGuildLanguageConfigured} from "./helpers/runtime/languages.js";
import {homeEmbed} from "./helpers/runtime/discord.js";
import {handleConsentButton,initUserConsentSchema,requireCurrentConsent} from "./helpers/security/terms-consent.js";
import {safeInteractionErrorMessage} from "./helpers/commands/command-errors.js";
import {createIssueLog,issueHashNotice} from "./helpers/runtime/issue-logs.js";
import {onCustomRoleMemberAdd,onCustomRoleMemberRemove,onCustomRoleMemberUpdate,onCustomRoleRoleDelete,reconcileCustomRoleGuild} from "./helpers/custom-roles/custom-role-lifecycle.js";
import {startCustomRolePicker,stopCustomRolePicker} from "./helpers/custom-roles/custom-role-picker-server.js";
import {startDashboardBridge,stopDashboardBridge} from "./helpers/runtime/dashboard-bridge.js";
import {startMediaNotificationScheduler,stopMediaNotificationScheduler} from "./helpers/media/media-notifications.js";
import {getReleaseDigestEntityEvents,previousReleaseDigestEventWindow} from "./helpers/community/community-releases.js";
import {startMusicScheduler,stopMusicScheduler} from "./helpers/integration/music.js";
import {configureMediaStorage,processArchiveAssetCleanup} from "./helpers/media/media-storage.js";
import {configureCustomRoleIconSourceLimit} from "./helpers/custom-roles/custom-role-images.js";

const config=loadConfig();configureLogger(config.logLevel);configureTranslation(config.translation);configureMediaStorage(config);configureCustomRoleIconSourceLimit(config.customRoleIconSourceMaxBytes);configureArchiveAccess(config.archiveGlobalModeratorIds);
const client=new Client({intents:[GatewayIntentBits.Guilds,GatewayIntentBits.GuildMembers,GatewayIntentBits.GuildMessages,GatewayIntentBits.MessageContent]});
const aniListEmbedClient=new AniListClient(config.anilistApiUrl,config.anilistTimeoutMs);
const socialEmbedSteamClient=new SteamClient(config.steamApiKey);
const releaseCalendarTmdbClient=new TmdbClient(config.tmdbBearerToken);
const releaseCalendarIgdbClient=new IgdbClient(config.igdbClientId,config.igdbClientSecret);
const commands=createCommandRegistry(config);
const commandByName=new Map<string,FeatureCommand>(commands.map(command=>[command.data.name,command]));
const updateDeferredInteractions=new WeakSet<Interaction>();
let atlasBridge: Server | undefined;
let reconciliationTimer: NodeJS.Timeout | undefined;
let dailyWorkerTimer: NodeJS.Timeout | undefined;
async function startAtlasBridge(): Promise<void> {
 const secret=config.dashboardBridgeSecret;
 if(Buffer.byteLength(secret)<32){logger.warn("Knowledge Atlas dashboard bridge disabled; DASHBOARD_BRIDGE_SECRET must contain at least 32 bytes.");return;}
 const port=config.dashboardAtlasBridgePort;
 if(!Number.isInteger(port)||port<1||port>65535)throw new Error("DASHBOARD_ATLAS_BRIDGE_PORT must be a valid TCP port.");
 const expected=Buffer.from(secret);
 const server=createServer((request,response)=>{
  const send=(status:number,payload:unknown)=>{if(response.headersSent)return;response.writeHead(status,{"content-type":"application/json; charset=utf-8","cache-control":"no-store"});response.end(JSON.stringify(payload));};
  if(request.method!=="GET"){send(405,{error:"Method not allowed."});return;}
  let parsed:URL;
  try{parsed=new URL(request.url??"/","http://127.0.0.1");}catch{send(400,{error:"Invalid request."});return;}
  if(parsed.pathname!=="/atlas"){send(404,{error:"Route not found."});return;}
  const authorization=request.headers.authorization??"";
  const supplied=Buffer.from(authorization.startsWith("Bearer ")?authorization.slice(7):"");
  if(supplied.length!==expected.length||!timingSafeEqual(supplied,expected)){send(401,{error:"Unauthorized."});return;}
  const guildId=parsed.searchParams.get("guild_id")??"";
  const title=(parsed.searchParams.get("title")??"").trim();
  const category=normalizeAtlasCategory(parsed.searchParams.get("category")??"");
  const rawUrl=parsed.searchParams.get("url");
  const safeUrl=rawUrl?safeAtlasUrl(rawUrl):null;
  if(!/^\d{17,20}$/.test(guildId)||!title||title.length>256||!category||(rawUrl&&!safeUrl)){send(400,{error:"A valid guild, title and media category are required."});return;}
  void isGuildSetupComplete(guildId).then((configured)=>{
   if(!configured){send(423,{error:"Server data-retention setup is required before Atlas can be used."});return;}
   return findAtlasGraph(guildId,{title,category,url:safeUrl},{maxDepth:2,maxNodes:24,perNodeLimit:8}).then((graph)=>{
    send(200,{
     root:{title,category,url:safeUrl},
     relationships:graph.directRelationships,
     graph:{rootId:graph.rootId,nodes:graph.nodes,edges:graph.edges,truncated:graph.truncated},
    });
   });
  }).catch((error)=>{
   logger.error("Knowledge Atlas lookup failed",{guildId,reason:error instanceof Error?error.message:"Unknown error"});
   send(503,{error:"The Knowledge Atlas is temporarily unavailable."});
  });
 });
 await new Promise<void>((resolve,reject)=>{
  const failed=(error:Error)=>reject(error);
  server.once("error",failed);
  server.listen(port,"127.0.0.1",()=>{server.off("error",failed);resolve();});
 });
 atlasBridge=server;
 logger.info("Knowledge Atlas dashboard bridge ready",{host:"127.0.0.1",port});
}
async function closeAtlasBridge(): Promise<void> {
 const server=atlasBridge;atlasBridge=undefined;
 if(!server)return;
 await new Promise<void>((resolve)=>server.close(()=>resolve()));
}


async function respondWithError(interaction:Interaction,message:string):Promise<void>{
 if(!interaction.isRepliable())return;
 try{
  if(interaction.isMessageComponent()&&interaction.deferred&&updateDeferredInteractions.has(interaction)){
   await interaction.followUp({content:message,flags:MessageFlags.Ephemeral});
   updateDeferredInteractions.delete(interaction);
  }
  else if(interaction.deferred)await interaction.editReply({content:message,embeds:[],components:[]});
  else if(interaction.replied)await interaction.followUp({content:message,flags:MessageFlags.Ephemeral});
  else await interaction.reply({content:message,flags:MessageFlags.Ephemeral});
 }catch(error){logger.warn("Failed to respond to interaction error",{reason:error instanceof Error?error.message:"Unknown error"});}
}
function interactionIssueAction(interaction:Interaction):string{
 if(interaction.isChatInputCommand())return "/"+interaction.commandName;
 if(interaction.isAutocomplete())return "/"+interaction.commandName+" autocomplete";
 if(interaction.isMessageComponent())return "/"+(interaction.customId.split(":",1)[0]??"component")+" component · "+interaction.customId;
 return "Discord interaction";
}
function commandOpensModal(interaction:Interaction):boolean{
 if(!interaction.isChatInputCommand())return false;
 const action=interaction.options.getString("action")??"";
 switch(interaction.commandName){
  case "feedback":return true;
  case "archive":return action==="collection-add"||action==="trail-add";
  case "custom-role":
   if(action==="create"||action==="rename")return !interaction.options.getString("name");
   if(action==="color")return !interaction.options.getString("color");
   if(action==="gradient")return !interaction.options.getString("color")||!interaction.options.getString("secondary_color");
   if(action==="icon")return !interaction.options.getString("emoji");
   if(action==="move"){
    const placement=interaction.options.getString("placement");
    return placement!=="above"&&placement!=="below";
   }
   if(action==="cooldown")return interaction.options.getInteger("seconds")===null;
   return false;
  case "play":
   if(action==="create-pack")return !interaction.options.getString("title");
   if(action==="add-question")return ["pack_id","question","correct_answer","source_url"].some(name=>!interaction.options.getString(name));
   return action==="edit-question";
  case "profile":
   if(action==="link-anilist"||action==="link-steam")return !interaction.options.getString("account");
   return action==="affinity"&&!interaction.options.getUser("member");
  case "settings":return action==="media-region"&&!interaction.options.getString("region");
  default:return false;
 }
}
function componentOpensModal(interaction:Interaction):boolean{
 if(!interaction.isMessageComponent())return false;
 const parts=interaction.customId.split(":");
 const [prefix,action,third]=parts;
 switch(prefix){
  case "archive":
   return (action==="usual"&&third==="yes")
    ||["configure-types","search","soundtrack-search","collection-feature","report","report-entry","submit-category"].includes(action??"");
  case "community":
   return ["session-nominate","tournament-create","season-create","season-add","ranking-create","ranking-candidate","session-create","discussion-create","daily-configure","daily-submit"].includes(action??"");
  case "custom-role":
   return ["words","create","rename","color","gradient","icon","move","cooldown"].includes(parts[2]??"");
  case "discover":
   return interaction.customId==="discover:airing"||interaction.customId==="discover:compare"
    ||interaction.customId.startsWith("discover:search:")||interaction.customId==="discover:creator-map";
  case "music":return interaction.customId==="music:add-channel";
  case "play":
   return ["create-pack","edit-pack","answer","question-pack"].includes(action??"");
  case "profile":return ["link-anilist","link-steam","affinity"].includes(action??"");
  case "settings":
   return ["settings:automation:add","settings:media-digest:configure","settings:media-region:open","settings:media-follows:add","settings:media-follows:subscriptions"].includes(interaction.customId);
  case "moderators":return action==="add"||action==="remove";
  default:return false;
 }
}

function componentUsesEphemeralLoadingReply(interaction:Interaction):boolean{
 if(!interaction.isMessageComponent())return false;
 const [prefix,action,third]=interaction.customId.split(":");
 if(prefix==="music"&&action==="test")return true;
 if(prefix==="discover"&&["trending","random","recommend","similar"].includes(action??""))return true;
 if(prefix==="custom-role"&&["legacy-takeover","legacy-archive"].includes(third??""))return true;
 return prefix==="settings"&&action==="backups"&&["create","verify","rehearse"].includes(third??"");
}
function interactionLoadingActivity(interaction:Interaction):string{
 const stages:Record<string,string> = {
  discover:"Searching media providers…",
  archive:"Fetching Archive entries…",
  community:"Fetching community activity…",
  play:"Loading game session data…",
  profile:"Fetching server profile data…",
  "custom-role":"Checking role permissions…",
  settings:"Fetching server settings…",
  music:"Fetching artist and release data…",
  language:"Saving server language…",
  help:"Preparing the command guide…",
  privacy:"Loading privacy details…",
  feedback:"Saving your feedback…",
  log:"Fetching diagnostic records…",
  moderators:"Fetching moderator access…",
  planned:"Checking feature availability…",
  timestamp:"Calculating timestamp…",
  invite:"Preparing the invite link…",
  convertlinks:"Checking media links…",
  "admin-login":"Verifying dashboard access…",
 };
 if(interaction.isChatInputCommand()){
  const name=interaction.commandName;
  const action=interaction.options.getString("action")??"";
  if(name==="discover"){
   const view=interaction.options.getString("view")??"search";
   return view==="random"?"Finding a random media pick…"
    :view==="trending"?"Fetching trending media…"
    :view==="edition"?"Checking exact book editions…"
    :view==="metadata"?"Fetching provider metadata…"
    :view==="releases"?"Fetching release dates…"
    :view==="grid"?"Matching the media grid…"
    :"Searching media providers…";
  }
  if(name==="archive"){
   if(["browse","search","panel-of-the-day","spotlight-list","mine","collection-list","trail-list"].includes(action))return "Fetching Archive entries…";
   if(["edit","delete","submit","finish-upload","collection-add","collection-remove","trail-add"].includes(action))return "Updating Archive records…";
   return "Loading the Community Archive…";
  }
  if(name==="community"){
   if(action==="media-night")return "Fetching Media Night candidates…";
   if(action==="calendar")return "Fetching the release calendar…";
   if(["history","spotlights","tournaments","seasons","reading-list"].includes(action))return "Fetching community activity…";
   if(["daily-submit","ranking-create","ranking-candidate","session-create","session-nominate","discussion-create"].includes(action))return "Saving community activity…";
   return "Loading community records…";
  }
  if(name==="play"){
   if(["start","join","resume","answer","next","finish","active-sessions"].includes(action))return "Loading the game session…";
   if(["packs","catalogue","manage-packs","challenge-centre","puzzle-room"].includes(action))return "Fetching question packs…";
   if(["create-pack","add-question","edit-question"].includes(action))return "Saving game content…";
   return "Loading the game room…";
  }
  if(name==="profile"){
   if(action.startsWith("leaderboard"))return "Fetching leaderboard data…";
   if(["link-anilist","link-steam","unlink"].includes(action))return "Updating account connections…";
   return "Fetching profile data…";
  }
  if(name==="settings"){
   if(action==="diagnostics")return "Running server diagnostics…";
   if(action==="data-backups")return "Checking backup records…";
   if(["toggle","media-region"].includes(action))return "Updating server configuration…";
   return "Fetching server settings…";
  }
  if(name==="music")return "Checking music providers…";
  if(name==="custom-role")return "Checking role permissions…";
  return stages[name]??("Processing /"+name+"…");
 }
 if(interaction.isModalSubmit()){
  const prefix=interaction.customId.split(":")[0]??"";
  const modalStages:Record<string,string> = {
   archive:"Saving your Archive contribution…",
   community:"Saving community changes…",
   "custom-role":"Updating your role settings…",
   discover:"Searching media providers…",
   music:"Adding the artist tracker…",
   play:"Saving game content…",
   profile:"Updating your profile…",
   settings:"Saving server settings…",
   feedback:"Submitting your feedback…",
   moderators:"Updating moderator access…",
   "admin-login":"Verifying dashboard credentials…",
  };
  return modalStages[prefix]??"Saving your changes…";
 }
 if(interaction.isMessageComponent()){
  const [prefix,action] = interaction.customId.split(":");
  if(prefix==="discover")return action==="tmdb-details"||action==="similar"?"Fetching related media details…":"Searching media providers…";
  if(prefix==="archive")return action==="browse-category"||action==="open-entry"||action==="collection-open"?"Fetching Archive entries…":"Updating Archive records…";
  if(prefix==="community")return action==="daily-poll"||action==="tournament-vote"?"Saving your vote…":"Fetching community activity…";
  if(prefix==="play")return action==="answer"?"Checking your answer…":"Loading game session…";
  if(prefix==="profile")return "Fetching profile data…";
  if(prefix==="custom-role")return "Updating role configuration…";
  if(prefix==="settings")return "Fetching server settings…";
  if(prefix==="music")return "Fetching artist and release data…";
  if(prefix==="moderators")return "Fetching moderator access…";
  if(prefix==="admin-login")return "Refreshing dashboard access…";
  return "Processing your request…";
 }
 return "Processing your request…";
}
async function routeInteraction(interaction:Interaction):Promise<void>{
 if(!interaction.guildId){
  if(interaction.isAutocomplete()){await interaction.respond([]).catch(()=>undefined);return;}
  if(interaction.isRepliable()){
   const message="Lemegeton commands and controls are available inside a Discord server, not in direct messages.";
   try{if(interaction.deferred)await interaction.editReply(message);else if(!interaction.replied)await interaction.reply({content:message,flags:MessageFlags.Ephemeral});}catch{}
  }
  return;
 }
 try{
  if(interaction.isButton()&&await handleConsentButton(interaction))return;
  const accessCommand=interaction.isChatInputCommand()||interaction.isAutocomplete()
   ?interaction.commandName
   :interaction.isMessageComponent()?interaction.customId.split(":",1)[0]??"":"";
  if(accessCommand&&commandByName.has(accessCommand)
   &&!await isCommandAccessAllowed(interaction.guildId,accessCommand,interaction.channelId,interaction.member)){
   if(interaction.isAutocomplete()){await interaction.respond([]);return;}
   if(interaction.isRepliable())await interaction.reply({content:"You can't use this command in this channel or with your current server roles.",flags:MessageFlags.Ephemeral});
   return;
  }
  if(!await requireCurrentConsent(interaction))return;
  const retentionConfigured=await isGuildRetentionConfigured(interaction.guildId);
  const languageConfigured=await isGuildLanguageConfigured(interaction.guildId);
  if(!retentionConfigured||!languageConfigured){
   const retentionCommand=interaction.isChatInputCommand()&&interaction.commandName==="settings"&&(interaction.options.getString("action")??"retention")==="retention";
   const retentionButton=interaction.isButton()&&/^settings:retention:(delete|retain)$/.test(interaction.customId);
   const languageCommand=interaction.isChatInputCommand()&&interaction.commandName==="language";
   const languageAutocomplete=interaction.isAutocomplete()&&interaction.commandName==="language";
   if(!retentionCommand&&!retentionButton&&!languageCommand&&!languageAutocomplete){
    if(interaction.isAutocomplete()){await interaction.respond([]);return;}
    const missing:string[]=[];
    if(!retentionConfigured)missing.push("Choose what happens to this server's data when Lemegeton leaves with /settings action:retention.");
    if(!languageConfigured)missing.push("Choose this server's language with /language.");
    if(interaction.isRepliable()){
     await interaction.deferReply({flags:MessageFlags.Ephemeral});
     const setupMessage=await translateGuildUiText(interaction.guildId,"Lemegeton is locked until this server completes its required setup:\n\n"+missing.join("\n")+"\n\nOnly the person who invited Lemegeton or a member with Manage Server permission can complete these settings.");
     await interaction.editReply({content:setupMessage});
    }
    return;
   }
  }
  if(interaction.isButton()&&Boolean((interaction.component as {disabled?:boolean}).disabled)){
   if(!interaction.replied&&!interaction.deferred){await interaction.deferReply({flags:MessageFlags.Ephemeral});await interaction.editReply({content:await translateGuildUiText(interaction.guildId,"This control is disabled and cannot be used.")});}
   return;
  }
  if(interaction.isAutocomplete()){const command=commandByName.get(interaction.commandName);if(command?.handleAutocomplete){await command.handleAutocomplete(interaction);}else{await interaction.respond([]);}return;}
  if(interaction.isChatInputCommand()){const command=commandByName.get(interaction.commandName);if(!command){await interaction.deferReply({flags:MessageFlags.Ephemeral});await interaction.editReply({content:await translateGuildUiText(interaction.guildId,"That feature command is not available.")});return;}if(["discover","archive","community","play","profile","custom-role"].includes(interaction.commandName)&&interaction.guildId&&interaction.commandName!=="settings"&&!await isFeatureEnabled(interaction.guildId,interaction.commandName)){await interaction.deferReply({flags:MessageFlags.Ephemeral});await interaction.editReply({content:await translateGuildUiText(interaction.guildId,"This feature is currently disabled by this server’s settings.")});return;}if(commandOpensModal(interaction))await command.execute(interaction);else await withFakeLoading(interaction,interactionLoadingActivity(interaction),"reply",current=>command.execute(current));return;}
  if(!interaction.isButton()&&!interaction.isStringSelectMenu()&&!interaction.isRoleSelectMenu()&&!interaction.isChannelSelectMenu()&&!interaction.isModalSubmit())return;
  const prefix=interaction.customId.split(":",1)[0]??"";const command=commandByName.get(prefix);if(!command)return;
  const invoke=async(current:Interaction):Promise<boolean>=>{
   if(current.isButton())return command.handleButton?command.handleButton(current):false;
   if(current.isStringSelectMenu()||current.isRoleSelectMenu()||current.isChannelSelectMenu())return command.handleSelect?command.handleSelect(current):false;
   if(current.isModalSubmit())return command.handleModal?command.handleModal(current):false;
   return false;
  };
  const activity=interactionLoadingActivity(interaction);
  const loadingMode=componentUsesEphemeralLoadingReply(interaction)?"reply":"update";
  if(interaction.isMessageComponent()&&!componentOpensModal(interaction)&&loadingMode==="update")updateDeferredInteractions.add(interaction);
  const handled=interaction.isModalSubmit()
   ?await withFakeLoading(interaction,activity,"reply",invoke)
   :componentOpensModal(interaction)
    ?await invoke(interaction)
    :await withFakeLoading(interaction,activity,loadingMode,invoke);
  if(!handled){
   const message=await translateGuildUiText(interaction.guildId,"This control is no longer available. Reopen the feature command and try again.");
   if(interaction.isMessageComponent()&&interaction.deferred&&updateDeferredInteractions.has(interaction)){
    await interaction.followUp({content:message,flags:MessageFlags.Ephemeral});
   }else if(interaction.deferred||interaction.replied)await interaction.editReply({content:message,embeds:[],components:[]});
   else{await interaction.deferReply({flags:MessageFlags.Ephemeral});await interaction.editReply({content:message});}
  }
  if(interaction.isMessageComponent())updateDeferredInteractions.delete(interaction);
 }catch(error){
  const message=safeInteractionErrorMessage(error);
  logger.error("Discord interaction failed",{interactionId:interaction.id,reason:message});
  let reference:string|undefined;
  if(interaction.guildId){
   try{
    reference=await createIssueLog({
     guildId:interaction.guildId,
     userId:interaction.user.id,
     username:interaction.user.globalName??interaction.user.username,
     interactionId:interaction.id,
     channelId:interaction.channelId,
     command:interactionIssueAction(interaction),
     details:{
      interactionType:interaction.type,
       commandAction:interactionIssueAction(interaction),
       focusedOption:interaction.isAutocomplete()?interaction.options.getFocused(true):undefined,
      commandOptions:interaction.isChatInputCommand()?interaction.options.data:undefined,
      componentCustomId:interaction.isMessageComponent()?interaction.customId:undefined,
      guildId:interaction.guildId,
      channelId:interaction.channelId,
     },
     error,
    });
   }catch(logError){
    logger.error("Could not persist issue diagnostic record",{interactionId:interaction.id,reason:logError instanceof Error?logError.message:"Unknown logging error"});
   }
  }
  await respondWithError(interaction,reference?`${message}\n\n${issueHashNotice(reference)}`:message);
 }
}
async function prepareGuildRetention(guild: Guild): Promise<void> {
 await ensureGuildRetentionSettings(guild.id);
 const current=await getGuildRetentionSettings(guild.id);
 if(current.invited_by)return;
 const botId=client.user?.id;
 if(!botId)return;
 try {
  const audit=await guild.fetchAuditLogs({type:AuditLogEvent.BotAdd,limit:100});
  const entry=audit.entries.find(item=>item.targetId===botId);
  if(entry?.executorId)await recordGuildInviter(guild.id,entry.executorId);
 } catch(error) {
  logger.info("Could not resolve the original bot inviter; Manage Server users can still complete retention setup",{
   guildId:guild.id,reason:error instanceof Error?error.message:"Audit log access unavailable",
  });
 }
}
async function reconcileDepartedGuildProfiles(guilds: Iterable<Guild>): Promise<void> {
 for (const guild of guilds) {
  try {
   if(!await isGuildRetentionConfigured(guild.id))continue;
   const profileUserIds = await getGuildProfileUserIds(guild.id);
   if (!profileUserIds.length) continue;
   const members = await guild.members.fetch();
   const botId = client.user?.id;
   if (!botId || !members.has(botId) || members.size < guild.memberCount) {
    logger.warn("Skipped departed-member profile reconciliation because Discord returned an incomplete guild member list", { guildId: guild.id, expected: guild.memberCount, received: members.size });
    continue;
   }
   const departed = findDepartedGuildProfileIds(profileUserIds, members.keys());
   for (const userId of departed) {
    await removeGuildMemberProfileData(guild.id, userId);
    logger.info("Removed stale guild-scoped profile data for a member who is no longer in the server", { guildId: guild.id, userId });
   }
  } catch (error) {
   logger.warn("Departed-member profile reconciliation failed; no incomplete membership results were used for deletion", { guildId: guild.id, reason: error instanceof Error ? error.message : "Unknown error" });
  }
 }
}
client.once(Events.ClientReady,ready=>{
 logger.info("Lemegeton TypeScript bot connected",{user:ready.user.tag,commands:commands.map(command=>command.data.name)});
 void reconcileDepartedGuildProfiles(ready.guilds.cache.values());
 startMediaNotificationScheduler(client,config);
 startMusicScheduler(client,config);
 for(const guild of ready.guilds.cache.values()){
  void prepareGuildRetention(guild).then(async()=>{
   if(await isGuildSetupComplete(guild.id))await reconcileCustomRoleGuild(guild,config.customRolesMassArchiveThreshold);
  }).catch(error=>logger.error("Guild retention setup initialization failed",{guildId:guild.id,reason:error instanceof Error?error.message:"Unknown error"}));
 }
 void retryDepartedGuildDeletions(ready.guilds.cache.keys()).then(result=>{
  if(result.deleted||result.failed)logger.info("Retried incomplete guild-leave data deletion",{...result});
 }).catch(error=>logger.error("Guild-leave deletion retry scan failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 void startCustomRolePicker(client,config).catch(error=>logger.error("Custom Roles picker startup failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 void startDashboardBridge(client,commands,config).catch(error=>logger.error("Dashboard bot bridge startup failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 reconciliationTimer=setInterval(()=>{
  void (async()=>{
   try{
    const deletion=await retryDepartedGuildDeletions(client.guilds.cache.keys());
    if(deletion.deleted||deletion.failed)logger.info("Retried incomplete guild-leave data deletion",deletion);
    for(const guild of client.guilds.cache.values()){
     if(await isGuildSetupComplete(guild.id))void reconcileCustomRoleGuild(guild,config.customRolesMassArchiveThreshold).catch(error=>logger.error("Custom Roles reconciliation failed",{guildId:guild.id,reason:error instanceof Error?error.message:"Unknown error"}));
    }
   }catch(error){
    logger.error("Guild reconciliation cycle failed",{reason:error instanceof Error?error.message:"Unknown error"});
   }
  })();
 },config.customRolesReconcileMinutes*60_000);
 reconciliationTimer.unref();
});
client.on(Events.GuildCreate,guild=>{
 logger.info("Lemegeton joined a Discord server",{guildId:guild.id,guildName:guild.name,memberCount:guild.memberCount});
 void prepareGuildRetention(guild).catch(error=>logger.error("Could not initialize guild retention setup",{guildId:guild.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.GuildDelete,guild=>{
 void (async()=>{
  if(!guild.available){
   logger.warn("Guild became unavailable; no leave-retention action was applied",{guildId:guild.id,guildName:guild.name});
   return;
  }
  const settings=await getGuildRetentionSettings(guild.id);
  if(settings.leave_action==="delete"){
   const result=await deleteGuildData(guild.id);
   logger.info("Applied the configured delete-on-leave policy",{guildId:guild.id,...result});
  }else{
   logger.info("Retained server data after bot departure",{guildId:guild.id,guildName:guild.name,policy:settings.leave_action??"unset"});
  }
 })().catch(error=>logger.error("Guild leave-retention action failed; server data was not intentionally removed",{guildId:guild.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.ShardDisconnect,(event,shardId)=>{
 logger.warn("Discord gateway shard disconnected",{shardId,code:event.code,reason:event.reason||"No reason supplied"});
});
client.on(Events.ShardResume,(shardId,replayedEvents)=>{
 logger.info("Discord gateway shard resumed",{shardId,replayedEvents});
});
client.on(Events.ShardReconnecting,shardId=>{
 logger.warn("Discord gateway shard reconnecting",{shardId});
});
client.on(Events.Error,error=>{
 logger.error("Discord client emitted an error",{reason:error.message});
});
client.on(Events.GuildMemberUpdate,async(oldMember,newMember)=>{
 if(!await isGuildSetupComplete(newMember.guild.id))return;
 void onCustomRoleMemberUpdate(oldMember,newMember,config.customRolesMassArchiveThreshold).catch(error=>logger.error("Custom Roles member update failed",{guildId:newMember.guild.id,userId:newMember.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.GuildMemberRemove,async member=>{
 if(!await isGuildRetentionConfigured(member.guild.id))return;
 if(await isGuildSetupComplete(member.guild.id)){
  void onCustomRoleMemberRemove(member,config.customRolesMassArchiveThreshold).catch(error=>logger.error("Custom Roles member removal failed",{guildId:member.guild.id,userId:member.id,reason:error instanceof Error?error.message:"Unknown error"}));
 }
 void removeGuildMemberProfileData(member.guild.id,member.id).then(()=>logger.info("Removed guild-scoped AniList/Steam links and profile preferences for departed member",{guildId:member.guild.id,userId:member.id})).catch(error=>logger.error("Could not remove departed member profile data",{guildId:member.guild.id,userId:member.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.GuildRoleDelete,async role=>{
 if(!await isGuildRetentionConfigured(role.guild.id))return;
 void onCustomRoleRoleDelete(role,config.customRolesMassArchiveThreshold).catch(error=>logger.error("Custom Roles role deletion handling failed",{guildId:role.guild.id,roleId:role.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.GuildMemberAdd,async member=>{
 if(!await isGuildSetupComplete(member.guild.id))return;
 void onCustomRoleMemberAdd(member).catch(error=>logger.error("Custom Roles member restoration failed",{guildId:member.guild.id,userId:member.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.InteractionCreate,interaction=>void routeInteraction(interaction));
client.on(Events.MessageCreate,async message=>{
 if(message.guildId&&!await isGuildSetupComplete(message.guildId))return;
 void handleArchiveUploadMessage(message,client).catch(async error=>{
  logger.error("Archive upload processing failed",{guildId:message.guildId,channelId:message.channelId,reason:error instanceof Error?error.message:"Unknown error"});
  if(!message.author.bot&&message.guildId){
   let reference:string|undefined;
   try{
    reference=await createIssueLog({
     guildId:message.guildId,
     userId:message.author.id,
     username:message.author.globalName??message.author.username,
     interactionId:message.id,
     channelId:message.channelId,
     command:"/archive upload",
     details:{messageId:message.id,attachmentCount:message.attachments.size,attachmentNames:[...message.attachments.values()].slice(0,5).map(item=>item.name)},
     error,
    });
   }catch(logError){
    logger.error("Could not persist Archive upload issue reference",{messageId:message.id,reason:logError instanceof Error?logError.message:"Unknown logging error"});
   }
   const response="The Archive could not store that upload privately. No public file link was created."+(reference?"\n\n"+issueHashNotice(reference):"");
   await message.reply({content:response,allowedMentions:{parse:[]}}).catch(()=>undefined);
  }
 });
 void handleAniListLinkMessage(message,aniListEmbedClient).catch(async error=>{
  logger.error("AniList link embed failed",{guildId:message.guildId,channelId:message.channelId,messageId:message.id,reason:error instanceof Error?error.message:"Unknown error"});
  if(!message.author.bot&&message.guildId){
   let reference:string|undefined;
   try{
    reference=await createIssueLog({
     guildId:message.guildId,
     userId:message.author.id,
     username:message.author.globalName??message.author.username,
     interactionId:message.id,
     channelId:message.channelId,
     command:"AniList link embed",
     details:{messageId:message.id,urlCount:(message.content.match(/https?:\/\//gi)??[]).length},
     error,
    });
   }catch(logError){
    logger.error("Could not persist AniList embed issue reference",{messageId:message.id,reason:logError instanceof Error?logError.message:"Unknown logging error"});
   }
   const response="I could not build the AniList embed for that link."+(reference?"\n\n"+issueHashNotice(reference):"");
   await message.reply({content:response,allowedMentions:{parse:[]}}).catch(()=>undefined);
  }
 });
 void handleSocialLinkMessage(message,socialEmbedSteamClient).catch(async error=>{
  logger.error("Social link integration failed",{guildId:message.guildId,channelId:message.channelId,messageId:message.id,reason:error instanceof Error?error.message:"Unknown error"});
  if(!message.author.bot&&message.guildId){
   let reference:string|undefined;
   try{
    reference=await createIssueLog({
     guildId:message.guildId,
     userId:message.author.id,
     username:message.author.globalName??message.author.username,
     interactionId:message.id,
     channelId:message.channelId,
     command:"Social link integration",
     details:{messageId:message.id,urlCount:(message.content.match(/https?:\/\//gi)??[]).length},
     error,
    });
   }catch(logError){
    logger.error("Could not persist social link issue reference",{messageId:message.id,reason:logError instanceof Error?logError.message:"Unknown logging error"});
   }
   const response="The social link preview could not be created."+(reference?"\n\n"+issueHashNotice(reference):"");
   await message.reply({content:response,allowedMentions:{parse:[]}}).catch(()=>undefined);
  }
 });
});
 
let workerRunning=false;
let dailyWorkerPromise:Promise<void>|undefined;
function scheduleDailyDrops():void{
 if(shuttingDown||dailyWorkerPromise)return;
 dailyWorkerPromise=processDailyDrops().finally(()=>{dailyWorkerPromise=undefined;});
}
async function processDailyDrops():Promise<void>{
 if(workerRunning||!client.isReady())return;workerRunning=true;
 try{
  try {
   const cleanup=await processArchiveAssetCleanup(10,client);
   if(cleanup.failed)logger.warn("Private Archive asset cleanup will retry",{attempted:cleanup.attempted,failed:cleanup.failed});
  } catch(error) {
   logger.warn("Private Archive asset cleanup queue could not be checked",{reason:error instanceof Error?error.message:"Unknown error"});
  }
  for(const schedule of await dueDailySchedules()){
   if(!await isGuildSetupComplete(schedule.guild_id))continue;
   try{await prepareDailyDelivery(schedule);}
   catch(error){logger.error("Could not prepare Daily Drop",{guildId:schedule.guild_id,reason:error instanceof Error?error.message:"Unknown error"});}
  }
  for(const reminder of await claimDueReadingReminders()){
   if(!await isGuildSetupComplete(reminder.guild_id))continue;
   try{
    const thread=await client.channels.fetch(reminder.thread_id);
    if(!thread||!thread.isTextBased()||!("send" in thread))throw new Error("The scheduled Reading Club thread is unavailable.");
    await (thread as TextChannel).send({
     content:`${emoji.bell} **Community Reading Club starts now:** ${reminder.title}. Keep plot spoilers marked with Discord spoiler tags.`,
     allowedMentions:{parse:[]},
    });
    await markReadingReminderSent(reminder.guild_id,reminder.nomination_id);
   }catch(error){
    logger.warn("Scheduled Reading Club notice could not be delivered",{
     guildId:reminder.guild_id,
     nominationId:reminder.nomination_id,
     reason:error instanceof Error?error.message:"Unknown delivery error",
    });
   }
  }
  for(const delivery of await dueDailyDeliveries()){
   if(!await isGuildSetupComplete(delivery.guild_id))continue;
   try{
    const channel=await client.channels.fetch(delivery.channel_id);
    if(!channel||!channel.isTextBased()||!("send" in channel)){await markDailyDelivery(delivery.id,delivery.claim_token,"pending",undefined,"Configured channel is unavailable.");continue;}
    const pollRows = delivery.format === "poll" && delivery.options.length >= 2
     ? [new ActionRowBuilder<ButtonBuilder>().addComponents(delivery.options.slice(0,5).map((option,index)=>
        new ButtonBuilder().setCustomId("community:daily-poll:"+delivery.id+":"+index)
         .setLabel(option.slice(0,80)).setStyle(ButtonStyle.Secondary),
       ))]
     : [];
    const description = delivery.content + (delivery.format === "poll" ? "\n\nChoose an option below. You can change your vote." : "");
    const message=await(channel as TextChannel).send({
     embeds:[homeEmbed("Daily Drop · "+delivery.title,description,delivery.source_url?[{name:"Source",value:"[Open original source]("+delivery.source_url+")"}]:[])],
     components:pollRows,
     allowedMentions:{parse:[]},
    });
    await markDailyDelivery(delivery.id,delivery.claim_token,"sent",message.id);
   }catch(error){await markDailyDelivery(delivery.id,delivery.claim_token,"pending",undefined,error instanceof Error?error.message:"Unknown delivery error").catch(()=>undefined);}
  }
  for(const schedule of await dueReleaseSchedules()){
   if(!await isGuildSetupComplete(schedule.guild_id))continue;
   try{await prepareReleaseDelivery(schedule);}
   catch(error){logger.error("Could not queue a release digest",{guildId:schedule.guild_id,reason:error instanceof Error?error.message:"Unknown error"});}
  }
  for(const delivery of await dueReleaseDeliveries()){
   if(!await isGuildSetupComplete(delivery.guild_id))continue;
   try{
    const releaseWindowStart=new Date(delivery.window_start);
    const releaseWindowEnd=new Date(delivery.window_end);
    const entityWindow=previousReleaseDigestEventWindow(releaseWindowStart,releaseWindowEnd);
    const [calendar,entityEvents,channel]=await Promise.all([
     upcomingProviderReleases(
      aniListEmbedClient,
      releaseCalendarTmdbClient,
      releaseWindowStart,
      releaseWindowEnd,
      delivery.region,
      delivery.categories,
      releaseCalendarIgdbClient,
     ),
     getReleaseDigestEntityEvents({
      guildId:delivery.guild_id,
      windowStart:entityWindow.start,
      windowEnd:entityWindow.end,
      entityTypes:delivery.entity_types,
      entityIds:delivery.entity_ids,
     }),
     client.channels.fetch(delivery.channel_id),
    ]);
    if(calendar.unavailableProviders.length&&!calendar.results.length&&!entityEvents.length){
     throw new Error("Digest release providers unavailable: "+calendar.unavailableProviders.join(", "));
    }
    if(!channel||!channel.isTextBased()||!("send" in channel)||!("guildId" in channel)||channel.guildId!==delivery.guild_id){
     throw new Error("The configured digest destination is unavailable in its server.");
    }
    const start=releaseWindowStart;
    const end=releaseWindowEnd;
    const localFormatter=new Intl.DateTimeFormat("en-GB",{
     dateStyle:"medium",timeStyle:"short",timeZone:delivery.time_zone,
    });
    const period=localFormatter.format(start)+" – "+localFormatter.format(end)+" ("+delivery.time_zone+")";
    const releaseFields=calendar.results.slice(0,8).map(item=>({
     name:item.title.slice(0,180)+" · <t:"+Math.floor(item.when.getTime()/1000)+":R>",
     value:item.category.toUpperCase()+" · "+item.provider+"\n[Open source]("+item.url+")",
     inline:false,
    }));
    const entityFields=entityEvents.slice(0,8).flatMap(item=>{
     let source:URL;
     try{source=new URL(item.source_url);if(source.protocol!=="https:"||source.username||source.password)return [];}
     catch{return [];}
     const eventAt=new Date(item.event_at);
     const timestamp=Number.isFinite(eventAt.getTime())?Math.floor(eventAt.getTime()/1000):0;
     return [{
      name:item.entity_type.toUpperCase()+" · "+item.title.slice(0,160),
      value:item.description.slice(0,300)+" · Detected <t:"+timestamp+":R>\n["+item.provider+" source]("+source.toString()+")",
      inline:false,
     }];
    });
    const fields=[
     ...releaseFields,
     ...entityFields,
     ...(calendar.unavailableProviders.length?[{
      name:"Providers temporarily unavailable",
      value:calendar.unavailableProviders.join(", ").slice(0,1000),
      inline:false,
     }]:[]),
    ];
    const description="Window: "+period+". Region: "+delivery.region+"."
     +(fields.length?"":" No provider-dated releases or selected followed-entity updates matched this window.");
    const message=await (channel as TextChannel).send({
     embeds:[homeEmbed("Lemegeton · Media Digest",description,fields)],
     allowedMentions:{parse:[]},
    });
    await markReleaseDelivery(delivery.id,delivery.claim_token,"sent",message.id);
   }catch(error){
    await markReleaseDelivery(delivery.id,delivery.claim_token,"pending",undefined,error instanceof Error?error.message:"Unknown digest delivery error").catch(()=>undefined);
    logger.warn("Media digest delivery failed and was queued for retry",{
     guildId:delivery.guild_id,deliveryId:delivery.id,reason:error instanceof Error?error.message:"Unknown error",
    });
   }
  }
  for(const rule of await claimDueMediaAutomationRules()){
   if(!await isGuildSetupComplete(rule.guild_id)){await releaseMediaAutomationRuleClaim(rule);continue;}
   try{
    const from=new Date();
    const to=new Date(from.getTime()+14*24*60*60*1000);
    const calendar=await upcomingProviderReleases(
     aniListEmbedClient,releaseCalendarTmdbClient,from,to,rule.region,rule.categories,
    );
    if(calendar.unavailableProviders.length)throw new Error("Automation providers unavailable: "+calendar.unavailableProviders.join(", "));
    for(const release of calendar.results)await queueMediaAutomationRelease(rule,release);
    await releaseMediaAutomationRuleClaim(rule);
   }catch(error){
    await releaseMediaAutomationRuleClaim(rule,true).catch(()=>undefined);
    logger.warn("Media automation rule could not be evaluated; it will retry",{
     guildId:rule.guild_id,ruleId:rule.id,reason:error instanceof Error?error.message:"Unknown error",
    });
   }
  }
  for(const delivery of await claimDueMediaAutomationDeliveries()){
   if(!await isGuildSetupComplete(delivery.guild_id)){
    await markMediaAutomationDelivery(delivery,"pending",undefined,"Server setup is not complete.");
    continue;
   }
   try{
    const channel=await client.channels.fetch(delivery.channel_id);
    if(!channel||!channel.isTextBased()||!("send" in channel)||!("guildId" in channel)||channel.guildId!==delivery.guild_id){
     throw new Error("The automation destination is unavailable in its configured server.");
    }
    let discussionLink:string|undefined;
    if(delivery.action==="discussion"){
     await createMediaAutomationDiscussion({delivery,creatorId:config.applicationId});
     const sourceCategory=delivery.provider.startsWith("AniList")?"ANIME":delivery.provider.startsWith("TMDB Movies")?"MOVIE":"TV";
     const destinationUrl="https://discord.com/channels/"+delivery.guild_id+"/"+delivery.channel_id;
     await recordAtlasRelationship({
      sourceTitle:delivery.title,sourceCategory,sourceUrl:delivery.source_url,
      targetTitle:"Release discussion · "+delivery.title,targetCategory:"DISCUSSION",targetUrl:destinationUrl,
      relationshipType:"community release discussion",sourceKind:"community",sourceLabel:"Media Automation Studio",
      guildId:delivery.guild_id,evidence:"Created from a provider-dated media release.",
     });
     discussionLink=destinationUrl;
    }
    const releaseTimestamp=Math.floor(new Date(delivery.release_at).getTime()/1000);
    const message=await(channel as TextChannel).send({
     embeds:[homeEmbed(
      "Media automation · "+delivery.title,
      "A "+delivery.provider+" release event matched the **"+delivery.rule_name+"** rule. Release: <t:"+releaseTimestamp+":F>.",
      [
       {name:"Provider source",value:"[Open release record]("+delivery.source_url+")",inline:false},
       ...(discussionLink?[{name:"Community discussion",value:"[Open server discussion]("+discussionLink+")",inline:false}]:[]),
      ],
     )],
     allowedMentions:{parse:[]},
    });
    await markMediaAutomationDelivery(delivery,"sent",message.id);
   }catch(error){
    await markMediaAutomationDelivery(delivery,"pending",undefined,error instanceof Error?error.message:"Unknown delivery error").catch(()=>undefined);
    logger.warn("Media automation delivery failed and was queued for retry",{
     guildId:delivery.guild_id,deliveryId:delivery.id,reason:error instanceof Error?error.message:"Unknown error",
    });
   }
  }
  for(const session of await claimDueMediaNightResults()){
   if(!await isGuildSetupComplete(session.guild_id))continue;
   try{
    const [results,channel]=await Promise.all([
     rankingResults(session.guild_id,session.id),
     client.channels.fetch(session.channel_id),
    ]);
    if(!channel||!channel.isTextBased()||!("send" in channel))throw new Error("The Media Night channel is unavailable.");
    const fields=results.map((item,index)=>({
     name:`${index+1}. ${item.title.slice(0,180)}`,
     value:`${item.votes} vote${item.votes===1?"":"s"}`,
     inline:false,
    }));
    const description=results.length
     ? "Final community vote results. Ties are ordered by the time the candidate was submitted."
     : "Media Night closed without any votes.";
    await (channel as TextChannel).send({
     embeds:[homeEmbed(`Media Night results · ${session.title}`,description,fields)],
     allowedMentions:{parse:[]},
    });
    await markMediaNightResultPublished(session.id);
   }catch(error){
    logger.warn("Media Night final results could not be delivered; the session remains queued for retry",{
     guildId:session.guild_id,sessionId:session.id,reason:error instanceof Error?error.message:"Unknown delivery error",
    });
   }
  }
 }catch(error){logger.error("Daily Drop worker failed",{reason:error instanceof Error?error.message:"Unknown error"});}
 finally{workerRunning=false;}
}
let shuttingDown=false;
async function shutdown(signal:NodeJS.Signals):Promise<void>{
 if(shuttingDown)return;
 shuttingDown=true;
 logger.info("Shutting down Lemegeton",{signal});
 if(reconciliationTimer){clearInterval(reconciliationTimer);reconciliationTimer=undefined;}
 if(dailyWorkerTimer){clearInterval(dailyWorkerTimer);dailyWorkerTimer=undefined;}
 await dailyWorkerPromise?.catch(error=>logger.error("Daily worker shutdown failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 await stopMediaNotificationScheduler();
 await stopMusicScheduler();
 await stopCustomRolePicker().catch(error=>logger.error("Custom Roles picker shutdown failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 await stopDashboardBridge().catch(error=>logger.error("Dashboard bridge shutdown failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 client.destroy();
 await closeAtlasBridge().catch(error=>logger.error("Atlas bridge shutdown failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 await closeDatabase().catch(error=>logger.error("Database shutdown failed",{reason:error instanceof Error?error.message:"Unknown error"}));
}
async function start():Promise<void>{
 await initDatabase(config.database);await initUserConsentSchema();await initCommandAccessSchema();await startAtlasBridge();await client.login(config.discordToken);
 dailyWorkerTimer=setInterval(()=>scheduleDailyDrops(),30_000);dailyWorkerTimer.unref();
 scheduleDailyDrops();
}
process.once("SIGINT",()=>void shutdown("SIGINT"));process.once("SIGTERM",()=>void shutdown("SIGTERM"));
void start().catch(async error=>{logger.error("Lemegeton startup failed",{reason:error instanceof Error?error.message:"Unknown error"});await shutdown("SIGTERM");process.exitCode=1;});
