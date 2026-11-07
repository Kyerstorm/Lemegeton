import test from "node:test";
import assert from "node:assert/strict";
import {loadConfig} from "../helpers/config.js";
import {isValidHttpsUrl,normalizeTags} from "../helpers/security.js";
import {validateSteamId} from "../helpers/steam.js";
import {nextLocalOccurrence} from "../helpers/community.js";
import {classifyArchiveUpload} from "../helpers/media-storage.js";
import {ARCHIVE_TAG_CATALOG,searchArchiveTags} from "../helpers/archive.js";
import {AniListClient} from "../helpers/anilist.js";
import {getAniListProfileAchievements} from "../helpers/profile.js";
import {allowPickerCall,clearPickerLinks,createPickerLink,lookupPickerLink} from "../helpers/custom-role-picker-tokens.js";
import {isPublicImageAddress} from "../helpers/custom-role-picker-server.js";
import sharp from "sharp";
import {processCustomRoleIconImage,extractCustomRoleAvatarPalette} from "../helpers/custom-role-images.js";
import {normalizeAtlasTitle,normalizeAtlasCategory,safeAtlasUrl} from "../helpers/atlas.js";
import {FEATURE_NAMES,isFeatureName} from "../helpers/settings.js";
import {dashboardCommandRows,dashboardSecretMatches,isDashboardGuildId} from "../helpers/dashboard-bridge.js";
import {customRoleChannelAllowed,customRoleCooldownMessage,parseCustomRoleColor,parseCustomRoleWordList,validateCustomRoleEmoji,validateCustomRoleName} from "../helpers/custom-roles.js";
import {renderAtlasSnapshot} from "../helpers/atlas-renderer.js";
import {filterMediaNotificationCandidates} from "../helpers/media-notifications.js";
import type {AniListRecentlyFinishedMedia} from "../helpers/anilist.js";

test("bot configuration requires valid Discord credentials and validates the AniList endpoint",()=>{
 assert.throws(()=>loadConfig({}),/DISCORD_TOKEN/);
 const config=loadConfig({DISCORD_TOKEN:"token",BOT_ID:"123456789012345678"});
 assert.equal(config.applicationId,"123456789012345678");
 assert.equal(config.anilistApiUrl,"https://graphql.anilist.co/");
 assert.throws(()=>loadConfig({DISCORD_TOKEN:"token",BOT_ID:"123456789012345678",ANILIST_API_URL:"http://example.com"}),/HTTPS/);
});
test("source URLs and Archive tags are normalized and validated",()=>{
 assert.equal(isValidHttpsUrl("https://example.com/a"),"https://example.com/a");
 assert.throws(()=>isValidHttpsUrl("http://example.com"),/HTTPS/);
 assert.deepEqual(normalizeTags("Lore, lore, Manga"),["lore","manga"]);
 assert.throws(()=>normalizeTags("a,b,c",2),/no more than/);
});
test("Steam links accept SteamID64 and reject malformed identifiers",()=>{
 assert.equal(validateSteamId("76561198000000000"),"76561198000000000");
 assert.equal(validateSteamId("not-a-steam-id"),null);
});
test("Daily Drop computes the next local occurrence using the configured timezone",()=>{
 const next=nextLocalOccurrence("Europe/Dublin","18:30",new Date("2026-11-06T18:00:00Z"));
 assert.equal(next.toISOString(),"2026-11-06T18:30:00.000Z");
 assert.throws(()=>nextLocalOccurrence("Mars/Olympus","18:30"),/timezone/i);
});
test("Archive media types are checked against category policy and MIME",()=>{
 const image={name:"panel.png",contentType:"image/png",bytes:Buffer.from([1])};
 assert.equal(classifyArchiveUpload("panels",image).kind,"image");
 assert.throws(()=>classifyArchiveUpload("panels",{...image,name:"panel.mp4",contentType:"video/mp4"}),/not supported/);
 assert.throws(()=>classifyArchiveUpload("panels",{...image,contentType:"image/jpeg"}),/does not match/);
});

