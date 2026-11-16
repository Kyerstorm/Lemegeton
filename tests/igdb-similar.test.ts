import test from "node:test";
import assert from "node:assert/strict";
import {IgdbClient} from "../helpers/integration/igdb.js";

test("IGDB similar-game lookup validates IDs before making requests",async()=>{
 const client=new IgdbClient("client","secret");
 await assert.rejects(()=>client.similarGames(0),/positive safe integer/);
 await assert.rejects(()=>client.similarGames(Number.MAX_SAFE_INTEGER+1),/positive safe integer/);
});
