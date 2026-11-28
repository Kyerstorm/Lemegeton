import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  createRelayChain, getRelayChain, joinRelayChain, reviewRelayContribution,
  submitRelayContribution,
} from "../helpers/community/relay.js";

test("Relay rotates turns, advances rejected contributions and remains guild-isolated", async () => {
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-relay-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const chainId=await createRelayChain({
      guildId:"111111111111111111",ownerId:"222222222222222222",
      title:"Shared universe",premise:"Each person adds one paragraph.",contributionLimit:3,reviewMode:"owner",
    });
    await joinRelayChain("111111111111111111",chainId,"333333333333333333");
    await joinRelayChain("111111111111111111",chainId,"444444444444444444");
    await assert.rejects(()=>submitRelayContribution({
      guildId:"222222222222222222",chainId,authorId:"222222222222222222",content:"Wrong server",
    }),/not open/);

    await assert.rejects(()=>submitRelayContribution({
      guildId:"111111111111111111",chainId,authorId:"333333333333333333",content:"Skipping the owner turn",
    }),/It is not your turn/);
    const first=await submitRelayContribution({
      guildId:"111111111111111111",chainId,authorId:"222222222222222222",content:"The first chapter.",
    });
    assert.equal(first.status,"pending");
    await reviewRelayContribution({
      guildId:"111111111111111111",chainId,contributionId:first.id,
      reviewerId:"222222222222222222",approve:true,
    });

    const second=await submitRelayContribution({
      guildId:"111111111111111111",chainId,authorId:"333333333333333333",content:"A new city appeared.",
    });
    await reviewRelayContribution({
      guildId:"111111111111111111",chainId,contributionId:second.id,
      reviewerId:"222222222222222222",approve:true,
    });

    const third=await submitRelayContribution({
      guildId:"111111111111111111",chainId,authorId:"444444444444444444",content:"A disallowed contribution.",
    });
    await reviewRelayContribution({
      guildId:"111111111111111111",chainId,contributionId:third.id,
      reviewerId:"222222222222222222",approve:false,
    });
    const details=await getRelayChain("111111111111111111",chainId);
    assert.equal(details?.chain.current_turn,4);
    assert.equal(details?.chain.status,"completed");
    assert.deepEqual(details?.contributions.map(item=>item.status),["accepted","accepted","rejected"]);
    assert.equal(await getRelayChain("222222222222222222",chainId),null);
  }finally{
    await closeDatabase();
    await rm(directory,{recursive:true,force:true});
  }
});

test("Relay revision requests preserve the previous version and only the author can resubmit", async () => {
  const directory=await mkdtemp(join(tmpdir(),"lemegeton-relay-revision-"));
  await initDatabase({path:join(directory,"bot.db"),primaryGuildId:null});
  try{
    const chainId=await createRelayChain({
      guildId:"111111111111111111",ownerId:"222222222222222222",
      title:"Mystery trail",premise:"Add a clue per turn.",contributionLimit:2,reviewMode:"owner",
    });
    await joinRelayChain("111111111111111111",chainId,"333333333333333333");
    await joinRelayChain("111111111111111111",chainId,"444444444444444444");
    const first=await submitRelayContribution({
      guildId:"111111111111111111",chainId,authorId:"222222222222222222",content:"Opening clue",
    });
    await reviewRelayContribution({
      guildId:"111111111111111111",chainId,contributionId:first.id,
      reviewerId:"222222222222222222",approve:true,
    });
    const pending=await submitRelayContribution({
      guildId:"111111111111111111",chainId,authorId:"333333333333333333",content:"First version",
    });
    await reviewRelayContribution({
      guildId:"111111111111111111",chainId,contributionId:pending.id,
      reviewerId:"222222222222222222",approve:false,requestRevision:true,note:"Clarify the clue",
    });
    await assert.rejects(()=>submitRelayContribution({
      guildId:"111111111111111111",chainId,authorId:"444444444444444444",content:"Attempted overwrite",
    }),/original contributor/);
    const revised=await submitRelayContribution({
      guildId:"111111111111111111",chainId,authorId:"333333333333333333",content:"Revised version",
    });
    assert.equal(revised.id,pending.id);
    assert.equal(revised.turn,2);
    const details=await getRelayChain("111111111111111111",chainId);
    assert.equal(details?.revisions.length,1);
    assert.equal(details?.revisions[0]?.content,"First version");
    assert.equal(details?.revisions[0]?.status,"revision_requested");
    assert.equal(details?.revisions[0]?.review_note,"Clarify the clue");
    assert.equal(details?.next_contributor_id,"333333333333333333");
    await assert.rejects(()=>reviewRelayContribution({
      guildId:"111111111111111111",chainId,contributionId:pending.id,
      reviewerId:"333333333333333333",approve:true,
    }),/Only the chain owner/);
  }finally{
    await closeDatabase();
    await rm(directory,{recursive:true,force:true});
  }
});
