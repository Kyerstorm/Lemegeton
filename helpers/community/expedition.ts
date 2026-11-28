import { createHmac, timingSafeEqual } from "node:crypto";
import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { cleanText } from "../security/security.js";

export interface Expedition {
  id:string;guild_id:string;owner_id:string;title:string;description:string;
  status:"draft"|"open"|"paused"|"completed"|"cancelled";participant_limit:number;created_at:string;
}
export interface ExpeditionStage {
  id:string;position:number;title:string;prompt:string;hint:string|null;
}
export interface ExpeditionDetails {
  expedition:Expedition;stages:ExpeditionStage[];
  participants:Array<{user_id:string;current_stage:number;status:"active"|"completed"|"withdrawn"}>;
  viewerProgress:{current_stage:number;status:"active"|"completed"|"withdrawn"}|null;
}
function required(value:string,maximum:number,label:string):string{
  const result=cleanText(value,maximum);if(!result)throw new Error(label+" is required.");return result;
}
function normalizeAnswer(value:string):string{
  return value.normalize("NFKC").trim().replace(/\s+/g," ").toLocaleLowerCase("en-US");
}
function answerDigest(secret:string,expeditionId:string,position:number,answer:string):Buffer{
  if(secret.length<32)throw new Error("The expedition answer secret must be at least 32 characters.");
  return createHmac("sha256",secret).update(expeditionId+":"+position+":"+normalizeAnswer(answer)).digest();
}
export async function createExpedition(input:{
  guildId:string;ownerId:string;title:string;description:string;participantLimit?:number;
}):Promise<string>{
  const title=required(input.title,180,"Expedition title"),description=required(input.description,1_000,"Expedition description");
  const limit=input.participantLimit??20;
  if(!Number.isInteger(limit)||limit<2||limit>200)throw new Error("Participant limit must be between 2 and 200.");
  const row=await queryOne<{id:string}>(
    "INSERT INTO expeditions (guild_id,owner_id,title,description,participant_limit,status) VALUES ($1,$2,$3,$4,$5,'draft') RETURNING id::text AS id",
    [input.guildId,input.ownerId,title,description,limit],
  );
  if(!row)throw new Error("The expedition could not be created.");return row.id;
}
export async function listExpeditions(guildId:string,viewerId:string,limit=15):Promise<Array<{id:string;title:string;status:string;stage_count:number;participant_count:number}>>{
  return query(
    `SELECT e.id::text,e.title,e.status,
      (SELECT COUNT(*) FROM expedition_stages s WHERE s.expedition_id=e.id)::INT AS stage_count,
      (SELECT COUNT(*) FROM expedition_participants p WHERE p.expedition_id=e.id AND p.status<>'withdrawn')::INT AS participant_count
     FROM expeditions e WHERE e.guild_id=$1 AND (e.status IN ('open','paused') OR (e.status='draft' AND e.owner_id=$2))
     ORDER BY e.created_at DESC LIMIT $3`,
    [guildId,viewerId,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}
export async function getExpedition(guildId:string,expeditionId:string,viewerId?:string):Promise<ExpeditionDetails|null>{
  const expedition=await queryOne<Expedition>(
    "SELECT id::text,guild_id::text,owner_id::text,title,description,status,participant_limit,created_at FROM expeditions WHERE id=$1 AND guild_id=$2",
    [expeditionId,guildId],
  );
  if(!expedition||(expedition.status==="draft"&&viewerId!==expedition.owner_id))return null;
  const [stages,participants,viewerProgress]=await Promise.all([
    query<ExpeditionStage>(
      "SELECT id::text,position,title,prompt,hint FROM expedition_stages WHERE expedition_id=$1 AND guild_id=$2 ORDER BY position ASC LIMIT 50",
      [expeditionId,guildId],
    ),
    query<{user_id:string;current_stage:number;status:"active"|"completed"|"withdrawn"}>(
      "SELECT user_id::text,current_stage,status FROM expedition_participants WHERE expedition_id=$1 AND guild_id=$2 ORDER BY joined_at ASC LIMIT 200",
      [expeditionId,guildId],
    ),
    viewerId?queryOne<{current_stage:number;status:"active"|"completed"|"withdrawn"}>(
      "SELECT current_stage,status FROM expedition_participants WHERE expedition_id=$1 AND guild_id=$2 AND user_id=$3",
      [expeditionId,guildId,viewerId],
    ):Promise.resolve(null),
  ]);
  const visibleStages=viewerId===expedition.owner_id?stages:stages.filter(stage=>viewerProgress&&stage.position<=viewerProgress.current_stage);
  return {expedition,stages:visibleStages,participants,viewerProgress};
}
export async function addExpeditionStage(input:{
  guildId:string;expeditionId:string;ownerId:string;title:string;prompt:string;answer:string;hint?:string;answerSecret:string;
}):Promise<string>{
  const title=required(input.title,180,"Stage title"),prompt=required(input.prompt,1_000,"Stage prompt");
  const answer=required(input.answer,180,"Stage answer");
  const hint=cleanText(input.hint,300)||null;
  return transaction(async client=>{
    const project=await client.query(
      "SELECT owner_id::text,status FROM expeditions WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [input.expeditionId,input.guildId],
    );
    const row=project.rows[0] as {owner_id:string;status:string}|undefined;
    if(!row||row.owner_id!==input.ownerId)throw new Error("Only the expedition owner can add stages.");
    if(row.status!=="draft")throw new Error("Stages can only be added before the expedition is published.");
    const positionResult=await client.query(
      "SELECT COALESCE(MAX(position),0)+1 AS next_position FROM expedition_stages WHERE expedition_id=$1 AND guild_id=$2",
      [input.expeditionId,input.guildId],
    );
    const position=Number((positionResult.rows[0] as {next_position:number}|undefined)?.next_position??1);
    const digest=answerDigest(input.answerSecret,input.expeditionId,position,answer).toString("hex");
    const inserted=await client.query<{id:string}>(
      "INSERT INTO expedition_stages (expedition_id,guild_id,position,title,prompt,answer_hash,hint) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id::text AS id",
      [input.expeditionId,input.guildId,position,title,prompt,digest,hint],
    );
    const id=inserted.rows[0]?.id;if(!id)throw new Error("The expedition stage could not be saved.");return id;
  });
}
export async function publishExpedition(input:{guildId:string;expeditionId:string;ownerId:string}):Promise<void>{
  await transaction(async client=>{
    const result=await client.query(
      "SELECT owner_id::text,status FROM expeditions WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [input.expeditionId,input.guildId],
    );
    const row=result.rows[0] as {owner_id:string;status:string}|undefined;
    if(!row||row.owner_id!==input.ownerId)throw new Error("Only the expedition owner can publish it.");
    if(row.status!=="draft")throw new Error("This expedition is no longer a draft.");
    const count=await client.query(
      "SELECT COUNT(*)::INT AS count FROM expedition_stages WHERE expedition_id=$1 AND guild_id=$2",
      [input.expeditionId,input.guildId],
    );
    const stageCount=Number((count.rows[0] as {count:number}|undefined)?.count??0);
    if(stageCount<1)throw new Error("Add at least one stage before publishing.");
    await client.query("UPDATE expeditions SET status='open',updated_at=CURRENT_TIMESTAMP WHERE id=$1 AND guild_id=$2",[input.expeditionId,input.guildId]);
  });
}
export async function joinExpedition(guildId:string,expeditionId:string,userId:string):Promise<boolean>{
  return transaction(async client=>{
    const result=await client.query(
      "SELECT status,participant_limit FROM expeditions WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [expeditionId,guildId],
    );
    const expedition=result.rows[0] as {status:string;participant_limit:number}|undefined;
    if(!expedition||expedition.status!=="open")return false;
    const count=await client.query(
      "SELECT COUNT(*)::INT AS count FROM expedition_participants WHERE expedition_id=$1 AND guild_id=$2 AND status<>'withdrawn'",
      [expeditionId,guildId],
    );
    const participantCount=Number((count.rows[0] as {count:number}|undefined)?.count??0);
    if(participantCount>=expedition.participant_limit)return false;
    const inserted=await client.query<{user_id:string}>(
      "INSERT INTO expedition_participants (expedition_id,guild_id,user_id) VALUES ($1,$2,$3) ON CONFLICT (expedition_id,user_id) DO NOTHING RETURNING user_id::text",
      [expeditionId,guildId,userId],
    );
    return Boolean(inserted.rows[0]);
  });
}
export async function submitExpeditionAnswer(input:{
  guildId:string;expeditionId:string;userId:string;answer:string;answerSecret:string;
}):Promise<{correct:boolean;completed:boolean;nextStage:number}>{
  const answer=required(input.answer,180,"Answer");
  return transaction(async client=>{
    const result=await client.query(
      `SELECT e.status,p.current_stage,p.status AS participant_status
       FROM expeditions e JOIN expedition_participants p ON p.expedition_id=e.id
       WHERE e.id=$1 AND e.guild_id=$2 AND p.guild_id=$2 AND p.user_id=$3 FOR UPDATE`,
      [input.expeditionId,input.guildId,input.userId],
    );
    const row=result.rows[0] as {status:string;current_stage:number;participant_status:string}|undefined;
    if(!row||row.status!=="open"||row.participant_status!=="active")throw new Error("Join an open expedition before submitting an answer.");
    const stageResult=await client.query(
      "SELECT id::text,position,answer_hash FROM expedition_stages WHERE expedition_id=$1 AND guild_id=$2 AND position=$3",
      [input.expeditionId,input.guildId,row.current_stage],
    );
    const stage=stageResult.rows[0] as {id:string;position:number;answer_hash:string}|undefined;
    if(!stage)throw new Error("The current stage is unavailable.");
    const attempts=await client.query(
      "SELECT COUNT(*)::INT AS count FROM expedition_submissions WHERE expedition_id=$1 AND stage_id=$2 AND guild_id=$3 AND user_id=$4 AND created_at>=datetime('now','-1 minute')",
      [input.expeditionId,stage.id,input.guildId,input.userId],
    );
    const attemptCount=Number((attempts.rows[0] as {count:number}|undefined)?.count??0);
    if(attemptCount>=5)throw new Error("Answer attempt limit reached. Try again after one minute.");
    const submitted=answerDigest(input.answerSecret,input.expeditionId,stage.position,answer);
    const expected=Buffer.from(stage.answer_hash,"hex");
    const correct=expected.length===submitted.length&&timingSafeEqual(expected,submitted);
    await client.query(
      "INSERT INTO expedition_submissions (expedition_id,stage_id,guild_id,user_id,answer_hash,correct) VALUES ($1,$2,$3,$4,$5,$6)",
      [input.expeditionId,stage.id,input.guildId,input.userId,submitted.toString("hex"),correct?1:0],
    );
    if(!correct)return {correct:false,completed:false,nextStage:row.current_stage};
    const next=row.current_stage+1;
    const final=await client.query("SELECT id FROM expedition_stages WHERE expedition_id=$1 AND guild_id=$2 AND position=$3",[input.expeditionId,input.guildId,next]);
    const completed=!final.rowCount;
    await client.query(
      "UPDATE expedition_participants SET current_stage=$1,status=$2 WHERE expedition_id=$3 AND guild_id=$4 AND user_id=$5",
      [completed?next-1:next,completed?"completed":"active",input.expeditionId,input.guildId,input.userId],
    );
    if(completed){
      const active=await client.query(
        "SELECT COUNT(*)::INT AS count FROM expedition_participants WHERE expedition_id=$1 AND guild_id=$2 AND status='active'",
        [input.expeditionId,input.guildId],
      );
      const activeCount=Number((active.rows[0] as {count:number}|undefined)?.count??0);
      if(activeCount===0){
        await client.query("UPDATE expeditions SET status='completed',updated_at=CURRENT_TIMESTAMP WHERE id=$1 AND guild_id=$2 AND status='open'",[input.expeditionId,input.guildId]);
      }
    }
    return {correct:true,completed,nextStage:completed?next-1:next};
  });
}
export async function setExpeditionStatus(input:{
  guildId:string;expeditionId:string;ownerId:string;status:"paused"|"open"|"cancelled";
}):Promise<void>{
  const row=await queryOne<{owner_id:string;status:string}>(
    "SELECT owner_id::text,status FROM expeditions WHERE id=$1 AND guild_id=$2",
    [input.expeditionId,input.guildId],
  );
  if(!row||row.owner_id!==input.ownerId)throw new Error("Only the expedition owner can change its status.");
  if(input.status==="open"&&!["paused","open"].includes(row.status))throw new Error("This expedition cannot be reopened.");
  if(input.status==="paused"&&row.status!=="open")throw new Error("Only an open expedition can be paused.");
  if(input.status==="cancelled"&&!["draft","open","paused"].includes(row.status))throw new Error("This expedition cannot be cancelled.");
  await query("UPDATE expeditions SET status=$1,updated_at=CURRENT_TIMESTAMP WHERE id=$2 AND guild_id=$3",[input.status,input.expeditionId,input.guildId]);
}
