import sharp from "sharp";

export interface MediaGridItem {
  title:string;
  image:string|null;
}
export type MediaGridSource =
  | { kind: "anime"; id: number }
  | { kind: "manga"; id: number }
  | { kind: "character"; id: number }
  | { kind: "game"; slug: string };


const TILE_WIDTH=220;
const TILE_HEIGHT=330;
const GAP=8;
const GRID_SIZE=3;
const MAX_IMAGE_BYTES=5*1024*1024;
const ALLOWED_IMAGE_HOSTS=new Set(["s4.anilist.co","images.igdb.com"]);

export function parseGridSourceUrls(titles:readonly string[]):MediaGridSource[]|null{
 const hasUrl=titles.some(title=>/^[a-z][a-z0-9+.-]*:\/\//i.test(title));
 if(!hasUrl)return null;
 if(titles.length!==9)throw new Error("Enter exactly nine provider URLs, one per line.");
 if(titles.some(title=>!/^https:\/\//i.test(title)))throw new Error("Use HTTPS AniList or IGDB URLs for every grid entry.");
 const sources=titles.map((raw,index):MediaGridSource=>{
  let url:URL;
  try{url=new URL(raw);}catch{throw new Error("Grid entry "+(index+1)+" is not a valid provider URL.");}
  if(url.username||url.password||url.port||url.search||url.hash)throw new Error("Grid entry "+(index+1)+" contains unsupported URL details.");
  if(url.hostname==="anilist.co"){
   const match=/^\/(anime|manga|character)\/(\d+)(?:\/[^/]*)?\/?$/.exec(url.pathname);
   const id=match?Number(match[2]):Number.NaN;
   if(!match||!Number.isSafeInteger(id)||id<1)throw new Error("Grid entry "+(index+1)+" must be a valid AniList anime, manga or character URL.");
   return{kind:match[1] as "anime"|"manga"|"character",id};
  }
  if(url.hostname==="www.igdb.com"||url.hostname==="igdb.com"){
   const match=/^\/games\/([a-z0-9]+(?:-[a-z0-9]+)*)\/?$/i.exec(url.pathname);
   if(!match)throw new Error("Grid entry "+(index+1)+" must be a valid IGDB game URL.");
   return{kind:"game",slug:match[1]!.toLowerCase()};
  }
  throw new Error("Grid entry "+(index+1)+" must use an AniList or IGDB provider URL.");
 });
 const kinds=new Set(sources.map(source=>source.kind));
 if(kinds.size!==1)throw new Error("All nine grid URLs must use the same media type.");
 return sources;
}

export function parseGridTitles(value:string):string[]{
 const titles=value.split(/\r?\n/).map(item=>item.trim()).filter(Boolean);
 if(titles.length!==9)throw new Error("Enter exactly nine titles, one per line.");
 if(titles.some(title=>title.length<2||title.length>200))throw new Error("Each title must contain between 2 and 200 characters.");
 return titles;
}

function safeImageUrl(value:string|null):string|null{
 if(!value)return null;
 try{
  const url=new URL(value);
  return url.protocol==="https:"&&!url.username&&!url.password&&ALLOWED_IMAGE_HOSTS.has(url.hostname.toLowerCase())?url.toString():null;
 }catch{return null;}
}

function escapeXml(value:string):string{
 return value.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&apos;");
}

function placeholder(title:string):Buffer{
 const safe=escapeXml(title.slice(0,60));
 const svg=`<svg width="${TILE_WIDTH}" height="${TILE_HEIGHT}" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#292d36"/><stop offset="1" stop-color="#111319"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><circle cx="110" cy="108" r="32" fill="#424957"/><path d="M94 110h32M110 94v32" stroke="#c5ccd7" stroke-width="3" stroke-linecap="round"/><text x="110" y="190" fill="#e7eaf0" font-family="Arial,sans-serif" font-size="15" text-anchor="middle">${safe}</text><text x="110" y="216" fill="#858d9b" font-family="Arial,sans-serif" font-size="11" text-anchor="middle">Cover unavailable</text></svg>`;
 return Buffer.from(svg);
}

async function downloadCover(value:string|null):Promise<Buffer|null>{
 const url=value?safeImageUrl(value):null;
 if(!url)return null;
 try{
  const response=await fetch(url,{signal:AbortSignal.timeout(8000),headers:{Accept:"image/avif,image/webp,image/png,image/jpeg"}});
  if(!response.ok)return null;
  const contentType=response.headers.get("content-type")?.split(";",1)[0]?.trim().toLowerCase()??"";
  if(!contentType.startsWith("image/"))return null;
  const length=Number(response.headers.get("content-length")??0);
  if(length>MAX_IMAGE_BYTES)return null;
  const bytes=Buffer.from(await response.arrayBuffer());
  if(bytes.length<1||bytes.length>MAX_IMAGE_BYTES)return null;
  return await sharp(bytes,{limitInputPixels:20_000_000}).rotate().resize(TILE_WIDTH,TILE_HEIGHT,{fit:"cover",position:"attention"}).jpeg({quality:86}).toBuffer();
 }catch{return null;}
}

export async function renderMediaGrid(items:readonly MediaGridItem[]):Promise<Buffer>{
 if(items.length!==9)throw new RangeError("A media grid needs exactly nine items.");
 const tiles=await Promise.all(items.map(async item=>await downloadCover(item.image)??placeholder(item.title)));
 const width=TILE_WIDTH*GRID_SIZE+GAP*(GRID_SIZE+1);
 const height=TILE_HEIGHT*GRID_SIZE+GAP*(GRID_SIZE+1);
 const composites=tiles.map((input,index)=>({
  input,left:GAP+(index%GRID_SIZE)*(TILE_WIDTH+GAP),top:GAP+Math.floor(index/GRID_SIZE)*(TILE_HEIGHT+GAP),
 }));
 return sharp({create:{width,height,channels:3,background:"#111319"}}).composite(composites).png({compressionLevel:9}).toBuffer();
}
