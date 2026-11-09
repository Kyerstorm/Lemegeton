import test from "node:test";
import assert from "node:assert/strict";
import {parseSteamStoreGame,validateSteamId} from "../helpers/providers/steam.js";

test("Steam Store details are normalized without inventing missing metadata",()=>{
 const item=parseSteamStoreGame({
  steam_appid:10,name:"Example Game",short_description:"A <b>short</b> game.",
  header_image:"https://cdn.example/game.jpg",is_free:false,
  price_overview:{initial_formatted:"$19.99",final_formatted:"$9.99",discount_percent:50},
  release_date:{date:"1 Jan, 2026",coming_soon:false},
  genres:[{description:"Adventure"}],categories:[{description:"Co-op"}],
  developers:["Studio"],publishers:["Publisher"],platforms:{windows:true,mac:false,linux:true},
 });
 assert.ok(item);
 assert.equal(item.appId,10);
 assert.equal(item.shortDescription,"A short game.");
 assert.deepEqual(item.price,{initial:"$19.99",final:"$9.99",discountPercent:50});
 assert.deepEqual(item.platforms,["windows","linux"]);
 assert.deepEqual(item.genres,["Adventure"]);
 assert.equal(item.comingSoon,false);
});

test("Steam Store parsing rejects invalid records and unsafe image URLs",()=>{
 assert.equal(parseSteamStoreGame({steam_appid:0,name:"No"}),null);
 assert.equal(parseSteamStoreGame({steam_appid:10,name:"Example",header_image:"http://bad.test/a"} )?.headerImage,null);
 assert.equal(validateSteamId("76561198000000000"),"76561198000000000");
 assert.equal(validateSteamId("not-valid"),null);
});
