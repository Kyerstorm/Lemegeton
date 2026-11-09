import test from "node:test";
import assert from "node:assert/strict";
import {parseOwnedSteamGames} from "../helpers/providers/steam.js";

test("owned Steam games normalize total playtime and top games",()=>{
 const summary=parseOwnedSteamGames([{appid:1,name:"First",playtime_forever:120,img_icon_url:"abc"},{appid:2,name:"Second",playtime_forever:360},{appid:3,name:"Invalid",playtime_forever:-20},{appid:0,name:"Invalid app"},{appid:4,name:"Third",playtime_forever:60}]);
 assert.equal(summary.totalPlaytimeMinutes,540);
 assert.deepEqual(summary.topGames.map(game=>game.name),["Second","First","Third"]);
 assert.equal(summary.topGames[1]?.icon,"https://media.steampowered.com/steamcommunity/public/images/apps/1/abc.jpg");
});

test("missing owned-game lists are treated as empty summaries",()=>{
 assert.deepEqual(parseOwnedSteamGames(null),{totalPlaytimeMinutes:0,topGames:[]});
});