test("Knowledge Atlas normalizes media identities and rejects unsafe URLs",()=>{
 assert.equal(normalizeAtlasTitle("  Frieren: Beyond Journey’s End  "),"frieren beyond journey s end");
 assert.equal(normalizeAtlasCategory("light novel"),"LIGHT_NOVEL");
 assert.equal(normalizeAtlasCategory("tv-series"),"TV");
 assert.equal(normalizeAtlasCategory("unsupported"),null);
 assert.equal(safeAtlasUrl("https://anilist.co/anime/1"),"https://anilist.co/anime/1");
 assert.equal(safeAtlasUrl("http://example.com"),null);
 assert.equal(safeAtlasUrl("https://user:pass@example.com"),null);
});
test("Dashboard bridge exposes only the guild's six feature flags and protects settings",()=>{
 const commands=[
  {data:{name:"discover",toJSON:()=>({description:"Find media"})}},
  {data:{name:"custom-role",toJSON:()=>({description:"Manage a personal role"})}},
  {data:{name:"settings",toJSON:()=>({description:"Server settings"})}},
 ] as unknown as Parameters<typeof dashboardCommandRows>[0];
 const settings={discover:false,archive:true,community:true,play:true,profile:true,"custom-role":false};
 const rows=dashboardCommandRows(commands,settings);
 assert.equal(rows[0]?.enabled,false);
 assert.equal(rows[1]?.enabled,false);
 assert.equal(rows[2]?.enabled,true);
 assert.equal(rows[2]?.protected,true);
 assert.equal(rows[2]?.scope,"global");
 assert.equal(rows.length,3);
});

test("Dashboard bridge uses exact shared-secret matching and Discord ID validation",()=>{
 assert.equal(dashboardSecretMatches("same-secret-value","same-secret-value"),true);
 assert.equal(dashboardSecretMatches("same-secret-value","same-secret-value-extra"),false);
 assert.equal(dashboardSecretMatches("short","longer"),false);
 assert.equal(isDashboardGuildId("123456789012345678"),true);
 assert.equal(isDashboardGuildId("123"),false);
 assert.equal(isDashboardGuildId("abc123456789012345"),false);
});

test("Server settings expose all six configurable feature environments",()=>{
 assert.deepEqual(FEATURE_NAMES,["discover","archive","community","play","profile","custom-role"]);
 assert.equal(isFeatureName("archive"),true);
 assert.equal(isFeatureName("custom-role"),true);
});

test("Custom role colors and names follow the existing safety rules",()=>{
 assert.equal(parseCustomRoleColor("#abc"),0xaabbcc);
 assert.equal(parseCustomRoleColor("#000"),0x010101);
 assert.equal(parseCustomRoleColor("not-a-color"),null);
 assert.equal(validateCustomRoleEmoji("🌙"),"🌙");
 assert.equal(validateCustomRoleEmoji("🌙🌙"),null);
 assert.equal(validateCustomRoleEmoji("<:moon:123456789012345678>"),null);
 assert.deepEqual(parseCustomRoleWordList("Spoiler, lore\n Romance\nspoiler"),["spoiler","lore","romance"]);
 assert.deepEqual(parseCustomRoleWordList(" , , "),[]);
 const settings={blocked_words:["spoiler"],removed_default_words:[]};
 assert.equal(validateCustomRoleName("Moonlit Circle",settings).name,"Moonlit Circle");
 assert.match(validateCustomRoleName("a.d.m.i.n",settings).error??"",/admin/i);
 assert.match(validateCustomRoleName("@everyone Crew",settings).error??"",/@everyone/i);
 assert.match(validateCustomRoleName("Spoiler Club",settings).error??"",/blocked word/i);
 assert.match(validateCustomRoleName("Server Team",settings,["Server Team"]).error??"",/already a server role/i);
 assert.equal(validateCustomRoleName("Mod Squad",{...settings,removed_default_words:["mod"]}).name,"Mod Squad");
});

test("Custom role command scope and cooldown are guild-local and deterministic",()=>{
 const settings={command_channel_id:"200"} as Parameters<typeof customRoleChannelAllowed>[2];
 assert.equal(customRoleChannelAllowed("200",null,settings),true);
 assert.equal(customRoleChannelAllowed("201","200",settings),true);
 assert.equal(customRoleChannelAllowed("201",null,settings),false);
 const changedAt="2026-01-01T00:00:00.000Z";
 const record={last_changed_at:changedAt} as Parameters<typeof customRoleCooldownMessage>[0];
 assert.match(customRoleCooldownMessage(record,120,Date.parse(changedAt)+30_000)??"",/2 minutes/);
 assert.equal(customRoleCooldownMessage(record,120,Date.parse(changedAt)+130_000),null);
});


