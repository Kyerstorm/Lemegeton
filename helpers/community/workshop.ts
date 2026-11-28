import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { cleanText, isDiscordSnowflake } from "../security/security.js";

export interface WorkshopProject {
  id:string;guild_id:string;owner_id:string;title:string;description:string;
  status:"draft"|"open"|"paused"|"completed"|"archived"|"cancelled";created_at:string;
}
export interface WorkshopSection {
  id:string;project_id:string;guild_id:string;title:string;description:string;
  assigned_to:string|null;status:"open"|"in_review"|"approved"|"changes_requested"|"rejected";position:number;
}
export interface WorkshopRevision {
  id:string;section_id:string;project_id:string;author_id:string;content:string;
  status:"pending"|"approved"|"changes_requested"|"rejected";reviewer_id:string|null;review_note:string|null;created_at:string;
}
export interface WorkshopDetails {
  project:WorkshopProject;sections:WorkshopSection[];revisions:WorkshopRevision[];
}

export async function createWorkshopProject(input:{guildId:string;ownerId:string;title:string;description:string}):Promise<string>{
  const title=cleanText(input.title,180),description=cleanText(input.description,1_000);
  if(!title||!description)throw new Error("Provide a project title and description.");
  const row=await queryOne<{id:string}>(
    "INSERT INTO workshop_projects (guild_id,owner_id,title,description,status) VALUES ($1,$2,$3,$4,'open') RETURNING id::text AS id",
    [input.guildId,input.ownerId,title,description],
  );
  if(!row)throw new Error("The project could not be created.");
  return row.id;
}

