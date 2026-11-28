import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase, query } from "../src/utility/database/libsql/database.js";
import {
  cancelTimeCapsule, claimDueTimeCapsules, contributeToTimeCapsule, createTimeCapsule,
  finishTimeCapsuleReveal, getTimeCapsule, listTimeCapsules, sealTimeCapsule,
} from "../helpers/community/time-capsules.js";

test("time capsules collect one revision per contributor and release only after owner sealing",async()=>{
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-capsules-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const id=await createTimeCapsule({
      guildId:"111111111111111111",ownerId:"222222222222222222",channelId:"333333333333333333",
      title:"Future message",description:"A note for later",releaseAt:new Date(Date.now()+60*60_000).toISOString(),
      audience:"guild",
    });
    await contributeToTimeCapsule({guildId:"111111111111111111",capsuleId:id,contributorId:"222222222222222222",content:"First version"});
    await contributeToTimeCapsule({guildId:"111111111111111111",capsuleId:id,contributorId:"222222222222222222",content:"Final version"});
    const details=await getTimeCapsule("111111111111111111",id,"222222222222222222");
    assert.equal(details?.capsule.contribution_count,1);
    assert.equal(details?.contributions[0]?.content,"Final version");
    await assert.rejects(()=>sealTimeCapsule({guildId:"111111111111111111",capsuleId:id,ownerId:"444444444444444444"}),/Only the capsule owner/);
    await sealTimeCapsule({guildId:"111111111111111111",capsuleId:id,ownerId:"222222222222222222"});
    assert.equal((await getTimeCapsule("111111111111111111",id,"222222222222222222"))?.capsule.status,"sealed");
    const sealedForOther=await getTimeCapsule("111111111111111111",id,"666666666666666666");
    assert.equal(sealedForOther?.capsule.description,"");
    assert.equal(sealedForOther?.contributions[0]?.content,"");
    await query("UPDATE time_capsules SET release_at='2000-01-01T00:00:00.000Z' WHERE id=$1",[id]);
    const due=await claimDueTimeCapsules();
    assert.equal(due.length,1);
    assert.equal(due[0]?.id,id);
    assert.equal(await finishTimeCapsuleReveal({
      guildId:"111111111111111111",capsuleId:id,claimToken:due[0]!.claim_token,messageId:"555555555555555555",
    }),true);
    assert.equal((await getTimeCapsule("111111111111111111",id,"222222222222222222"))?.capsule.status,"revealed");
    const revealedForMember=await getTimeCapsule("111111111111111111",id,"666666666666666666");
    assert.equal(revealedForMember?.capsule.description,"A note for later");
    assert.equal(revealedForMember?.contributions[0]?.content,"Final version");
  }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

test("capsules are isolated by guild and can be cancelled by their owner",async()=>{
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-capsule-cancel-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const id=await createTimeCapsule({
      guildId:"111111111111111111",ownerId:"222222222222222222",channelId:"333333333333333333",
      title:"Private note",releaseAt:new Date(Date.now()+60*60_000).toISOString(),audience:"owner",
    });
    assert.equal(await getTimeCapsule("222222222222222222",id),null);
    await cancelTimeCapsule({guildId:"111111111111111111",capsuleId:id,ownerId:"222222222222222222"});
    assert.equal((await getTimeCapsule("111111111111111111",id,"222222222222222222"))?.capsule.status,"cancelled");
  }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

test("owner-audience capsules stay private and accept contributions only from their owner",async()=>{
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-capsule-owner-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const id=await createTimeCapsule({
      guildId:"111111111111111111",ownerId:"222222222222222222",channelId:"333333333333333333",
      title:"Personal capsule",releaseAt:new Date(Date.now()+60*60_000).toISOString(),audience:"owner",
    });
    assert.equal(await getTimeCapsule("111111111111111111",id,"444444444444444444"),null);
    assert.equal((await getTimeCapsule("111111111111111111",id,"222222222222222222"))?.capsule.status,"collecting");
    assert.equal((await listTimeCapsules("111111111111111111",15,"444444444444444444")).some(item=>item.id===id),false);
    assert.equal((await listTimeCapsules("111111111111111111",15,"222222222222222222")).some(item=>item.id===id),true);
    await assert.rejects(()=>contributeToTimeCapsule({
      guildId:"111111111111111111",capsuleId:id,contributorId:"444444444444444444",content:"Not my capsule",
    }),/not accepting contributions/);
    await contributeToTimeCapsule({
      guildId:"111111111111111111",capsuleId:id,contributorId:"222222222222222222",content:"Owner-only contribution",
    });
  }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

test("contributor-audience capsule content is visible only to contributors after reveal",async()=>{
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-capsule-contributors-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const id=await createTimeCapsule({
      guildId:"111111111111111111",ownerId:"222222222222222222",channelId:"333333333333333333",
      title:"Group capsule",description:"A group message",releaseAt:new Date(Date.now()+60*60_000).toISOString(),
      audience:"contributors",
    });
    await contributeToTimeCapsule({guildId:"111111111111111111",capsuleId:id,contributorId:"222222222222222222",content:"Owner contribution"});
    await contributeToTimeCapsule({guildId:"111111111111111111",capsuleId:id,contributorId:"444444444444444444",content:"Member contribution"});
    await sealTimeCapsule({guildId:"111111111111111111",capsuleId:id,ownerId:"222222222222222222"});
    await query("UPDATE time_capsules SET release_at='2000-01-01T00:00:00.000Z' WHERE id=$1",[id]);
    const [due]=await claimDueTimeCapsules();
    assert.equal(due?.id,id);
    assert.equal(await finishTimeCapsuleReveal({
      guildId:"111111111111111111",capsuleId:id,claimToken:due!.claim_token,
    }),true);
    const outsider=await getTimeCapsule("111111111111111111",id,"555555555555555555");
    assert.equal(outsider?.capsule.description,"");
    assert.deepEqual(outsider?.contributions.map(item=>item.content),["",""]);
    const contributor=await getTimeCapsule("111111111111111111",id,"444444444444444444");
    assert.equal(contributor?.capsule.description,"A group message");
    assert.deepEqual(contributor?.contributions.map(item=>item.content),["Owner contribution","Member contribution"]);
  }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

test("stale capsule worker claims are failed for reconciliation and are not automatically resent",async()=>{
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-capsule-stale-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const id=await createTimeCapsule({
      guildId:"111111111111111111",ownerId:"222222222222222222",channelId:"333333333333333333",
      title:"Interrupted delivery",description:"Do not duplicate this reveal",
      releaseAt:new Date(Date.now()-60_000).toISOString(),audience:"guild",
    });
    await contributeToTimeCapsule({
      guildId:"111111111111111111",capsuleId:id,contributorId:"222222222222222222",content:"Stored contribution",
    });
    await sealTimeCapsule({guildId:"111111111111111111",capsuleId:id,ownerId:"222222222222222222"});
    await query(
      "UPDATE time_capsules SET status='revealing',claim_token='expired-claim',claimed_at=datetime('now','-10 minutes') WHERE id=$1",
      [id],
    );
    const due=await claimDueTimeCapsules();
    assert.equal(due.length,0);
    const status=await query("SELECT status,delivery_error,claim_token FROM time_capsules WHERE id=$1 AND guild_id=$2",[id,"111111111111111111"]);
    assert.equal(status[0]?.status,"failed");
    assert.match(String(status[0]?.delivery_error),/status unknown/i);
    assert.equal(status[0]?.claim_token,null);
    assert.equal((await claimDueTimeCapsules()).length,0);
  }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

