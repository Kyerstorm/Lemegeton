import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  addExpeditionStage,createExpedition,getExpedition,joinExpedition,listExpeditions,publishExpedition,submitExpeditionAnswer,
} from "../helpers/community/expedition.js";

test("Expedition stages keep answers private and advance participants independently",async()=>{
 const directory=await mkdtemp(join(tmpdir(),"lemegeton-expedition-"));
 await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
 try{
  const secret="a-long-test-secret-that-is-never-stored-in-the-database";
  const id=await createExpedition({guildId:"111111111111111111",ownerId:"222222222222222222",title:"Knowledge trail",description:"A safe, multi-step knowledge challenge."});
  assert.equal((await listExpeditions("111111111111111111","222222222222222222")).some(item=>item.id===id),true);
  assert.equal((await listExpeditions("111111111111111111","333333333333333333")).some(item=>item.id===id),false);
  assert.equal(await getExpedition("111111111111111111",id,"333333333333333333"),null);
  await addExpeditionStage({guildId:"111111111111111111",expeditionId:id,ownerId:"222222222222222222",title:"First clue",prompt:"What is the capital of France?",answer:"Paris",hint:"It is a European capital.",answerSecret:secret});
  await addExpeditionStage({guildId:"111111111111111111",expeditionId:id,ownerId:"222222222222222222",title:"Second clue",prompt:"Name the red planet.",answer:"Mars",answerSecret:secret});
  await publishExpedition({guildId:"111111111111111111",expeditionId:id,ownerId:"222222222222222222"});
  assert.equal((await getExpedition("111111111111111111",id,"333333333333333334"))?.stages.length,0);
  assert.equal(await joinExpedition("111111111111111111",id,"333333333333333333"),true);
  assert.equal((await getExpedition("111111111111111111",id,"333333333333333333"))?.stages.length,1);
  const wrong=await submitExpeditionAnswer({guildId:"111111111111111111",expeditionId:id,userId:"333333333333333333",answer:"London",answerSecret:secret});
  assert.equal(wrong.correct,false);
  const first=await submitExpeditionAnswer({guildId:"111111111111111111",expeditionId:id,userId:"333333333333333333",answer:"  PARIS ",answerSecret:secret});
  assert.equal(first.correct,true);assert.equal(first.nextStage,2);
  const second=await submitExpeditionAnswer({guildId:"111111111111111111",expeditionId:id,userId:"333333333333333333",answer:"Mars",answerSecret:secret});
  assert.equal(second.completed,true);
  const loaded=await getExpedition("111111111111111111",id,"333333333333333333");
  assert.equal(loaded?.viewerProgress?.status,"completed");
  assert.equal(loaded?.expedition.status,"completed");
  assert.equal(loaded?.stages[0]?.prompt,"What is the capital of France?");
  assert.equal("answer_hash" in (loaded?.stages[0]??{}),false);
  assert.equal(await getExpedition("222222222222222222",id),null);
 }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

test("Expedition answer guesses are rate limited per participant and stage",async()=>{
 const directory=await mkdtemp(join(tmpdir(),"lemegeton-expedition-attempts-"));
 await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
 try{
  const secret="a-long-test-secret-for-expedition-rate-limits";
  const id=await createExpedition({
   guildId:"111111111111111111",ownerId:"222222222222222222",
   title:"Rate limited trail",description:"A bounded answer challenge.",
  });
  await addExpeditionStage({
   guildId:"111111111111111111",expeditionId:id,ownerId:"222222222222222222",
   title:"First stage",prompt:"A simple clue.",answer:"Correct",answerSecret:secret,
  });
  await publishExpedition({guildId:"111111111111111111",expeditionId:id,ownerId:"222222222222222222"});
  await joinExpedition("111111111111111111",id,"333333333333333333");
  for(let attempt=0;attempt<5;attempt+=1){
   const result=await submitExpeditionAnswer({
    guildId:"111111111111111111",expeditionId:id,userId:"333333333333333333",
    answer:"Wrong answer "+attempt,answerSecret:secret,
   });
   assert.equal(result.correct,false);
  }
  await assert.rejects(()=>submitExpeditionAnswer({
   guildId:"111111111111111111",expeditionId:id,userId:"333333333333333333",
   answer:"Correct",answerSecret:secret,
  }),/attempt limit/);
 }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