export async function listWorkshopProjects(guildId:string,limit=15):Promise<Array<{id:string;title:string;status:string;section_count:number}>>{
  return query(
    `SELECT p.id::text AS id,p.title,p.status,
      (SELECT COUNT(*) FROM workshop_sections s WHERE s.project_id=p.id)::INT AS section_count
     FROM workshop_projects p WHERE p.guild_id=$1 AND p.status IN ('open','paused','draft')
     ORDER BY p.created_at DESC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}

export async function getWorkshopProject(guildId:string,projectId:string):Promise<WorkshopDetails|null>{
  const project=await queryOne<WorkshopProject>(
    "SELECT id::text,guild_id::text,owner_id::text,title,description,status,created_at FROM workshop_projects WHERE id=$1 AND guild_id=$2",
    [projectId,guildId],
  );
  if(!project)return null;
  const [sections,revisions]=await Promise.all([
    query<WorkshopSection>(
      "SELECT id::text,project_id::text,guild_id::text,title,description,assigned_to::text,status,position FROM workshop_sections WHERE project_id=$1 AND guild_id=$2 ORDER BY position,id LIMIT 25",
      [projectId,guildId],
    ),
    query<WorkshopRevision>(
      "SELECT id::text,section_id::text,project_id::text,author_id::text,content,status,reviewer_id::text,review_note,created_at FROM workshop_revisions WHERE project_id=$1 AND guild_id=$2 ORDER BY created_at DESC LIMIT 50",
      [projectId,guildId],
    ),
  ]);
  return {project,sections,revisions};
}

export async function createWorkshopSection(input:{
  guildId:string;projectId:string;ownerId:string;title:string;description?:string;assignedTo?:string;
}):Promise<string>{
  const title=cleanText(input.title,180);
  if(!title)throw new Error("A section needs a title.");
  const assignedTo=input.assignedTo?.trim()||null;
  if(assignedTo&&!isDiscordSnowflake(assignedTo))throw new Error("Enter a valid Discord user ID for the assignment.");
  const project=await queryOne<{owner_id:string}>(
    "SELECT owner_id::text FROM workshop_projects WHERE id=$1 AND guild_id=$2 AND status='open'",
    [input.projectId,input.guildId],
  );
  if(!project||project.owner_id!==input.ownerId)throw new Error("Only the owner of an open project can add sections.");
  const position=await queryOne<{next_position:number}>(
    "SELECT COALESCE(MAX(position),-1)+1 AS next_position FROM workshop_sections WHERE project_id=$1 AND guild_id=$2",
    [input.projectId,input.guildId],
  );
  const row=await queryOne<{id:string}>(
    "INSERT INTO workshop_sections (project_id,guild_id,title,description,assigned_to,position) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id::text AS id",
    [input.projectId,input.guildId,title,cleanText(input.description,500),assignedTo,position?.next_position??0],
  );
  if(!row)throw new Error("The section could not be created.");
  return row.id;
}

export async function submitWorkshopRevision(input:{
  guildId:string;projectId:string;sectionId:string;authorId:string;content:string;
}):Promise<string>{
  const content=cleanText(input.content,4_000);
  if(!content)throw new Error("A revision cannot be empty.");
  return transaction(async client=>{
    const result=await client.query(
      `SELECT s.assigned_to::text,s.status,p.status AS project_status
       FROM workshop_sections s JOIN workshop_projects p ON p.id=s.project_id
       WHERE s.id=$1 AND s.project_id=$2 AND s.guild_id=$3 FOR UPDATE`,
      [input.sectionId,input.projectId,input.guildId],
    );
    const section=result.rows[0] as {assigned_to:string|null;status:string;project_status:string}|undefined;
    if(!section||section.project_status!=="open")throw new Error("That section is not in an open project.");
    if(section.assigned_to&&section.assigned_to!==input.authorId)throw new Error("This section is assigned to another contributor.");
    if(section.status==="approved")throw new Error("This section is already approved.");
    if(section.status==="in_review")throw new Error("A revision for this section is already awaiting review.");
    const inserted=await client.query<{id:string}>(
      "INSERT INTO workshop_revisions (section_id,project_id,guild_id,author_id,content,status) VALUES ($1,$2,$3,$4,$5,'pending') RETURNING id::text AS id",
      [input.sectionId,input.projectId,input.guildId,input.authorId,content],
    );
    const id=inserted.rows[0]?.id;
    if(!id)throw new Error("The revision could not be saved.");
    await client.query("UPDATE workshop_sections SET status='in_review' WHERE id=$1 AND project_id=$2 AND guild_id=$3",[input.sectionId,input.projectId,input.guildId]);
    return id;
  });
}

export async function reviewWorkshopRevision(input:{
  guildId:string;projectId:string;sectionId:string;revisionId:string;reviewerId:string;approve:boolean;note?:string;
}):Promise<void>{
  await transaction(async client=>{
    const result=await client.query(
      `SELECT p.owner_id::text,p.status AS project_status,s.id::text,r.id::text,r.status,r.author_id::text
       FROM workshop_projects p JOIN workshop_sections s ON s.project_id=p.id
       JOIN workshop_revisions r ON r.section_id=s.id AND r.project_id=p.id
       WHERE p.id=$1 AND p.guild_id=$2 AND s.id=$3 AND r.id=$4 FOR UPDATE`,
      [input.projectId,input.guildId,input.sectionId,input.revisionId],
    );
    const row=result.rows[0] as {owner_id:string;project_status:string;status:string;author_id:string}|undefined;
    if(!row||row.status!=="pending")throw new Error("That pending revision was not found.");
    if(row.owner_id!==input.reviewerId)throw new Error("Only the project owner can review revisions.");
    if(row.project_status!=="open")throw new Error("Revisions can only be reviewed while the project is open.");
    if(row.author_id===input.reviewerId)throw new Error("A contributor cannot review their own revision.");
    const status=input.approve?"approved":"changes_requested";
    await client.query(
      "UPDATE workshop_revisions SET status=$1,reviewer_id=$2,review_note=$3 WHERE id=$4 AND guild_id=$5",
      [status,input.reviewerId,cleanText(input.note,500)||null,input.revisionId,input.guildId],
    );
    await client.query(
      "UPDATE workshop_sections SET status=$1 WHERE id=$2 AND project_id=$3 AND guild_id=$4",
      [status,input.sectionId,input.projectId,input.guildId],
    );
  });
}

export async function setWorkshopProjectStatus(input:{
  guildId:string;projectId:string;actorId:string;status:"paused"|"open"|"completed"|"archived"|"cancelled";
}):Promise<void>{
  const row=await queryOne<{owner_id:string;status:string}>(
    "SELECT owner_id::text,status FROM workshop_projects WHERE id=$1 AND guild_id=$2",
    [input.projectId,input.guildId],
  );
  if(!row||row.owner_id!==input.actorId)throw new Error("Only the project owner can change project status.");
  if(input.status==="open"&&!["paused","draft","open"].includes(row.status))throw new Error("This project cannot be reopened.");
  if(input.status==="paused"&&row.status!=="open")throw new Error("Only an open project can be paused.");
  if(["completed","archived","cancelled"].includes(input.status)&&!["open","paused","draft"].includes(row.status))throw new Error("This project is already closed.");
  await query("UPDATE workshop_projects SET status=$1,updated_at=CURRENT_TIMESTAMP WHERE id=$2 AND guild_id=$3",[input.status,input.projectId,input.guildId]);
}
