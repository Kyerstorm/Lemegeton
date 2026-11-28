import { createHash, randomBytes } from "node:crypto";
import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { logger } from "../runtime/logger.js";
import { cleanText } from "../security/security.js";

export type CouncilStatus = "review" | "deliberation" | "frozen" | "voting" | "passed" | "failed" | "cancelled";
export type CouncilVotingMethod = "single" | "multiple";
export interface CouncilBallot { option_key: string; option_label: string; position: number; }
export interface CouncilAmendment { id: string; author_id: string; amendment: string; status: "pending" | "accepted" | "rejected"; review_note: string | null; }
export interface CouncilProposal {
  id: string; guild_id: string; owner_id: string; title: string; description: string; status: CouncilStatus;
  voting_method: CouncilVotingMethod; quorum: number; max_choices: number; starts_at: string | null; ends_at: string | null;
  created_at: string; vote_count: number;
}
export interface CouncilDetail {
  proposal: CouncilProposal;
  ballots: CouncilBallot[];
  amendments: CouncilAmendment[];
  tally: Array<{ option_key: string; option_label: string; votes: number }>;
}

function required(value: string, maximum: number, label: string): string {
  const clean = cleanText(value, maximum);
  if (!clean) throw new Error(label + " is required.");
  return clean;
}

function parseOptions(value: readonly string[]): Array<{ key: string; label: string }> {
  const unique = new Map<string,string>();
  for (const raw of value) {
    const label = cleanText(raw, 80);
    if (!label) continue;
    const key = createHash("sha256").update(label.toLocaleLowerCase("en-US")).digest("hex").slice(0,12);
    unique.set(key,label);
  }
  const options = [...unique].map(([key,label])=>({key,label}));
  if (options.length < 2 || options.length > 10) throw new Error("A proposal needs between 2 and 10 distinct ballot options.");
  return options;
}

export async function createCouncilProposal(input: {
  guildId: string; ownerId: string; title: string; description: string; options: readonly string[];
  votingMethod?: CouncilVotingMethod; quorum?: number; maxChoices?: number;
}): Promise<string> {
  const title=required(input.title,180,"Proposal title");
  const description=required(input.description,2_000,"Proposal description");
  const options=parseOptions(input.options);
  const method=input.votingMethod??"single";
  if(!["single","multiple"].includes(method))throw new Error("Choose single-choice or multiple-choice voting.");
  const quorum=input.quorum??0;
  if(!Number.isInteger(quorum)||quorum<0||quorum>10_000)throw new Error("Quorum must be a whole number between 0 and 10000.");
  const maxChoices=input.maxChoices??(method==="single"?1:Math.min(3,options.length));
  if(!Number.isInteger(maxChoices)||maxChoices<1||maxChoices>options.length||(method==="single"&&maxChoices!==1))throw new Error("The maximum choices must match the selected voting method.");
  return transaction(async client=>{
    const created=await client.query<{id:string}>(
      "INSERT INTO council_proposals (guild_id,owner_id,title,description,voting_method,quorum,max_choices) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id::text AS id",
      [input.guildId,input.ownerId,title,description,method,quorum,maxChoices],
    );
    const id=created.rows[0]?.id;
    if(!id)throw new Error("The proposal could not be created.");
    for(let i=0;i<options.length;i++){
      await client.query(
        "INSERT INTO council_ballots (proposal_id,guild_id,option_key,option_label,position) VALUES ($1,$2,$3,$4,$5)",
        [id,input.guildId,options[i]!.key,options[i]!.label,i],
      );
    }
    return id;
  });
}

