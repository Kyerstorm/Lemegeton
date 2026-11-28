import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase, query } from "../src/utility/database/libsql/database.js";
import {
  advanceCouncilProposal,closeCouncilVoting,closeExpiredCouncilProposals,createCouncilProposal,getCouncilProposal,
  reviewCouncilAmendment,submitCouncilAmendment,submitCouncilVote,verifyCouncilReceipt,
} from "../helpers/community/council.js";

test("Council proposal moves through deliberation, amendments and a unique voting result",async()=>{
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-council-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const proposalId=await createCouncilProposal({
      guildId:"111111111111111111",ownerId:"222222222222222222",title:"Community archive",
      description:"Choose the archive's default visibility.",options:["Server only","Public"],quorum:1,
    });
    const initialOptions=(await getCouncilProposal("111111111111111111",proposalId))!.ballots;
    await assert.rejects(()=>submitCouncilVote({
      guildId:"111111111111111111",proposalId,voterId:"333333333333333333",choices:[initialOptions[0]!.option_key],
    }),/not accepting/);
    await advanceCouncilProposal({guildId:"111111111111111111",proposalId,ownerId:"222222222222222222",action:"deliberation"});
    const amendmentId=await submitCouncilAmendment({
      guildId:"111111111111111111",proposalId,authorId:"333333333333333333",amendment:"Provide a visible opt-in before public sharing.",
    });
    await reviewCouncilAmendment({guildId:"111111111111111111",proposalId,amendmentId,reviewerId:"222222222222222222",accept:true});
    await advanceCouncilProposal({guildId:"111111111111111111",proposalId,ownerId:"222222222222222222",action:"freeze"});
    await advanceCouncilProposal({guildId:"111111111111111111",proposalId,ownerId:"222222222222222222",action:"start-voting",durationMinutes:1});
    const options=(await getCouncilProposal("111111111111111111",proposalId))!.ballots;
    const receipt=await submitCouncilVote({guildId:"111111111111111111",proposalId,voterId:"333333333333333333",choices:[options[0]!.option_key]});
    assert.equal(receipt.length,32);
    assert.equal(await verifyCouncilReceipt({
      guildId:"111111111111111111",proposalId,voterId:"333333333333333333",receipt,
    }),true);
    assert.equal(await verifyCouncilReceipt({
      guildId:"111111111111111111",proposalId,voterId:"333333333333333333",receipt:"0".repeat(32),
    }),false);
    assert.equal(await verifyCouncilReceipt({
      guildId:"222222222222222222",proposalId,voterId:"333333333333333333",receipt,
    }),false);
    await assert.rejects(()=>submitCouncilVote({guildId:"111111111111111111",proposalId,voterId:"333333333333333333",choices:[options[1]!.option_key]}),/already been recorded/);
    await assert.rejects(()=>closeCouncilVoting({guildId:"111111111111111111",proposalId,actorId:"222222222222222222"}),/has not ended/);
    await query("UPDATE council_proposals SET ends_at='2000-01-01 00:00:00' WHERE id=$1",[proposalId]);
    const closed=await closeCouncilVoting({guildId:"111111111111111111",proposalId,actorId:"222222222222222222"});
    assert.equal(closed.status,"passed");
    assert.equal(closed.votes,1);
    assert.equal(closed.tally[0]?.votes,1);
    const current=await getCouncilProposal("111111111111111111",proposalId);
    assert.equal(current?.proposal.vote_count,1);
    assert.equal(current?.proposal.description.includes("Accepted amendment"),true);
  }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

test("Council votes cannot be submitted through another guild",async()=>{
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-council-isolation-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const proposalId=await createCouncilProposal({
      guildId:"111111111111111111",ownerId:"222222222222222222",title:"Test proposal",
      description:"Guild isolation",options:["Yes","No"],
    });
    await assert.rejects(()=>advanceCouncilProposal({guildId:"222222222222222222",proposalId,ownerId:"222222222222222222",action:"deliberation"}),/Only the proposal owner/);
  }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

test("expired Council ballots are finalized by the deadline worker",async()=>{
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-council-deadline-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const proposalId=await createCouncilProposal({
      guildId:"111111111111111111",ownerId:"222222222222222222",
      title:"Expired decision",description:"A proposal with an expired voting window.",options:["Accept","Decline"],
    });
    await advanceCouncilProposal({guildId:"111111111111111111",proposalId,ownerId:"222222222222222222",action:"deliberation"});
    await advanceCouncilProposal({guildId:"111111111111111111",proposalId,ownerId:"222222222222222222",action:"freeze"});
    await advanceCouncilProposal({guildId:"111111111111111111",proposalId,ownerId:"222222222222222222",action:"start-voting",durationMinutes:60});
    await query("UPDATE council_proposals SET ends_at='2000-01-01 00:00:00' WHERE id=$1",[proposalId]);
    assert.equal(await closeExpiredCouncilProposals(),1);
    assert.equal((await getCouncilProposal("111111111111111111",proposalId))?.proposal.status,"failed");
    assert.equal(await closeExpiredCouncilProposals(),0);
  }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});

