import { randomInt } from "node:crypto";
export interface IgdbGame{id:number;title:string;summary:string|null;sourceUrl:string;image:string|null;releaseDate:string|null;genres:string[];platforms:string[];developers:string[];publishers:string[]}
const obj=(v:unknown):Record<string,unknown>|null=>typeof v==="object"&&v!==null&&!Array.isArray(v)?v as Record<string,unknown>:null;
export class IgdbClient{private token:string|null=null;private expires=0;constructor(private readonly clientId?:string,private readonly secret?:string){}async search(query:string,offset=0):Promise<IgdbGame[]>{
 if(!this.clientId||!this.secret)throw new Error("IGDB is not configured. Set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET to enable game discovery.");
 const token=await this.getToken();
 const clean=query.replace(/[";\\]/g," ").replace(/\s+/g," ").trim().slice(0,100);
 const searchClause=clean?`search "${clean}"; `:"";
 const safeOffset=Math.max(0,Math.min(500,Math.trunc(offset)));
 const res=await fetch("https://api.igdb.com/v4/games",{method:"POST",headers:{"Client-ID":this.clientId,Authorization:`Bearer ${token}`,"Content-Type":"text/plain"},body:`${searchClause}fields id,name,slug,summary,first_release_date,cover.url,genres.name,platforms.name,involved_companies.developer,involved_companies.publisher,involved_companies.company.name; sort rating desc; limit 10; offset ${safeOffset};`,signal:AbortSignal.timeout(12000)});
 if(!res.ok)throw new Error(`IGDB returned HTTP ${res.status}.`);
 const rows:unknown=await res.json();
 return(Array.isArray(rows)?rows:[]).flatMap(raw=>{
  const x=obj(raw);if(!x||typeof x.id!=="number"||typeof x.name!=="string")return[];
  const cover=obj(x.cover);
  const companies=(Array.isArray(x.involved_companies)?x.involved_companies:[]).flatMap(rawCompany=>{const c=obj(rawCompany),co=obj(c?.company);return co&&typeof co.name==="string"?[{name:co.name,developer:c?.developer===true,publisher:c?.publisher===true}]:[];});
  const list=(v:unknown)=>Array.isArray(v)?v.flatMap(i=>obj(i)&&typeof obj(i)!.name==="string"?[String(obj(i)!.name)]:[]):[];
  return[{id:x.id,title:x.name,summary:typeof x.summary==="string"?x.summary:null,sourceUrl:typeof x.slug==="string"?`https://www.igdb.com/games/${x.slug}`:`https://www.igdb.com/search?type=1&q=${encodeURIComponent(x.name)}`,image:typeof cover?.url==="string"?`https:${cover.url.replace(/^https?:/,"")}`:null,releaseDate:typeof x.first_release_date==="number"?new Date(x.first_release_date*1000).toISOString().slice(0,10):null,genres:list(x.genres),platforms:list(x.platforms),developers:companies.filter(c=>c.developer).map(c=>c.name),publishers:companies.filter(c=>c.publisher).map(c=>c.name)}];
 });
}
async random():Promise<IgdbGame[]>{return this.search("",randomInt(0,501));}private async getToken():Promise<string>{if(this.token&&Date.now()<this.expires)return this.token;const url=new URL("https://id.twitch.tv/oauth2/token");url.searchParams.set("client_id",this.clientId!);url.searchParams.set("client_secret",this.secret!);url.searchParams.set("grant_type","client_credentials");const res=await fetch(url,{method:"POST",signal:AbortSignal.timeout(10000)});if(!res.ok)throw new Error(`IGDB authentication returned HTTP ${res.status}.`);const p=obj(await res.json());if(typeof p?.access_token!=="string"||typeof p.expires_in!=="number")throw new Error("IGDB authentication response was invalid.");this.token=p.access_token;this.expires=Date.now()+Math.max(60,p.expires_in-120)*1000;return this.token;}}
