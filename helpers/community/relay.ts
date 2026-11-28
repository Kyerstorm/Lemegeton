import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { cleanText } from "../security/security.js";

export interface RelayChain {
  id: string;
  guild_id: string;
  owner_id: string;
  title: string;
  premise: string;
  contribution_limit: number;
  review_mode: "owner" | "automatic";
  status: "draft" | "open" | "paused" | "completed" | "cancelled";
  current_turn: number;
  created_at: string;
}
export interface RelayContribution {
  id: string;
  turn_number: number;
  author_id: string;
  parent_contribution_id: string | null;
  content: string;
  status: "pending" | "accepted" | "rejected" | "revision_requested";
  created_at: string;
  review_note: string | null;
}
export interface RelayContributionRevision {
  id: string;
  contribution_id: string;
  revision_number: number;
  author_id: string;
  content: string;
  status: "revision_requested";
  created_at: string;
  review_note: string | null;
}

export interface RelayDetails {
  chain: RelayChain;
  members: Array<{ user_id: string; joined_at: string }>;
  contributions: RelayContribution[];
  revisions: RelayContributionRevision[];
  next_contributor_id: string;
}

export async function createRelayChain(input: {
  guildId: string; ownerId: string; title: string; premise: string; contributionLimit?: number; reviewMode?: "owner" | "automatic";
}): Promise<string> {
  const title=cleanText(input.title,180);
  const premise=cleanText(input.premise,1_000);
  const limit=input.contributionLimit??20;
  if(!title||!premise)throw new Error("Provide a chain title and premise.");
  if(!Number.isInteger(limit)||limit<2||limit>100)throw new Error("Contribution limit must be between 2 and 100.");
  const mode=input.reviewMode??"owner";
  if(!["owner","automatic"].includes(mode))throw new Error("Choose owner review or automatic acceptance.");
  return transaction(async client=>{
    const created=await client.query<{id:string}>(
      `INSERT INTO relay_chains (guild_id,owner_id,title,premise,contribution_limit,review_mode,status)
       VALUES ($1,$2,$3,$4,$5,$6,'open') RETURNING id::text AS id`,
      [input.guildId,input.ownerId,title,premise,limit,mode],
    );
    const id=created.rows[0]?.id;
    if(!id)throw new Error("The Relay chain could not be created.");
    await client.query("INSERT INTO relay_members (chain_id,guild_id,user_id) VALUES ($1,$2,$3)",[id,input.guildId,input.ownerId]);
    return id;
  });
}

