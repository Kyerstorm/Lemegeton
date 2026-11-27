import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { cleanText } from "../security/security.js";

export interface CasebookCase {
  id:string;guild_id:string;author_id:string;title:string;premise:string;
  status:"draft"|"published"|"paused"|"closed";created_at:string;
}
export interface CasebookEvidence {
  id:string;title:string;description:string;unlock_order:number;is_red_herring:boolean|null;
}
export interface CasebookTheory {
  id:string;team_key:string;author_id:string;theory:string;cited_evidence_ids:string;status:"open"|"submitted"|"correct"|"incorrect";created_at:string;
}
export interface CasebookDetails {
  case:CasebookCase;evidence:CasebookEvidence[];theories:CasebookTheory[];
}
function required(value:string,maximum:number,label:string):string{
  const result=cleanText(value,maximum);if(!result)throw new Error(label+" is required.");return result;
}
function solutionKey(secret:string):Buffer{
  if(secret.length<32)throw new Error("The Casebook solution secret must be at least 32 characters.");
  return createHash("sha256").update(secret+"::Lemegeton::Casebook::v1").digest();
}
function encryptSolution(secret:string,solution:string):string{
  const iv=randomBytes(12);
  const cipher=createCipheriv("aes-256-gcm",solutionKey(secret),iv);
  const ciphertext=Buffer.concat([cipher.update(solution,"utf8"),cipher.final()]);
  return ["v1",iv.toString("base64"),cipher.getAuthTag().toString("base64"),ciphertext.toString("base64")].join(":");
}
function decryptSolution(secret:string,value:string):string{
  const [version,ivText,tagText,cipherText]=value.split(":");
  if(version!=="v1"||!ivText||!tagText||!cipherText)throw new Error("The stored solution format is not supported.");
  const decipher=createDecipheriv("aes-256-gcm",solutionKey(secret),Buffer.from(ivText,"base64"));
  decipher.setAuthTag(Buffer.from(tagText,"base64"));
  return Buffer.concat([decipher.update(Buffer.from(cipherText,"base64")),decipher.final()]).toString("utf8");
}

