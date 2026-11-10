import test from "node:test";
import assert from "node:assert/strict";
import {archiveEntryLookupScope,parseAniListMangaReference,parsePanelChapterCaption} from "../helpers/archive/archive.js";

test("Manga panel chapter metadata supports numbered and unknown chapters",()=>{
 assert.deepEqual(parsePanelChapterCaption("Chapter 12 — Final battle"),{chapterNumber:"12",caption:"Final battle"});
 assert.deepEqual(parsePanelChapterCaption("ch. 12.5"),{chapterNumber:"12.5",caption:""});
 assert.deepEqual(parsePanelChapterCaption("N/A"),{chapterNumber:"N/A",caption:""});
 assert.deepEqual(parsePanelChapterCaption("12 - Short note"),{chapterNumber:"12",caption:"Short note"});
});

test("Manga panel chapter metadata rejects incomplete input",()=>{
 for(const value of ["","chapter twelve","Chapter 12 —","N/A —"])assert.throws(()=>parsePanelChapterCaption(value));
});

test("AniList manga references accept numeric IDs and canonical HTTPS URLs only",()=>{
 assert.deepEqual(parseAniListMangaReference("123"),{id:"123",url:"https://anilist.co/manga/123"});
 assert.deepEqual(parseAniListMangaReference("https://anilist.co/manga/456/slug"),{id:"456",url:"https://anilist.co/manga/456"});
 assert.deepEqual(parseAniListMangaReference(""),{id:null,url:null});
 for(const value of ["0","http://anilist.co/manga/4","https://example.com/manga/4","https://anilist.co/anime/4"])assert.throws(()=>parseAniListMangaReference(value));
});


test("Archive pending-entry lookups stay guild-scoped unless global scope is explicit",()=>{
 assert.equal(
  archiveEntryLookupScope(true,false),
  "visibility = 'server' AND created_guild_id = $2",
 );
 assert.equal(
  archiveEntryLookupScope(true,true),
  "visibility = 'global'",
 );
 assert.equal(
  archiveEntryLookupScope(false,false),
  "(visibility = 'global' OR (visibility = 'server' AND created_guild_id = $2)) AND status = 'approved'",
 );
 assert.equal(
  archiveEntryLookupScope(false,true),
  "visibility = 'global'",
 );
});
