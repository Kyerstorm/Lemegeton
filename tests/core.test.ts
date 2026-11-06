import test from "node:test";
import assert from "node:assert/strict";
import {loadConfig} from "../Helpers/config.js";
import {isValidHttpsUrl,normalizeTags} from "../Helpers/security.js";
import {validateSteamId} from "../Helpers/steam.js";
import {nextLocalOccurrence} from "../Helpers/community.js";
import {classifyArchiveUpload} from "../Helpers/media-storage.js";
import {ARCHIVE_TAG_CATALOG,searchArchiveTags} from "../Helpers/archive.js";
import {AniListClient} from "../Helpers/anilist.js";
import {normalizeAtlasTitle,normalizeAtlasCategory,safeAtlasUrl} from "../Helpers/atlas.js";
import {FEATURE_NAMES,isFeatureName} from "../Helpers/settings.js";

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
test("Server settings expose only the five registered feature environments",()=>{
 assert.deepEqual(FEATURE_NAMES,["discover","archive","community","play","profile"]);
 assert.equal(isFeatureName("archive"),true);
 assert.equal(isFeatureName("custom-role"),false);
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
 assert.equal(ARCHIVE_TAG_CATALOG.some(tag=>tag==="nsfw"||tag==="mature"),false);
 assert.ok(searchArchiveTags("").length<=25);
});
