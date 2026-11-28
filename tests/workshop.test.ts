import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  createWorkshopProject, createWorkshopSection, getWorkshopProject,
  reviewWorkshopRevision, submitWorkshopRevision,
} from "../helpers/community/workshop.js";

test("Workshop persists sections, revisions and owner-only review by guild",async()=>{
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-workshop-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const projectId=await createWorkshopProject({
      guildId:"111111111111111111",ownerId:"222222222222222222",
      title:"Community guide",description:"Build a shared guide in reviewed sections.",
    });
    const sectionId=await createWorkshopSection({
      guildId:"111111111111111111",projectId,ownerId:"222222222222222222",
      title:"Introduction",description:"Opening section",assignedTo:"333333333333333333",
    });
    const revisionId=await submitWorkshopRevision({
      guildId:"111111111111111111",projectId,sectionId,
      authorId:"333333333333333333",content:"First version of the introduction.",
    });
    await assert.rejects(()=>submitWorkshopRevision({
      guildId:"111111111111111111",projectId,sectionId,
      authorId:"333333333333333333",content:"A second pending version.",
    }),/already awaiting review/);
    await assert.rejects(()=>submitWorkshopRevision({
      guildId:"111111111111111111",projectId,sectionId,
      authorId:"444444444444444444",content:"Unauthorized revision.",
    }),/assigned to another/);
    await assert.rejects(()=>reviewWorkshopRevision({
      guildId:"111111111111111111",projectId,sectionId,revisionId,
      reviewerId:"333333333333333333",approve:true,
    }),/Only the project owner/);
    await reviewWorkshopRevision({
      guildId:"111111111111111111",projectId,sectionId,revisionId,
      reviewerId:"222222222222222222",approve:true,
    });
    const loaded=await getWorkshopProject("111111111111111111",projectId);
    assert.equal(loaded?.sections[0]?.status,"approved");
    assert.equal(loaded?.revisions[0]?.status,"approved");
    assert.equal(await getWorkshopProject("222222222222222222",projectId),null);
  }finally{
    await closeDatabase();
    await rm(directory,{recursive:true,force:true});
  }
});
