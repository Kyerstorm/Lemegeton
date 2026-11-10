import test from "node:test";
import assert from "node:assert/strict";
import {parseGridSourceUrls,parseGridTitles,renderMediaGrid} from "../helpers/media/media-grid.js";
import sharp from "sharp";

test("3x3 grid title parser keeps exactly nine cleaned titles",()=>{
 const titles=parseGridTitles(" One \n Two\nThree\nFour\nFive\nSix\nSeven\nEight\nNine ");
 assert.equal(titles.length,9);
 assert.deepEqual(titles.slice(0,2),["One","Two"]);
 assert.equal(titles[8],"Nine");
});

test("3x3 provider URL parser resolves exact AniList media and character IDs",()=>{
 const anime=parseGridSourceUrls(Array.from({length:9},(_,i)=>"https://anilist.co/anime/"+(100+i)+"/title/"));
 assert.ok(anime);
 assert.deepEqual(anime[0],{kind:"anime",id:100});
 const manga=parseGridSourceUrls(Array.from({length:9},(_,i)=>"https://anilist.co/manga/"+(200+i)+"/title"));
 assert.deepEqual(manga?.[0],{kind:"manga",id:200});
 const characters=parseGridSourceUrls(Array.from({length:9},(_,i)=>"https://anilist.co/character/"+(300+i)+"/"));
 assert.deepEqual(characters?.[0],{kind:"character",id:300});
});

test("3x3 provider URL parser resolves IGDB slugs and returns null for title input",()=>{
 const games=parseGridSourceUrls(Array.from({length:9},(_,i)=>"https://www.igdb.com/games/game-"+i));
 assert.deepEqual(games?.[0],{kind:"game",slug:"game-0"});
 assert.equal(parseGridSourceUrls(Array.from({length:9},(_,i)=>"Title "+i)),null);
});

test("3x3 provider URL parser rejects mixed, insecure and untrusted URLs",()=>{
 const valid=Array.from({length:9},(_,i)=>"https://anilist.co/anime/"+(100+i)+"/");
 assert.throws(()=>parseGridSourceUrls(["http://anilist.co/anime/1",...valid.slice(1)]),/HTTPS/);
 assert.throws(()=>parseGridSourceUrls(["https://evil.example/anime/1",...valid.slice(1)]),/AniList or IGDB/);
 assert.throws(()=>parseGridSourceUrls(["https://user@anilist.co/anime/1",...valid.slice(1)]),/unsupported URL details/);
 assert.throws(()=>parseGridSourceUrls(["https://anilist.co/anime/1?next=2",...valid.slice(1)]),/unsupported URL details/);
 assert.throws(()=>parseGridSourceUrls(["https://anilist.co/character/1",...valid.slice(1)]),/same media type/);
 assert.throws(()=>parseGridSourceUrls(["https://anilist.co/anime/1","Title Two",...valid.slice(2)]),/HTTPS/);
});

test("3x3 grid title parser rejects wrong counts and oversized entries",()=>{
 assert.throws(()=>parseGridTitles("one\ntwo"),/exactly nine/);
 assert.throws(()=>parseGridTitles(Array.from({length:10},(_,i)=>"Title "+i).join("\n")),/exactly nine/);
 assert.throws(()=>parseGridTitles(["x",...Array.from({length:8},(_,i)=>"Title "+i)].join("\n")),/between 2 and 200/);
 assert.throws(()=>parseGridTitles(["x".repeat(201),...Array.from({length:8},(_,i)=>"Title "+i)].join("\n")),/between 2 and 100/);
});

test("3x3 media grid renders a bounded PNG with placeholders for unresolved covers",async()=>{
 const image=await renderMediaGrid(Array.from({length:9},(_,index)=>({title:`Title ${index+1}`,image:null})));
 const metadata=await sharp(image).metadata();
 assert.equal(metadata.format,"png");
 assert.equal(metadata.width,692);
 assert.equal(metadata.height,1022);
});
