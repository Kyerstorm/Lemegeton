import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  addCasebookEvidence,closeCasebookCase,createCasebookCase,getCasebookCase,
  publishCasebookCase,revealCasebookSolution,submitCasebookTheory,unlockNextCasebookEvidence,
} from "../helpers/community/casebook.js";

test("Casebook reveals clues in order, validates theory citations and protects the solution",async()=>{
 const directory=await mkdtemp(join(tmpdir(),"lemegeton-casebook-"));
 await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
 try{
  const secret="another-long-secret-for-casebook-solution-encryption";
  const id=await createCasebookCase({
   guildId:"111111111111111111",authorId:"222222222222222222",title:"The Vanishing Manuscript",
   premise:"A fictional archivist's manuscript disappeared from a locked archive.",
   solution:"The curator moved it to protect a damaged page and forgot to record the transfer.",solutionSecret:secret,
  });
  const first=await addCasebookEvidence({guildId:"111111111111111111",caseId:id,authorId:"222222222222222222",title:"Broken seal",description:"The display seal is intact.",redHerring:true});
  await addCasebookEvidence({guildId:"111111111111111111",caseId:id,authorId:"222222222222222222",title:"Transfer ledger",description:"A signed ledger lists a temporary move."});
  await publishCasebookCase({guildId:"111111111111111111",caseId:id,authorId:"222222222222222222"});
  assert.equal(await getCasebookCase("111111111111111111",id,"333333333333333333"),null);
  const visible=await getCasebookCase("111111111111111111",id,"333333333333333333");
  assert.equal(visible?.evidence.length,1);
  assert.equal(visible?.evidence[0]?.is_red_herring,null);
  await assert.rejects(()=>submitCasebookTheory({
   guildId:"111111111111111111",caseId:id,authorId:"333333333333333333",
   theory:"The curator moved it.",citedEvidenceIds:["999999999999999999"],
  }),/Only evidence unlocked/);
  const clue=await unlockNextCasebookEvidence({guildId:"111111111111111111",caseId:id,authorId:"222222222222222222"});
  assert.equal(clue?.title,"Transfer ledger");
  const theoryId=await submitCasebookTheory({
   guildId:"111111111111111111",caseId:id,authorId:"333333333333333333",
   theory:"The curator moved it temporarily.",citedEvidenceIds:[first],
  });
  assert.ok(theoryId);
  await submitCasebookTheory({
   guildId:"111111111111111111",caseId:id,authorId:"444444444444444444",
   theory:"A fictional guest borrowed it.",citedEvidenceIds:[first],
  });
  assert.equal((await getCasebookCase("111111111111111111",id,"333333333333333333"))?.theories.length,1);
  assert.equal((await getCasebookCase("111111111111111111",id,"222222222222222222"))?.theories.length,2);
  await assert.rejects(()=>revealCasebookSolution({
   guildId:"111111111111111111",caseId:id,actorId:"333333333333333333",solutionSecret:secret,
  }),/Only the case author/);
  await closeCasebookCase({guildId:"111111111111111111",caseId:id,actorId:"222222222222222222"});
  assert.match(await revealCasebookSolution({
   guildId:"111111111111111111",caseId:id,actorId:"222222222222222222",solutionSecret:secret,
  }),/curator moved it/);
  assert.equal(await getCasebookCase("222222222222222222",id,"222222222222222222"),null);
 }finally{await closeDatabase();await rm(directory,{recursive:true,force:true});}
});
