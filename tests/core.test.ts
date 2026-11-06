import test from "node:test";
import assert from "node:assert/strict";
import {loadConfig} from "../Helpers/config.js";
import {isValidHttpsUrl,normalizeTags} from "../Helpers/security.js";
import {validateSteamId} from "../Helpers/steam.js";
import {nextLocalOccurrence} from "../Helpers/community.js";
import {classifyArchiveUpload} from "../Helpers/media-storage.js";

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
