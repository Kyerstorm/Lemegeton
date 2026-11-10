import {Client,Events,GatewayIntentBits,MessageFlags,type Interaction,type TextChannel} from "discord.js";
import {createServer, type Server} from "node:http";
import {timingSafeEqual} from "node:crypto";
import {findAtlasRelationships,normalizeAtlasCategory,safeAtlasUrl} from "./helpers/providers/atlas.js";
import {loadConfig} from "./helpers/runtime/config.js";
import {configureLogger,logger} from "./helpers/runtime/logger.js";
import type {FeatureCommand} from "./helpers/commands/command.js";
import {handleArchiveUploadMessage} from "./helpers/archive/archive.js";
import {AniListClient} from "./helpers/providers/anilist.js";
import {TmdbClient} from "./helpers/providers/tmdb.js";
import {handleAniListLinkMessage} from "./helpers/embeds/anilist.js";
import {closeDatabase,initDatabase} from "./database.js";
import {claimDueMediaNightResults,dueDailyDeliveries,dueDailySchedules,markDailyDelivery,markMediaNightResultPublished,prepareDailyDelivery,rankingResults,dueReleaseDeliveries,dueReleaseSchedules,markReleaseDelivery,prepareReleaseDelivery,upcomingProviderReleases} from "./helpers/community/community.js";
import {claimDueReadingReminders,markReadingReminderSent} from "./helpers/community/community-reading.js";
import {createCommandRegistry} from "./src/registry.js";
import {isFeatureEnabled} from "./helpers/runtime/settings.js";
import {homeEmbed} from "./helpers/runtime/discord.js";
import {handleConsentButton,initUserConsentSchema,requireCurrentConsent} from "./helpers/security/terms-consent.js";
import {safeInteractionErrorMessage} from "./helpers/commands/command-errors.js";
import {createIssueLog,issueHashNotice} from "./helpers/runtime/issue-logs.js";
import {onCustomRoleMemberAdd,onCustomRoleMemberRemove,onCustomRoleMemberUpdate,onCustomRoleRoleDelete,reconcileCustomRoleGuild} from "./helpers/custom-roles/custom-role-lifecycle.js";
import {startCustomRolePicker,stopCustomRolePicker} from "./helpers/custom-roles/custom-role-picker-server.js";
import {startDashboardBridge,stopDashboardBridge} from "./helpers/runtime/dashboard-bridge.js";
import {startMediaNotificationScheduler,stopMediaNotificationScheduler} from "./helpers/media/media-notifications.js";

