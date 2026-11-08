import test from "node:test";
import assert from "node:assert/strict";
import {buildAniListTrailerUrl} from "../helpers/anilist.js";

test("AniList trailers produce safe YouTube and Dailymotion links",()=>{
 assert.equal(buildAniListTrailerUrl("youtube","aBC_123-XYZ"),"https://youtu.be/aBC_123-XYZ");
 assert.equal(buildAniListTrailerUrl("dailymotion","x7tgad0"),"https://www.dailymotion.com/video/x7tgad0");
});

test("unsupported sites and malformed trailer IDs are ignored",()=>{
 assert.equal(buildAniListTrailerUrl("Vimeo","123456"),null);
 assert.equal(buildAniListTrailerUrl("youtube","javascript:alert(1)"),null);
 assert.equal(buildAniListTrailerUrl("dailymotion","bad/id"),null);
 assert.equal(buildAniListTrailerUrl(null,"123456"),null);
});
