import test from "node:test";
import assert from "node:assert/strict";
import {parseCreator} from "../helpers/anilist.js";

test("AniList creator records preserve occupations and linked media",()=>{
 const creator=parseCreator({id:42,name:{full:"Example Creator"},siteUrl:"https://anilist.co/staff/42",image:{large:"https://s4.anilist.co/file/anilistcdn/staff/large/b42.jpg"},description:"A creator",primaryOccupations:["Writer","Illustrator"],yearsActive:[2000],staffMedia:{edges:[{staffRole:"Original Creator",node:{id:9,type:"MANGA",siteUrl:"https://anilist.co/manga/9",title:{english:"Example Comic"}}}]}});
 assert.ok(creator);assert.equal(creator.name,"Example Creator");assert.deepEqual(creator.occupations,["Writer","Illustrator"]);assert.deepEqual(creator.yearsActive,[2000]);assert.equal(creator.media[0]?.title,"Example Comic");
});

test("AniList creator parser rejects untrusted profile and media URLs",()=>{
 assert.equal(parseCreator({id:1,name:{full:"Creator"},siteUrl:"http://anilist.co/staff/1"}),null);
 const creator=parseCreator({id:1,name:{full:"Creator"},siteUrl:"https://anilist.co/staff/1",staffMedia:{edges:[{staffRole:"Writer",node:{id:2,type:"ANIME",siteUrl:"https://example.com/anime/2",title:{romaji:"Bad"}}}]}});
 assert.deepEqual(creator?.media,[]);
});