export async function listRelayChains(guildId:string,limit=15):Promise<Array<{id:string;title:string;current_turn:number;contribution_limit:number;members:number}>> {
  return query(
    `SELECT c.id::text AS id,c.title,c.current_turn,c.contribution_limit,
      (SELECT COUNT(*) FROM relay_members m WHERE m.chain_id=c.id)::INT AS members
     FROM relay_chains c WHERE c.guild_id=$1 AND c.status IN ('open','paused')
     ORDER BY c.created_at DESC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}

export async function getRelayChain(guildId:string,chainId:string):Promise<RelayDetails|null>{
  const chain=await queryOne<RelayChain>(
    `SELECT id::text,guild_id::text,owner_id::text,title,premise,contribution_limit,review_mode,status,current_turn,created_at
     FROM relay_chains WHERE id=$1 AND guild_id=$2`,
    [chainId,guildId],
  );
  if(!chain)return null;
  const [members,contributions,revisions]=await Promise.all([
    query<{ user_id: string; joined_at: string }>("SELECT user_id::text,joined_at FROM relay_members WHERE chain_id=$1 AND guild_id=$2 ORDER BY rowid ASC LIMIT 100",[chainId,guildId]),
    query<RelayContribution>(
      "SELECT id::text,turn_number,author_id::text,parent_contribution_id::text,content,status,created_at,review_note FROM relay_contributions WHERE chain_id=$1 AND guild_id=$2 ORDER BY turn_number ASC LIMIT 100",
      [chainId,guildId],
    ),
    query<RelayContributionRevision>(
      "SELECT id::text,contribution_id::text,revision_number,author_id::text,content,status,created_at,review_note FROM relay_contribution_revisions WHERE chain_id=$1 AND guild_id=$2 ORDER BY contribution_id,revision_number ASC LIMIT 300",
      [chainId,guildId],
    ),
  ]);
  const previous = [...contributions].reverse().find(item => item.turn_number < chain.current_turn);
  const previousIndex = previous ? members.findIndex(member => member.user_id === previous.author_id) : -1;
  const nextContributor = previousIndex < 0
    ? chain.owner_id
    : members[(previousIndex + 1) % members.length]?.user_id ?? chain.owner_id;
  return {chain,members,contributions,revisions,next_contributor_id:nextContributor};
}

export async function joinRelayChain(guildId:string,chainId:string,userId:string):Promise<boolean>{
  const row=await queryOne<{id:string}>(
    `INSERT INTO relay_members (chain_id,guild_id,user_id)
     SELECT id,$2,$3 FROM relay_chains WHERE id=$1 AND guild_id=$2 AND status='open'
     ON CONFLICT (chain_id,user_id) DO NOTHING RETURNING user_id::text AS id`,
    [chainId,guildId,userId],
  );
  return Boolean(row);
}

export async function submitRelayContribution(input:{
  guildId:string;chainId:string;authorId:string;content:string;
}):Promise<{id:string;status:"pending"|"accepted";turn:number}>{
  const content=cleanText(input.content,1_500);
  if(!content)throw new Error("Write a contribution before submitting.");
  return transaction(async client=>{
    const result=await client.query(
      `SELECT id::text,owner_id::text,current_turn,contribution_limit,review_mode,status
       FROM relay_chains WHERE id=$1 AND guild_id=$2 FOR UPDATE`,
      [input.chainId,input.guildId],
    );
    const chain=result.rows[0] as {
      owner_id:string;current_turn:number;contribution_limit:number;review_mode:"owner"|"automatic";status:string;
    }|undefined;
    if(!chain||chain.status!=="open")throw new Error("That Relay chain is not open.");
    const member=await client.query("SELECT user_id FROM relay_members WHERE chain_id=$1 AND guild_id=$2 AND user_id=$3",[input.chainId,input.guildId,input.authorId]);
    if(!member.rowCount)throw new Error("Join the chain before contributing.");
    if(chain.current_turn>chain.contribution_limit)throw new Error("This chain has reached its contribution limit.");
    const prior=await client.query(
      "SELECT id::text,status,author_id::text FROM relay_contributions WHERE chain_id=$1 AND guild_id=$2 AND turn_number=$3",
      [input.chainId,input.guildId,chain.current_turn],
    );
    const existing=prior.rows[0] as {id:string;status:string;author_id:string}|undefined;
    if(existing&&existing.status!=="revision_requested")throw new Error("This turn already has a contribution awaiting review or acceptance.");
    const members=await client.query(
      "SELECT user_id::text FROM relay_members WHERE chain_id=$1 AND guild_id=$2 ORDER BY rowid ASC",
      [input.chainId,input.guildId],
    );
    const memberIds=members.rows.map(row=>(row as {user_id:string}).user_id);
    const previous=await client.query(
      "SELECT author_id::text FROM relay_contributions WHERE chain_id=$1 AND guild_id=$2 AND turn_number<$3 ORDER BY turn_number DESC LIMIT 1",
      [input.chainId,input.guildId,chain.current_turn],
    );
    const previousAuthor=(previous.rows[0] as {author_id:string}|undefined)?.author_id;
    const previousIndex=previousAuthor ? memberIds.indexOf(previousAuthor) : -1;
    const expectedAuthor=existing?.status==="revision_requested"
      ? existing.author_id
      : previousIndex<0 ? chain.owner_id : memberIds[(previousIndex+1)%memberIds.length];
    if(existing&&existing.author_id!==input.authorId)throw new Error("Only the original contributor can revise this turn.");
    if(expectedAuthor!==input.authorId)throw new Error("It is not your turn. The next contributor is <@"+expectedAuthor+">.");
    const parent=await client.query(
      "SELECT id::text FROM relay_contributions WHERE chain_id=$1 AND guild_id=$2 AND status='accepted' ORDER BY turn_number DESC LIMIT 1",
      [input.chainId,input.guildId],
    );
    const parentId=(parent.rows[0] as {id:string}|undefined)?.id??null;
    const auto=chain.review_mode==="automatic";
    let id:string;
    if(existing){
      const revisionCount=await client.query(
        "SELECT COUNT(*) AS count FROM relay_contribution_revisions WHERE contribution_id=$1 AND guild_id=$2",
        [existing.id,input.guildId],
      );
      const revisionNumber=Number((revisionCount.rows[0] as {count:number|string}|undefined)?.count??0)+1;
      await client.query(
        "INSERT INTO relay_contribution_revisions (contribution_id,chain_id,guild_id,revision_number,author_id,content,status,review_note) SELECT id,chain_id,guild_id,$1,author_id,content,status,review_note FROM relay_contributions WHERE id=$2 AND chain_id=$3 AND guild_id=$4",
        [revisionNumber,existing.id,input.chainId,input.guildId],
      );
      await client.query(
        `UPDATE relay_contributions SET content=$1,status=$2,created_at=CURRENT_TIMESTAMP,reviewed_by=NULL,review_note=NULL
         WHERE id=$3 AND chain_id=$4 AND guild_id=$5`,
        [content,auto?"accepted":"pending",existing.id,input.chainId,input.guildId],
      );
      id=existing.id;
    }else{
      const inserted=await client.query<{id:string}>(
        `INSERT INTO relay_contributions (chain_id,guild_id,turn_number,author_id,parent_contribution_id,content,status)
         VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id::text AS id`,
        [input.chainId,input.guildId,chain.current_turn,input.authorId,parentId,content,auto?"accepted":"pending"],
      );
      id=inserted.rows[0]?.id??"";
    }
    if(!id)throw new Error("The contribution could not be saved.");
    if(auto){
      const next=chain.current_turn+1;
      await client.query(
        "UPDATE relay_chains SET current_turn=$1,status=$2,updated_at=CURRENT_TIMESTAMP WHERE id=$3 AND guild_id=$4",
        [next,next>chain.contribution_limit?"completed":"open",input.chainId,input.guildId],
      );
    }
    return {id,status:auto?"accepted":"pending",turn:chain.current_turn};
  });
}

export async function reviewRelayContribution(input:{
  guildId:string;chainId:string;contributionId:string;reviewerId:string;approve:boolean;requestRevision?:boolean;note?:string;
}):Promise<void>{
  await transaction(async client=>{
    const result=await client.query(
      `SELECT c.id::text,c.turn_number,c.status,r.owner_id::text,r.current_turn,r.contribution_limit
       FROM relay_contributions c JOIN relay_chains r ON r.id=c.chain_id
       WHERE c.id=$1 AND c.chain_id=$2 AND c.guild_id=$3 FOR UPDATE`,
      [input.contributionId,input.chainId,input.guildId],
    );
    const row=result.rows[0] as {turn_number:number;status:string;owner_id:string;current_turn:number;contribution_limit:number}|undefined;
    if(!row||row.status!=="pending")throw new Error("That pending contribution was not found.");
    if(row.owner_id!==input.reviewerId)throw new Error("Only the chain owner can review contributions.");
    const status=input.approve?"accepted":input.requestRevision?"revision_requested":"rejected";
    await client.query(
      "UPDATE relay_contributions SET status=$1,reviewed_by=$2,review_note=$3 WHERE id=$4 AND chain_id=$5 AND guild_id=$6",
      [status,input.reviewerId,cleanText(input.note,500)||null,input.contributionId,input.chainId,input.guildId],
    );
    if(input.approve||!input.requestRevision){
      const next=row.current_turn+1;
      await client.query(
        "UPDATE relay_chains SET current_turn=$1,status=$2,updated_at=CURRENT_TIMESTAMP WHERE id=$3 AND guild_id=$4",
        [next,next>row.contribution_limit?"completed":"open",input.chainId,input.guildId],
      );
    }
  });
}

export async function setRelayChainStatus(input:{
  guildId:string;chainId:string;actorId:string;status:"paused"|"open"|"cancelled";
}):Promise<void>{
  const row=await queryOne<{owner_id:string;status:string}>(
    "SELECT owner_id::text,status FROM relay_chains WHERE id=$1 AND guild_id=$2",
    [input.chainId,input.guildId],
  );
  if(!row||row.owner_id!==input.actorId)throw new Error("Only the chain owner can change its status.");
  if(input.status==="open"&&!["paused","open"].includes(row.status))throw new Error("A completed or cancelled chain cannot be reopened.");
  if(input.status==="paused"&&row.status!=="open")throw new Error("Only an open chain can be paused.");
  if(input.status==="cancelled"&&!["open","paused","draft"].includes(row.status))throw new Error("That chain cannot be cancelled.");
  await query("UPDATE relay_chains SET status=$1,updated_at=CURRENT_TIMESTAMP WHERE id=$2 AND guild_id=$3",[input.status,input.chainId,input.guildId]);
}