export async function listCouncilProposals(guildId:string,limit=15):Promise<Array<{id:string;title:string;status:CouncilStatus;vote_count:number}>>{
  return query(
    `SELECT p.id::text,p.title,p.status,
      (SELECT COUNT(*) FROM council_votes v WHERE v.proposal_id=p.id AND v.guild_id=p.guild_id)::INT AS vote_count
     FROM council_proposals p WHERE p.guild_id=$1 AND p.status<>'cancelled'
     ORDER BY p.created_at DESC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}

export async function getCouncilProposal(guildId:string,proposalId:string):Promise<CouncilDetail|null>{
  const proposal=await queryOne<CouncilProposal>(
    `SELECT p.id::text,p.guild_id::text,p.owner_id::text,p.title,p.description,p.status,p.voting_method,p.quorum,p.max_choices,
      p.starts_at,p.ends_at,p.created_at,
      (SELECT COUNT(*) FROM council_votes v WHERE v.proposal_id=p.id AND v.guild_id=p.guild_id)::INT AS vote_count
     FROM council_proposals p WHERE p.id=$1 AND p.guild_id=$2`,
    [proposalId,guildId],
  );
  if(!proposal)return null;
  const [ballots,amendments,votes]=await Promise.all([
    query<CouncilBallot>("SELECT option_key,option_label,position FROM council_ballots WHERE proposal_id=$1 AND guild_id=$2 ORDER BY position",[proposalId,guildId]),
    query<CouncilAmendment>("SELECT id::text,author_id::text,amendment,status,review_note FROM council_amendments WHERE proposal_id=$1 AND guild_id=$2 ORDER BY created_at ASC LIMIT 25",[proposalId,guildId]),
    proposal.status==="passed"||proposal.status==="failed"
      ? query<{ballot_value:string}>("SELECT ballot_value FROM council_votes WHERE proposal_id=$1 AND guild_id=$2",[proposalId,guildId])
      : Promise.resolve([] as Array<{ballot_value:string}>),
  ]);
  const tally=new Map(ballots.map(option=>[option.option_key,{option_key:option.option_key,option_label:option.option_label,votes:0}]));
  for(const vote of votes){
    let selected:string[]=[];
    try{const parsed=JSON.parse(vote.ballot_value) as unknown;if(Array.isArray(parsed))selected=parsed.filter((v):v is string=>typeof v==="string");}catch{continue;}
    for(const key of selected){const current=tally.get(key);if(current)current.votes++;}
  }
  return {proposal,ballots,amendments,tally:[...tally.values()]};
}

export async function submitCouncilAmendment(input:{
  guildId:string;proposalId:string;authorId:string;amendment:string;
}):Promise<string>{
  const text=required(input.amendment,1_000,"Amendment");
  const row=await queryOne<{id:string}>(
    `INSERT INTO council_amendments (proposal_id,guild_id,author_id,amendment)
     SELECT id,guild_id,$3,$4 FROM council_proposals WHERE id=$1 AND guild_id=$2 AND status='deliberation'
     RETURNING id::text AS id`,
    [input.proposalId,input.guildId,input.authorId,text],
  );
  if(!row)throw new Error("Amendments can only be submitted during deliberation.");
  return row.id;
}

export async function reviewCouncilAmendment(input:{
  guildId:string;proposalId:string;amendmentId:string;reviewerId:string;accept:boolean;note?:string;
}):Promise<void>{
  await transaction(async client=>{
    const result=await client.query(
      `SELECT p.owner_id::text,p.description,a.amendment,a.status
       FROM council_proposals p JOIN council_amendments a ON a.proposal_id=p.id
       WHERE p.id=$1 AND p.guild_id=$2 AND a.id=$3 AND a.guild_id=$2 FOR UPDATE`,
      [input.proposalId,input.guildId,input.amendmentId],
    );
    const row=result.rows[0] as {owner_id:string;description:string;amendment:string;status:string}|undefined;
    if(!row||row.status!=="pending")throw new Error("That pending amendment was not found.");
    if(row.owner_id!==input.reviewerId)throw new Error("Only the proposal owner can review amendments.");
    if(input.accept){
      const combined=cleanText(row.description+"\n\nAccepted amendment: "+row.amendment,2_000);
      await client.query("UPDATE council_proposals SET description=$1 WHERE id=$2 AND guild_id=$3",[combined,input.proposalId,input.guildId]);
    }
    await client.query(
      "UPDATE council_amendments SET status=$1,reviewed_by=$2,review_note=$3 WHERE id=$4 AND proposal_id=$5 AND guild_id=$6",
      [input.accept?"accepted":"rejected",input.reviewerId,cleanText(input.note,500)||null,input.amendmentId,input.proposalId,input.guildId],
    );
  });
}

export async function advanceCouncilProposal(input:{
  guildId:string;proposalId:string;ownerId:string;action:"deliberation"|"freeze"|"start-voting"|"cancel";
  durationMinutes?:number;
}):Promise<void>{
  await transaction(async client=>{
    const result=await client.query(
      "SELECT owner_id::text,status FROM council_proposals WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [input.proposalId,input.guildId],
    );
    const proposal=result.rows[0] as {owner_id:string;status:string}|undefined;
    if(!proposal||proposal.owner_id!==input.ownerId)throw new Error("Only the proposal owner can change its phase.");
    const transitions:Record<string,string>={review:"deliberation",deliberation:"frozen",frozen:"start-voting"};
    if(input.action==="cancel"){
      if(!["review","deliberation","frozen","voting"].includes(proposal.status))throw new Error("This proposal cannot be cancelled.");
      await client.query("UPDATE council_proposals SET status='cancelled',closed_at=CURRENT_TIMESTAMP WHERE id=$1 AND guild_id=$2",[input.proposalId,input.guildId]);
      return;
    }
    const next=transitions[proposal.status];
    if(next!==input.action)throw new Error("The proposal cannot move to that phase from its current status.");
    if(input.action==="start-voting"){
      const duration=input.durationMinutes??1_440;
      if(!Number.isInteger(duration)||duration<1||duration>10_080)throw new Error("Voting duration must be between 1 minute and 7 days.");
      await client.query(
        "UPDATE council_proposals SET status='voting',starts_at=CURRENT_TIMESTAMP,ends_at=datetime('now', '+' || $1 || ' minutes') WHERE id=$2 AND guild_id=$3",
        [duration,input.proposalId,input.guildId],
      );
    }else{
      await client.query(
        "UPDATE council_proposals SET status=$1,frozen_at=CASE WHEN $1='frozen' THEN CURRENT_TIMESTAMP ELSE frozen_at END WHERE id=$2 AND guild_id=$3",
        [next,input.proposalId,input.guildId],
      );
    }
  });
}

export async function submitCouncilVote(input:{
  guildId:string;proposalId:string;voterId:string;choices:readonly string[];
}):Promise<string>{
  return transaction(async client=>{
    const result=await client.query(
      "SELECT status,voting_method,max_choices,ends_at FROM council_proposals WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [input.proposalId,input.guildId],
    );
    const proposal=result.rows[0] as {status:string;voting_method:CouncilVotingMethod;max_choices:number;ends_at:string|null}|undefined;
    if(!proposal||proposal.status!=="voting")throw new Error("This proposal is not accepting votes.");
    if(proposal.ends_at&&new Date(proposal.ends_at).getTime()<=Date.now())throw new Error("The voting period has ended.");
    const choices=[...new Set(input.choices)];
    if(!choices.length||choices.length>proposal.max_choices||(proposal.voting_method==="single"&&choices.length!==1))throw new Error("Choose a valid number of ballot options.");
    const known=await client.query("SELECT option_key FROM council_ballots WHERE proposal_id=$1 AND guild_id=$2",[input.proposalId,input.guildId]);
    const keys=new Set(known.rows.map(row=>(row as {option_key:string}).option_key));
    if(choices.some(choice=>!keys.has(choice)))throw new Error("One or more selected ballot options are invalid.");
    const receipt=randomBytes(16).toString("hex");
    const receiptHash=createHash("sha256").update(input.proposalId+":"+input.voterId+":"+receipt).digest("hex");
    const inserted=await client.query<{proposal_id:string}>(
      "INSERT INTO council_votes (proposal_id,guild_id,voter_id,ballot_value,receipt_hash) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (proposal_id,voter_id) DO NOTHING RETURNING proposal_id::text",
      [input.proposalId,input.guildId,input.voterId,JSON.stringify(choices),receiptHash],
    );
    if(!inserted.rows[0])throw new Error("A ballot has already been recorded for your account.");
    return receipt;
  });
}

export async function verifyCouncilReceipt(input:{
  guildId:string;proposalId:string;voterId:string;receipt:string;
}):Promise<boolean>{
  if(!/^[a-f0-9]{32}$/i.test(input.receipt))return false;
  const receiptHash=createHash("sha256").update(input.proposalId+":"+input.voterId+":"+input.receipt).digest("hex");
  const row=await queryOne<{receipt_hash:string}>(
    "SELECT receipt_hash FROM council_votes WHERE proposal_id=$1 AND guild_id=$2 AND voter_id=$3",
    [input.proposalId,input.guildId,input.voterId],
  );
  return Boolean(row&&row.receipt_hash===receiptHash);
}
export async function closeCouncilVoting(input:{
  guildId:string;proposalId:string;actorId:string;canModerate?:boolean;
}):Promise<{status:"passed"|"failed";votes:number;quorum:number;tally:Array<{option_key:string;option_label:string;votes:number}>}>{
  return transaction(async client=>{
    const result=await client.query(
      `SELECT p.owner_id::text,p.status,p.quorum,p.ends_at
       FROM council_proposals p WHERE p.id=$1 AND p.guild_id=$2 FOR UPDATE`,
      [input.proposalId,input.guildId],
    );
    const row=result.rows[0] as {owner_id:string;status:string;quorum:number;ends_at:string|null}|undefined;
    if(!row||row.status!=="voting")throw new Error("This proposal is not in its voting phase.");
    if(row.owner_id!==input.actorId&&!input.canModerate)throw new Error("Only the owner or a moderator can close voting.");
    if(row.ends_at&&new Date(row.ends_at).getTime()>Date.now())throw new Error("The voting period has not ended yet.");
    const ballots=await client.query("SELECT option_key,option_label FROM council_ballots WHERE proposal_id=$1 AND guild_id=$2",[input.proposalId,input.guildId]);
    const votes=await client.query("SELECT ballot_value FROM council_votes WHERE proposal_id=$1 AND guild_id=$2",[input.proposalId,input.guildId]);
    const tally=new Map((ballots.rows as Array<{option_key:string;option_label:string}>).map(option=>[option.option_key,{...option,votes:0}]));
    for(const vote of votes.rows as Array<{ballot_value:string}>){
      try{
        const selected=JSON.parse(vote.ballot_value) as unknown;
        if(Array.isArray(selected))for(const key of selected){if(typeof key==="string"&&tally.has(key))tally.get(key)!.votes++;}
      }catch{/* Ignore malformed legacy ballot values. */}
    }
    const values=[...tally.values()];
    const high=Math.max(0,...values.map(item=>item.votes));
    const leaders=values.filter(item=>item.votes===high&&high>0);
    const passed=votes.rows.length>=row.quorum&&leaders.length===1;
    const status=passed?"passed":"failed";
    await client.query("UPDATE council_proposals SET status=$1,closed_at=CURRENT_TIMESTAMP WHERE id=$2 AND guild_id=$3",[status,input.proposalId,input.guildId]);
    return {status,votes:votes.rows.length,quorum:row.quorum,tally:values};
  });
}


let councilWorkerTimer: NodeJS.Timeout | undefined;
let councilWorkerRunning = false;
let councilWorkerPromise: Promise<void> | undefined;

export async function closeExpiredCouncilProposals(): Promise<number> {
  const expired = await query<{ id: string; guild_id: string; owner_id: string }>(
    "SELECT id::text,guild_id::text,owner_id::text FROM council_proposals WHERE status='voting' AND ends_at IS NOT NULL AND datetime(ends_at)<=datetime('now') ORDER BY ends_at ASC LIMIT 50",
  );
  let closed = 0;
  for (const proposal of expired) {
    try {
      await closeCouncilVoting({
        guildId: proposal.guild_id,
        proposalId: proposal.id,
        actorId: proposal.owner_id,
      });
      closed += 1;
    } catch (error) {
      logger.warn("Expired Council proposal could not be finalized", {
        guildId: proposal.guild_id,
        proposalId: proposal.id,
        reason: error instanceof Error ? error.message : "Unknown voting finalization error",
      });
    }
  }
  return closed;
}

async function runCouncilVotingWorker(): Promise<void> {
  if (councilWorkerRunning) return;
  councilWorkerRunning = true;
  try {
    await closeExpiredCouncilProposals();
  } catch (error) {
    logger.error("Council voting worker failed", {
      reason: error instanceof Error ? error.message : "Unknown Council worker error",
    });
  } finally {
    councilWorkerRunning = false;
  }
}

export function startCouncilVotingWorker(): void {
  if (councilWorkerTimer) return;
  councilWorkerPromise = runCouncilVotingWorker();
  councilWorkerTimer = setInterval(() => {
    councilWorkerPromise = runCouncilVotingWorker();
    void councilWorkerPromise;
  }, 60_000);
  councilWorkerTimer.unref();
}

export async function stopCouncilVotingWorker(): Promise<void> {
  if (councilWorkerTimer) clearInterval(councilWorkerTimer);
  councilWorkerTimer = undefined;
  await councilWorkerPromise?.catch(() => undefined);
}