test("Custom role image icons validate PNG/JPEG data and crop to bounded square PNGs",async()=>{
 const png=await sharp({create:{width:180,height:120,channels:4,background:{r:120,g:80,b:200,alpha:1}}}).png().toBuffer();
 const cropped=await processCustomRoleIconImage(png,{x:20,y:10,size:80});
 assert.equal(cropped.side,64);
 assert.deepEqual(cropped.crop,{x:20,y:10,size:80});
 assert.ok(cropped.png.byteLength<=256*1024);
 assert.deepEqual([...cropped.png.subarray(0,8)],[137,80,78,71,13,10,26,10]);
 const jpeg=await sharp(png).jpeg().toBuffer();
 assert.equal((await processCustomRoleIconImage(jpeg)).sourceType,"jpeg");
 await assert.rejects(()=>processCustomRoleIconImage(Buffer.from("not an image")));
 await assert.rejects(()=>processCustomRoleIconImage(png,{x:100,y:90,size:80}),/doesn't fit/);
});

test("Custom role avatar palette ignores transparent pixels and returns distinct RGB colors",async()=>{
 const image=await sharp({create:{width:8,height:8,channels:4,background:{r:255,g:0,b:0,alpha:1}}})
  .composite([{input:await sharp({create:{width:4,height:4,channels:4,background:{r:0,g:0,b:255,alpha:1}}}).png().toBuffer(),left:0,top:0}])
  .png().toBuffer();
 const palette=await extractCustomRoleAvatarPalette(image,5);
 assert.ok(palette.length>0 && palette.length<=5);
 assert.ok(palette.every(color=>Number.isInteger(color)&&color>=0&&color<=0xffffff));
});


test("Custom role picker tokens replace prior links and enforce short write windows",()=>{
 clearPickerLinks();
 const config={customRolePickerIdleTtl:120,customRolePickerMaxTtl:600} as Parameters<typeof createPickerLink>[2];
 const first=createPickerLink("guild-1","member-1",config);
 assert.equal(first.token.length,43);
 assert.ok(lookupPickerLink(first.token));
 const now=Date.now();
 for(let index=0;index<20;index++)assert.equal(allowPickerCall(lookupPickerLink(first.token)!,true,now+index),true);
 assert.equal(allowPickerCall(lookupPickerLink(first.token)!,true,now+21),false);
 const second=createPickerLink("guild-1","member-1",config);
 assert.notEqual(second.token,first.token);
 assert.equal(lookupPickerLink(first.token),null);
 assert.ok(lookupPickerLink(second.token));
 clearPickerLinks();
 assert.equal(lookupPickerLink(second.token),null);
});

test("custom role picker external image fetch rejects private and reserved address ranges",()=>{
 assert.equal(isPublicImageAddress("8.8.8.8"),true);
 assert.equal(isPublicImageAddress("1.1.1.1"),true);
 assert.equal(isPublicImageAddress("127.0.0.1"),false);
 assert.equal(isPublicImageAddress("10.0.0.1"),false);
 assert.equal(isPublicImageAddress("169.254.1.1"),false);
 assert.equal(isPublicImageAddress("192.168.1.1"),false);
 assert.equal(isPublicImageAddress("100.64.0.1"),false);
 assert.equal(isPublicImageAddress("224.0.0.1"),false);
 assert.equal(isPublicImageAddress("::1"),false);
 assert.equal(isPublicImageAddress("fd00::1"),false);
 assert.equal(isPublicImageAddress("2001:db8::1"),false);
 assert.equal(isPublicImageAddress("2001:4860:4860::8888"),true);
 assert.equal(isPublicImageAddress("::ffff:8.8.8.8"),false);
});

test("AniList linked profiles preserve provider-reported statistics and supported milestones",async()=>{
 const client=new AniListClient(undefined,1000,async(_input,init)=>{
  const request=JSON.parse(String(init?.body)) as {query:string;variables:Record<string,unknown>};
  assert.match(request.query,/episodesWatched/);
  assert.match(request.query,/chaptersRead/);
  return new Response(JSON.stringify({data:{User:{
   id:42,name:"VirExample",siteUrl:"https://anilist.co/user/VirExample",
   avatar:{large:"https://anilist.co/avatar.png"},bannerImage:null,about:"A media profile",
   statistics:{
    anime:{count:520,meanScore:84,episodesWatched:6400,minutesWatched:92000,
     statuses:[{status:"COMPLETED",count:400}],formats:[{format:"TV",count:300}],
     genres:[{genre:"Fantasy",count:80}]},
    manga:{count:210,meanScore:78,chaptersRead:9000,volumesRead:360,
     statuses:[{status:"COMPLETED",count:150}],formats:[{format:"MANGA",count:180}],
     genres:[{genre:"Drama",count:70}]}
   },
   favourites:{
    anime:{nodes:[]},manga:{nodes:[]},characters:{nodes:[]}
   }
  }}}),{status:200,headers:{"content-type":"application/json"}});
 });
 const profile=await client.getUser("VirExample");
 assert.ok(profile);
 assert.equal(profile.anime.episodesWatched,6400);
 assert.equal(profile.anime.minutesWatched,92000);
 assert.equal(profile.manga.chaptersRead,9000);
 assert.equal(profile.manga.volumesRead,360);
 assert.deepEqual(profile.anime.statuses,[{status:"COMPLETED",count:400}]);
 assert.deepEqual(profile.manga.formats,[{format:"MANGA",count:180}]);
 assert.deepEqual(
  getAniListProfileAchievements(profile).map(item=>item.title),
  ["Anime shelf","Anime archive","Manga shelf","Manga archive","High anime average"],
 );
});

test("AniList profile milestones do not award thresholds before the provider data reaches them",()=>{
 const profile={
  anime:{count:99,meanScore:90,episodesWatched:null,minutesWatched:null,chaptersRead:null,volumesRead:null,genres:[],statuses:[],formats:[]},
  manga:{count:49,meanScore:0,episodesWatched:null,minutesWatched:null,chaptersRead:null,volumesRead:null,genres:[],statuses:[],formats:[]},
 } as Parameters<typeof getAniListProfileAchievements>[0];
 assert.deepEqual(getAniListProfileAchievements(profile),[]);
});

test("AniList random discovery samples a catalogue page rather than the trending feed", async () => {
 const captured: {body?:{query:string;variables:Record<string,unknown>}} = {};
 const client = new AniListClient(undefined, 1000, async (_input, init) => {
  captured.body = JSON.parse(String(init?.body)) as {query:string;variables:Record<string,unknown>};
  return new Response(JSON.stringify({data:{Page:{media:[]}}}), {status:200,headers:{"content-type":"application/json"}});
 });
 await client.random("ANIME");
 assert.ok(captured.body);
 assert.equal(captured.body.variables.type,"ANIME");
 assert.equal(captured.body.variables.sort,"POPULARITY_DESC");
 assert.equal(captured.body.variables.perPage,10);
 assert.ok(Number(captured.body.variables.page)>=1 && Number(captured.body.variables.page)<=200);
 assert.match(captured.body.query,/Page\(page:\$page,perPage:\$perPage\)/);
});

test("Archive tag search supports incremental multi-tag selection",()=>{
 assert.ok(searchArchiveTags("rom").includes("romance"));
 assert.ok(!searchArchiveTags("rom",["Romance"]).includes("romance"));
 assert.ok(searchArchiveTags("sci").includes("sci-fi"));
 assert.equal((ARCHIVE_TAG_CATALOG as readonly string[]).some(tag=>tag==="nsfw"||tag==="mature"),false);
 assert.ok(searchArchiveTags("").length<=25);
});

test("Media completion notifications filter unsupported and undersized AniList records", () => {
 const makeItem = (
  id: number,
  type: "ANIME" | "MANGA",
  format: string,
  episodes: number | null,
  chapters: number | null,
 ): AniListRecentlyFinishedMedia => ({
  id,type,title:`Media ${id}`,description:null,url:`https://anilist.co/${type.toLowerCase()}/${id}`,
  cover:null,status:"FINISHED",format,episodes,chapters,averageScore:null,genres:[],endDate:null,
 });
 const items = [
  makeItem(1,"ANIME","TV",8,null),
  makeItem(2,"ANIME","TV",7,null),
  makeItem(3,"ANIME","OVA",12,null),
  makeItem(4,"MANGA","MANGA",null,40),
  makeItem(5,"MANGA","MANGA",null,39),
  makeItem(6,"MANGA","ONE_SHOT",null,80),
 ];
 assert.deepEqual(filterMediaNotificationCandidates(items,"ANIME").map(item=>item.id),[1]);
 assert.deepEqual(filterMediaNotificationCandidates(items,"MANGA").map(item=>item.id),[4]);
});

test("Knowledge Atlas snapshots render bounded media nodes and escape provider text", async () => {
 const image = await renderAtlasSnapshot("<Example & Title>", "ANIME", [
  {title:"Related <work>",category:"MANGA",url:"https://anilist.co/manga/1",relationType:"Source Material",source:"AniList",sourceKind:"provider"},
  {title:"Community Pick",category:"BOOK",url:null,relationType:"Community Link",source:"Server archive",sourceKind:"community"},
 ]);
 assert.deepEqual([...image.subarray(0,8)],[137,80,78,71,13,10,26,10]);
 assert.ok(image.byteLength > 1024);
});