export async function createCasebookCase(input:{
  guildId:string;authorId:string;title:string;premise:string;solution:string;solutionSecret:string;
}):Promise<string>{
  const title=required(input.title,180,"Case title");
  const premise=required(input.premise,2_000,"Case premise");
  const solution=required(input.solution,2_000,"Case solution");
  const encrypted=encryptSolution(input.solutionSecret,solution);
  const row=await queryOne<{id:string}>(
    "INSERT INTO casebook_cases (guild_id,author_id,title,premise,answer_key,status) VALUES ($1,$2,$3,$4,$5,'draft') RETURNING id::text AS id",
    [input.guildId,input.authorId,title,premise,encrypted],
  );
  if(!row)throw new Error("The casebook entry could not be created.");return row.id;
}
export async function listCasebookCases(guildId:string,limit=15):Promise<Array<{id:string;title:string;status:string;evidence_count:number;theory_count:number}>>{
  return query(
    `SELECT c.id::text,c.title,c.status,
      (SELECT COUNT(*) FROM casebook_evidence e WHERE e.case_id=c.id AND e.is_unlocked=1)::INT AS evidence_count,
      (SELECT COUNT(*) FROM casebook_theories t WHERE t.case_id=c.id)::INT AS theory_count
     FROM casebook_cases c WHERE c.guild_id=$1 AND c.status IN ('published','paused','closed')
     ORDER BY c.created_at DESC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}
export async function getCasebookCase(guildId:string,caseId:string,viewerId:string):Promise<CasebookDetails|null>{
  const caseItem=await queryOne<CasebookCase>(
    "SELECT id::text,guild_id::text,author_id::text,title,premise,status,created_at FROM casebook_cases WHERE id=$1 AND guild_id=$2",
    [caseId,guildId],
  );
  if(!caseItem||(caseItem.status==="draft"&&caseItem.author_id!==viewerId))return null;
  const [evidence,theories]=await Promise.all([
    query<CasebookEvidence>(
      `SELECT e.id::text,e.title,e.description,e.unlock_order,
        CASE WHEN c.status='closed' THEN e.is_red_herring ELSE NULL END AS is_red_herring
       FROM casebook_evidence e JOIN casebook_cases c ON c.id=e.case_id
       WHERE e.case_id=$1 AND e.guild_id=$2 AND (e.is_unlocked=1 OR c.status='closed')
       ORDER BY e.unlock_order ASC LIMIT 25`,
      [caseId,guildId],
    ),
    query<CasebookTheory>(
      `SELECT t.id::text,t.team_key,t.author_id::text,t.theory,t.cited_evidence_ids,t.status,t.created_at
       FROM casebook_theories t JOIN casebook_cases c ON c.id=t.case_id
       WHERE t.case_id=$1 AND t.guild_id=$2
         AND (c.author_id=$3 OR t.author_id=$3 OR c.status='closed')
       ORDER BY t.created_at DESC LIMIT 25`,
      [caseId,guildId,viewerId??null],
    ),
  ]);
  return {case:caseItem,evidence,theories};
}
export async function addCasebookEvidence(input:{
  guildId:string;caseId:string;authorId:string;title:string;description:string;redHerring?:boolean;
}):Promise<string>{
  const title=required(input.title,180,"Evidence title");
  const description=required(input.description,1_000,"Evidence description");
  return transaction(async client=>{
    const found=await client.query(
      "SELECT author_id::text,status FROM casebook_cases WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [input.caseId,input.guildId],
    );
    const row=found.rows[0] as {author_id:string;status:string}|undefined;
    if(!row||row.author_id!==input.authorId)throw new Error("Only the case author can add evidence.");
    if(row.status!=="draft")throw new Error("Evidence can only be added before the case is published.");
    const position=await client.query(
      "SELECT COALESCE(MAX(unlock_order),0)+1 AS next_position FROM casebook_evidence WHERE case_id=$1 AND guild_id=$2",
      [input.caseId,input.guildId],
    );
    const next=Number((position.rows[0] as {next_position:number}|undefined)?.next_position??1);
    const inserted=await client.query<{id:string}>(
      "INSERT INTO casebook_evidence (case_id,guild_id,title,description,unlock_order,is_red_herring) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id::text AS id",
      [input.caseId,input.guildId,title,description,next,input.redHerring?1:0],
    );
    const id=inserted.rows[0]?.id;if(!id)throw new Error("Evidence could not be saved.");return id;
  });
}
export async function publishCasebookCase(input:{guildId:string;caseId:string;authorId:string}):Promise<void>{
  await transaction(async client=>{
    const found=await client.query(
      "SELECT author_id::text,status FROM casebook_cases WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [input.caseId,input.guildId],
    );
    const row=found.rows[0] as {author_id:string;status:string}|undefined;
    if(!row||row.author_id!==input.authorId)throw new Error("Only the case author can publish it.");
    if(row.status!=="draft")throw new Error("This case is no longer a draft.");
    const count=await client.query("SELECT id FROM casebook_evidence WHERE case_id=$1 AND guild_id=$2 ORDER BY unlock_order LIMIT 1",[input.caseId,input.guildId]);
    const first=count.rows[0] as {id:string}|undefined;
    if(!first)throw new Error("Add at least one piece of evidence before publishing.");
    await client.query("UPDATE casebook_evidence SET is_unlocked=1 WHERE id=$1 AND case_id=$2 AND guild_id=$3",[first.id,input.caseId,input.guildId]);
    await client.query("UPDATE casebook_cases SET status='published',published_at=CURRENT_TIMESTAMP WHERE id=$1 AND guild_id=$2",[input.caseId,input.guildId]);
  });
}
export async function unlockNextCasebookEvidence(input:{guildId:string;caseId:string;authorId:string}):Promise<CasebookEvidence|null>{
  return transaction(async client=>{
    const found=await client.query(
      "SELECT author_id::text,status FROM casebook_cases WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [input.caseId,input.guildId],
    );
    const row=found.rows[0] as {author_id:string;status:string}|undefined;
    if(!row||row.author_id!==input.authorId)throw new Error("Only the case author can unlock evidence.");
    if(row.status!=="published")throw new Error("Evidence can only be unlocked while the case is published.");
    const result=await client.query(
      "SELECT id::text,title,description,unlock_order,is_red_herring FROM casebook_evidence WHERE case_id=$1 AND guild_id=$2 AND is_unlocked=0 ORDER BY unlock_order ASC LIMIT 1",
      [input.caseId,input.guildId],
    );
    const next=result.rows[0] as CasebookEvidence|undefined;
    if(!next)return null;
    await client.query("UPDATE casebook_evidence SET is_unlocked=1 WHERE id=$1 AND case_id=$2 AND guild_id=$3",[next.id,input.caseId,input.guildId]);
    return {...next,is_red_herring:null};
  });
}
export async function submitCasebookTheory(input:{
  guildId:string;caseId:string;authorId:string;theory:string;citedEvidenceIds?:readonly string[];
}):Promise<string>{
  const theory=required(input.theory,1_500,"Theory");
  const cited=[...new Set(input.citedEvidenceIds??[])].slice(0,10);
  const item=await queryOne<{status:string}>(
    "SELECT status FROM casebook_cases WHERE id=$1 AND guild_id=$2",
    [input.caseId,input.guildId],
  );
  if(!item||item.status!=="published")throw new Error("Theories can only be submitted to a published case.");
  if(cited.length){
    const evidence=await query<{id:string}>(
      "SELECT id::text FROM casebook_evidence WHERE case_id=$1 AND guild_id=$2 AND is_unlocked=1",
      [input.caseId,input.guildId],
    );
    const available=new Set(evidence.map(row=>row.id));
    if(cited.some(id=>!available.has(id)))throw new Error("Only evidence unlocked in this case can be cited.");
  }
  const row=await queryOne<{id:string}>(
    "INSERT INTO casebook_theories (case_id,guild_id,team_key,author_id,theory,cited_evidence_ids,status) VALUES ($1,$2,$3,$3,$4,$5,'submitted') RETURNING id::text AS id",
    [input.caseId,input.guildId,input.authorId,theory,JSON.stringify(cited)],
  );
  if(!row)throw new Error("The theory could not be saved.");return row.id;
}
export async function closeCasebookCase(input:{
  guildId:string;caseId:string;actorId:string;canModerate?:boolean;
}):Promise<void>{
  const row=await queryOne<{author_id:string;status:string}>(
    "SELECT author_id::text,status FROM casebook_cases WHERE id=$1 AND guild_id=$2",
    [input.caseId,input.guildId],
  );
  if(!row||row.status!=="published")throw new Error("Only a published case can be closed.");
  if(row.author_id!==input.actorId&&!input.canModerate)throw new Error("Only the case author or a moderator can close it.");
  await query("UPDATE casebook_cases SET status='closed' WHERE id=$1 AND guild_id=$2 AND status='published'",[input.caseId,input.guildId]);
}
export async function setCasebookStatus(input:{
  guildId:string;caseId:string;authorId:string;status:"paused"|"published"|"cancelled";
}):Promise<void>{
  const row=await queryOne<{author_id:string;status:string}>(
    "SELECT author_id::text,status FROM casebook_cases WHERE id=$1 AND guild_id=$2",
    [input.caseId,input.guildId],
  );
  if(!row||row.author_id!==input.authorId)throw new Error("Only the case author can change the case status.");
  if(input.status==="paused"&&row.status!=="published")throw new Error("Only a published case can be paused.");
  if(input.status==="published"&&row.status!=="paused")throw new Error("Only a paused case can be resumed.");
  if(input.status==="cancelled"&&!["draft","published","paused"].includes(row.status))throw new Error("This case cannot be cancelled.");
  await query("UPDATE casebook_cases SET status=$1 WHERE id=$2 AND guild_id=$3",[input.status,input.caseId,input.guildId]);
}
export async function revealCasebookSolution(input:{
  guildId:string;caseId:string;actorId:string;canModerate?:boolean;solutionSecret:string;
}):Promise<string>{
  const row=await queryOne<{author_id:string;status:string;answer_key:string}>(
    "SELECT author_id::text,status,answer_key FROM casebook_cases WHERE id=$1 AND guild_id=$2",
    [input.caseId,input.guildId],
  );
  if(!row||row.status!=="closed")throw new Error("The case must be closed before its solution is revealed.");
  if(row.author_id!==input.actorId&&!input.canModerate)throw new Error("Only the case author or a moderator can reveal the solution.");
  return decryptSolution(input.solutionSecret,row.answer_key);
}