const config=loadConfig();configureLogger(config.logLevel);
const client=new Client({intents:[GatewayIntentBits.Guilds,GatewayIntentBits.GuildMembers,GatewayIntentBits.GuildMessages,GatewayIntentBits.MessageContent]});
const aniListEmbedClient=new AniListClient(config.anilistApiUrl,config.anilistTimeoutMs);
const releaseCalendarTmdbClient=new TmdbClient(config.tmdbBearerToken);
const commands=createCommandRegistry(config);
const commandByName=new Map<string,FeatureCommand>(commands.map(command=>[command.data.name,command]));
let atlasBridge: Server | undefined;
let reconciliationTimer: NodeJS.Timeout | undefined;
let dailyWorkerTimer: NodeJS.Timeout | undefined;
async function startAtlasBridge(): Promise<void> {
 const secret=process.env.DASHBOARD_BRIDGE_SECRET?.trim()??"";
 if(Buffer.byteLength(secret)<32){logger.warn("Knowledge Atlas dashboard bridge disabled; DASHBOARD_BRIDGE_SECRET must contain at least 32 bytes.");return;}
 const port=Number(process.env.DASHBOARD_ATLAS_BRIDGE_PORT??"8093");
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
  void findAtlasRelationships(guildId,title,category,safeUrl,30).then((relationships)=>{
   send(200,{root:{title,category,url:safeUrl},relationships});
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
 try{if(interaction.deferred)await interaction.editReply({content:message,embeds:[],components:[]});
 else if(interaction.replied)await interaction.followUp({content:message,flags:MessageFlags.Ephemeral});
 else await interaction.reply({content:message,flags:MessageFlags.Ephemeral});}
 catch(error){logger.warn("Failed to respond to interaction error",{reason:error instanceof Error?error.message:"Unknown error"});}
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
  if(!await requireCurrentConsent(interaction))return;
  if(interaction.isButton()&&Boolean((interaction.component as {disabled?:boolean}).disabled)){
   if(!interaction.replied&&!interaction.deferred)await interaction.reply({content:"This control is disabled and cannot be used.",flags:MessageFlags.Ephemeral});
   return;
  }
  if(interaction.isAutocomplete()){const command=commandByName.get(interaction.commandName);if(command?.handleAutocomplete){await command.handleAutocomplete(interaction);}else{await interaction.respond([]);}return;}
  if(interaction.isChatInputCommand()){const command=commandByName.get(interaction.commandName);if(!command){await interaction.reply({content:"That feature command is not available.",flags:MessageFlags.Ephemeral});return;}if(["discover","archive","community","play","profile","custom-role"].includes(interaction.commandName)&&interaction.guildId&&interaction.commandName!=="settings"&&!await isFeatureEnabled(interaction.guildId,interaction.commandName)){await interaction.reply({content:"This feature is currently disabled by this server’s settings.",flags:MessageFlags.Ephemeral});return;}await command.execute(interaction);return;}
  if(!interaction.isButton()&&!interaction.isStringSelectMenu()&&!interaction.isRoleSelectMenu()&&!interaction.isChannelSelectMenu()&&!interaction.isModalSubmit())return;
  const prefix=interaction.customId.split(":",1)[0]??"";const command=commandByName.get(prefix);if(!command)return;
  const handled=interaction.isButton()?await(command.handleButton?.(interaction)??false)
   :(interaction.isStringSelectMenu()||interaction.isRoleSelectMenu()||interaction.isChannelSelectMenu())?await(command.handleSelect?.(interaction)??false)
   :await(command.handleModal?.(interaction)??false);
  if(!handled&&!interaction.replied&&!interaction.deferred)await interaction.reply({content:"This control is no longer available. Reopen the feature command and try again.",flags:MessageFlags.Ephemeral});
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
     command:interaction.isChatInputCommand()?"/"+interaction.commandName:interaction.isAutocomplete()?"autocomplete":interaction.isMessageComponent()?interaction.customId:"interaction",
     details:{
      interactionType:interaction.type,
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
client.once(Events.ClientReady,ready=>{
 logger.info("Lemegeton TypeScript bot connected",{user:ready.user.tag,commands:commands.map(command=>command.data.name)});
 startMediaNotificationScheduler(client,config);
 void startCustomRolePicker(client,config).catch(error=>logger.error("Custom Roles picker startup failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 void startDashboardBridge(client,commands,config).catch(error=>logger.error("Dashboard bot bridge startup failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 for(const guild of ready.guilds.cache.values()){
  void reconcileCustomRoleGuild(guild).catch(error=>logger.error("Initial Custom Roles reconciliation failed",{guildId:guild.id,reason:error instanceof Error?error.message:"Unknown error"}));
 }
 reconciliationTimer=setInterval(()=>{
  for(const guild of client.guilds.cache.values()){
   void reconcileCustomRoleGuild(guild).catch(error=>logger.error("Custom Roles reconciliation failed",{guildId:guild.id,reason:error instanceof Error?error.message:"Unknown error"}));
  }
 },30*60_000);
 reconciliationTimer.unref();
});
client.on(Events.GuildCreate,guild=>{
 logger.info("Lemegeton joined a Discord server",{guildId:guild.id,guildName:guild.name,memberCount:guild.memberCount});
});
client.on(Events.GuildDelete,guild=>{
 logger.info("Lemegeton left or lost access to a Discord server; retained server data was not deleted",{guildId:guild.id,guildName:guild.name});
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
client.on(Events.GuildMemberUpdate,(oldMember,newMember)=>{
 void onCustomRoleMemberUpdate(oldMember,newMember).catch(error=>logger.error("Custom Roles member update failed",{guildId:newMember.guild.id,userId:newMember.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.GuildMemberRemove,member=>{
 void onCustomRoleMemberRemove(member).catch(error=>logger.error("Custom Roles member removal failed",{guildId:member.guild.id,userId:member.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.GuildRoleDelete,role=>{
 void onCustomRoleRoleDelete(role).catch(error=>logger.error("Custom Roles role deletion handling failed",{guildId:role.guild.id,roleId:role.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.GuildMemberAdd,member=>{
 void onCustomRoleMemberAdd(member).catch(error=>logger.error("Custom Roles member restoration failed",{guildId:member.guild.id,userId:member.id,reason:error instanceof Error?error.message:"Unknown error"}));
});
client.on(Events.InteractionCreate,interaction=>void routeInteraction(interaction));
client.on(Events.MessageCreate,message=>{
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
  for(const schedule of await dueDailySchedules()){
   try{await prepareDailyDelivery(schedule);}
   catch(error){logger.error("Could not prepare Daily Drop",{guildId:schedule.guild_id,reason:error instanceof Error?error.message:"Unknown error"});}
  }
  for(const reminder of await claimDueReadingReminders()){
   try{
    const thread=await client.channels.fetch(reminder.thread_id);
    if(!thread||!thread.isTextBased()||!("send" in thread))throw new Error("The scheduled Reading Club thread is unavailable.");
    await (thread as TextChannel).send({
     content:`🔔 **Community Reading Club starts now:** ${reminder.title}. Keep plot spoilers marked with Discord spoiler tags.`,
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
   try{
    const channel=await client.channels.fetch(delivery.channel_id);
    if(!channel||!channel.isTextBased()||!("send" in channel)){await markDailyDelivery(delivery.id,"pending",undefined,"Configured channel is unavailable.");continue;}
    const message=await(channel as TextChannel).send({embeds:[homeEmbed(`Daily Drop · ${delivery.title}`,delivery.content,delivery.source_url?[{name:"Source",value:`[Open original source](${delivery.source_url})`}]:[])],allowedMentions:{parse:[]}});
    await markDailyDelivery(delivery.id,"sent",message.id);
   }catch(error){await markDailyDelivery(delivery.id,"pending",undefined,error instanceof Error?error.message:"Unknown delivery error").catch(()=>undefined);}
  }
  for(const schedule of await dueReleaseSchedules()){
   try{await prepareReleaseDelivery(schedule);}
   catch(error){logger.error("Could not queue a release digest",{guildId:schedule.guild_id,reason:error instanceof Error?error.message:"Unknown error"});}
  }
  for(const delivery of await dueReleaseDeliveries()){
   try{
    const [calendar,channel]=await Promise.all([
     upcomingProviderReleases(
      aniListEmbedClient,
      releaseCalendarTmdbClient,
      new Date(delivery.window_start),
      new Date(delivery.window_end),
      delivery.region,
      delivery.categories,
     ),
     client.channels.fetch(delivery.channel_id),
    ]);
    if(calendar.unavailableProviders.length)throw new Error(\`Release digest providers unavailable: \${calendar.unavailableProviders.join(", ")}\`);
    if(!channel||!channel.isTextBased()||!("send" in channel))throw new Error("The configured release digest channel is unavailable.");
    const releases=calendar.results;
    const fields=releases.slice(0,20).map((item)=>({
     name:`${item.title.slice(0,180)} · <t:${Math.floor(item.when.getTime()/1000)}:R>`,
     value:`[${item.provider} source](${item.url})`,
     inline:false,
    }));
    const description=releases.length
     ? `Upcoming provider-dated releases for <t:${Math.floor(new Date(delivery.window_start).getTime()/1000)}:d> – <t:${Math.floor(new Date(delivery.window_end).getTime()/1000)}:d>. Region: ${delivery.region}.`
     : `No provider-dated releases were returned for this digest window. Region: ${delivery.region}.`;
    const message=await (channel as TextChannel).send({
     embeds:[homeEmbed("Lemegeton · Release digest",description,fields)],
     allowedMentions:{parse:[]},
    });
    await markReleaseDelivery(delivery.id,"sent",message.id);
   }catch(error){
    await markReleaseDelivery(delivery.id,"pending",undefined,error instanceof Error?error.message:"Unknown delivery error").catch(()=>undefined);
    logger.warn("Release digest delivery failed and was queued for retry",{guildId:delivery.guild_id,deliveryId:delivery.id,reason:error instanceof Error?error.message:"Unknown error"});
   }
  }
  for(const session of await claimDueMediaNightResults()){
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
 await stopCustomRolePicker().catch(error=>logger.error("Custom Roles picker shutdown failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 await stopDashboardBridge().catch(error=>logger.error("Dashboard bridge shutdown failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 client.destroy();
 await closeAtlasBridge().catch(error=>logger.error("Atlas bridge shutdown failed",{reason:error instanceof Error?error.message:"Unknown error"}));
 await closeDatabase().catch(error=>logger.error("Database shutdown failed",{reason:error instanceof Error?error.message:"Unknown error"}));
}
async function start():Promise<void>{
 await initDatabase();await initUserConsentSchema();await startAtlasBridge();await client.login(config.discordToken);
 dailyWorkerTimer=setInterval(()=>scheduleDailyDrops(),30_000);dailyWorkerTimer.unref();
 scheduleDailyDrops();
}
process.once("SIGINT",()=>void shutdown("SIGINT"));process.once("SIGTERM",()=>void shutdown("SIGTERM"));
void start().catch(async error=>{logger.error("Lemegeton startup failed",{reason:error instanceof Error?error.message:"Unknown error"});await shutdown("SIGTERM");process.exitCode=1;});
