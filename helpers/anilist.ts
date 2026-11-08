import { randomInt } from "node:crypto";
export type AniListMediaType = "ANIME" | "MANGA";
export interface AniListSearchFilters {genre?:string;yearFrom?:number;yearTo?:number;status?:string;format?:string;season?:string;seasonYear?:number;}
function filterVariables(filters:AniListSearchFilters):Record<string,unknown>{return{...(filters.genre?{genreIn:[filters.genre]}:{}),...(filters.yearFrom?{startDateGreater:filters.yearFrom*10000+101}:{}),...(filters.yearTo?{startDateLesser:filters.yearTo*10000+1231}:{}),...(filters.status?{status:filters.status}:{}),...(filters.format?{format:filters.format}:{}),...(filters.season?{season:filters.season}:{}),...(filters.seasonYear?{seasonYear:filters.seasonYear}:{})};}
export interface AniListMedia {
  id:number; type:AniListMediaType;
  title:{romaji:string|null;english:string|null;native:string|null};
  description:string|null; siteUrl:string; coverImage:string|null; bannerImage:string|null;
  averageScore:number|null; status:string|null; format:string|null;
  startDate:{year:number|null;month:number|null;day:number|null}|null;
  episodes:number|null; chapters:number|null; volumes:number|null;
  genres:string[]; studios:string[]; staff:string[];
  relations:Array<{id:number;title:string;relation:string;url:string;category:"anime"|"manga"}>;
}
export interface AniListCreator {
 id:number;name:string;url:string;image:string|null;description:string|null;
 occupations:string[];yearsActive:number[];media:Array<{title:string;url:string;role:string;type:AniListMediaType}>;
}
export interface AniListFavoriteMedia {id:number;title:string;url:string;image:string|null}
export interface AniListFavoriteCharacter {id:number;name:string;url:string;image:string|null}
export interface AniListUserInterests {
  anime:{genres:string[];tags:string[]};
  manga:{genres:string[];tags:string[]};
}
export interface AniListUserStatistics {
  count:number;
  meanScore:number;
  episodesWatched:number|null;
  minutesWatched:number|null;
  chaptersRead:number|null;
  volumesRead:number|null;
  genres:Array<{genre:string;count:number}>;
  statuses:Array<{status:string;count:number}>;
  formats:Array<{format:string;count:number}>;
}
export interface AniListUserProfile {
  id:number; name:string; url:string; avatar:string|null; banner:string|null; about:string|null;
  anime:AniListUserStatistics;
  manga:AniListUserStatistics;
  favorites:{anime:AniListFavoriteMedia[];manga:AniListFavoriteMedia[];characters:AniListFavoriteCharacter[]};
}
export interface AniListRecentlyFinishedMedia {
  id: number;
  type: AniListMediaType;
  title: string;
  description: string | null;
  url: string;
  cover: string | null;
  status: "FINISHED" | "CANCELLED";
  format: string | null;
  episodes: number | null;
  chapters: number | null;
  averageScore: number | null;
  genres: string[];
  endDate: { year: number; month: number; day: number } | null;
}

export interface AniListAiring {mediaId:number;title:string;episode:number;airingAt:number;url:string;image:string|null}
type Obj=Record<string,unknown>;
const isObj=(v:unknown):v is Obj=>typeof v==="object"&&v!==null&&!Array.isArray(v);
const str=(v:unknown)=>typeof v==="string"&&v.trim()?v:null;
const num=(v:unknown)=>typeof v==="number"&&Number.isFinite(v)?v:null;
function titleOf(v:unknown):string {const t=isObj(v)?v:{};return str(t.english)??str(t.romaji)??str(t.native)??"Untitled";}
function imageOf(v:unknown):string|null {const o=isObj(v)?v:{};const value=str(o.large);if(!value)return null;try{const u=new URL(value);return u.protocol==="https:"&&u.hostname==="anilist.co"?value:null;}catch{return null;}}
function parseMedia(v:unknown):AniListMedia|null {
 if(!isObj(v)||typeof v.id!=="number"||(v.type!=="ANIME"&&v.type!=="MANGA"))return null;
 const t=isObj(v.title)?v.title:{};const d=isObj(v.startDate)?v.startDate:null;const url=str(v.siteUrl);
 if(!url)return null;try{const u=new URL(url);if(u.protocol!=="https:"||u.hostname!=="anilist.co")return null;}catch{return null;}
 const studios=isObj(v.studios)&&Array.isArray(v.studios.nodes)?v.studios.nodes:[];
 const staff=isObj(v.staff)&&Array.isArray(v.staff.nodes)?v.staff.nodes:[];
 const edges=isObj(v.relations)&&Array.isArray(v.relations.edges)?v.relations.edges:[];
 return {id:v.id,type:v.type,title:{romaji:str(t.romaji),english:str(t.english),native:str(t.native)},
 description:str(v.description),siteUrl:url,coverImage:imageOf(v.coverImage),
 bannerImage:str(v.bannerImage),averageScore:num(v.averageScore),status:str(v.status),format:str(v.format),
 startDate:d?{year:num(d.year),month:num(d.month),day:num(d.day)}:null,
 episodes:num(v.episodes),chapters:num(v.chapters),volumes:num(v.volumes),
 genres:Array.isArray(v.genres)?v.genres.filter((x):x is string=>typeof x==="string").slice(0,20):[],
 studios:studios.flatMap(x=>isObj(x)&&typeof x.name==="string"?[x.name]:[]).slice(0,8),
 staff:staff.flatMap(x=>isObj(x)&&isObj(x.name)&&typeof x.name.full==="string"?[x.name.full]:[]).slice(0,8),
 relations:edges.flatMap(x=>{if(!isObj(x)||!isObj(x.node))return[];const n=x.node;const u=str(n.siteUrl);if(!u||typeof n.id!=="number"||(n.type!=="ANIME"&&n.type!=="MANGA"))return[];return[{id:n.id,title:titleOf(n.title),relation:str(x.relationType)??"RELATED",url:u,category:n.type==="ANIME"?"anime" as const:"manga" as const}];}).slice(0,10)};
}
export function parseCreator(value:unknown):AniListCreator|null {
 if(!isObj(value)||typeof value.id!=="number"||!Number.isSafeInteger(value.id))return null;
 const name=isObj(value.name)?str(value.name.full):null;
 const url=str(value.siteUrl);
 if(!name||!url)return null;
 try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co"||!parsed.pathname.startsWith("/staff/"))return null;}catch{return null;}
 const connection=isObj(value.staffMedia)&&Array.isArray(value.staffMedia.edges)?value.staffMedia.edges:[];
 const media=connection.flatMap(edge=>{
  if(!isObj(edge)||!isObj(edge.node))return[];
  const node=edge.node;const mediaUrl=str(node.siteUrl);
  if(typeof node.id!=="number"||(node.type!=="ANIME"&&node.type!=="MANGA")||!mediaUrl)return[];
  try{const parsed=new URL(mediaUrl);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
  return[{title:titleOf(node.title),url:mediaUrl,role:str(edge.staffRole)??"Staff",type:node.type as AniListMediaType}];
 }).slice(0,8);
 return {
  id:value.id,name,url,image:imageOf(value.image),description:str(value.description),
  occupations:Array.isArray(value.primaryOccupations)?value.primaryOccupations.filter((x):x is string=>typeof x==="string").slice(0,8):[],
  yearsActive:Array.isArray(value.yearsActive)?value.yearsActive.filter((x):x is number=>typeof x==="number"&&Number.isSafeInteger(x)).slice(0,2):[],
  media,
 };
}
function stats(v:unknown):AniListUserStatistics {
 const o=isObj(v)?v:{};
 const genres=Array.isArray(o.genres)?o.genres.flatMap(x=>isObj(x)&&typeof x.genre==="string"&&typeof x.count==="number"?[{genre:x.genre,count:x.count}]:[]):[];
 const statuses=Array.isArray(o.statuses)?o.statuses.flatMap(x=>isObj(x)&&typeof x.status==="string"&&typeof x.count==="number"?[{status:x.status,count:x.count}]:[]):[];
 const formats=Array.isArray(o.formats)?o.formats.flatMap(x=>isObj(x)&&typeof x.format==="string"&&typeof x.count==="number"?[{format:x.format,count:x.count}]:[]):[];
 return{
  count:num(o.count)??0,meanScore:num(o.meanScore)??0,
  episodesWatched:num(o.episodesWatched),minutesWatched:num(o.minutesWatched),
  chaptersRead:num(o.chaptersRead),volumesRead:num(o.volumesRead),
  genres:genres.sort((x,y)=>y.count-x.count).slice(0,20),
  statuses:statuses.sort((x,y)=>y.count-x.count),
  formats:formats.sort((x,y)=>y.count-x.count),
 };
}
function favoriteMedia(v:unknown):AniListFavoriteMedia[] {
 const nodes=isObj(v)&&Array.isArray(v.nodes)?v.nodes:[];
 return nodes.flatMap(item=>{
  if(!isObj(item)||typeof item.id!=="number")return[];
  const url=str(item.siteUrl);if(!url)return[];
  try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
  return[{id:item.id,title:titleOf(item.title),url,image:imageOf(item.coverImage)}];
 }).slice(0,5);
}
function favoriteCharacters(v:unknown):AniListFavoriteCharacter[] {
 const nodes=isObj(v)&&Array.isArray(v.nodes)?v.nodes:[];
 return nodes.flatMap(item=>{
  if(!isObj(item)||typeof item.id!=="number")return[];
  const name=isObj(item.name)?str(item.name.full):null,url=str(item.siteUrl);
  if(!name||!url)return[];
  try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
  return[{id:item.id,name,url,image:imageOf(item.image)}];
 }).slice(0,5);
}
function parseInterestSection(value:unknown):AniListUserInterests["anime"] {
 const lists=isObj(value)&&Array.isArray(value.lists)?value.lists:[];
 const genres=new Set<string>(),tags=new Set<string>();
 for(const list of lists){
  const entries=isObj(list)&&Array.isArray(list.entries)?list.entries:[];
  for(const entry of entries){
   const media=isObj(entry)&&isObj(entry.media)?entry.media:{};
   if(Array.isArray(media.genres))for(const genre of media.genres)if(typeof genre==="string"&&genre.trim())genres.add(genre);
   if(Array.isArray(media.tags))for(const tag of media.tags){
    if(isObj(tag)&&tag.isMediaSpoiler!==true&&typeof tag.name==="string"&&tag.name.trim()
      &&typeof tag.rank==="number"&&tag.rank>=75)tags.add(tag.name);
   }
  }
 }
 return{genres:[...genres],tags:[...tags]};
}
const SEARCH=`query Search($search:String,$type:MediaType!,$format:MediaFormat,$sort:[MediaSort],$page:Int,$perPage:Int,$genreIn:[String],$startDateGreater:FuzzyDateInt,$startDateLesser:FuzzyDateInt,$status:MediaStatus,$season:MediaSeason,$seasonYear:Int){Page(page:$page,perPage:$perPage){media(search:$search,type:$type,format:$format,sort:$sort,genre_in:$genreIn,startDate_greater:$startDateGreater,startDate_lesser:$startDateLesser,status:$status,season:$season,seasonYear:$seasonYear){id type title{romaji english native} description(asHtml:false) siteUrl coverImage{large} bannerImage averageScore status format startDate{year month day} episodes chapters volumes genres studios{nodes{name}} staff(page:1,perPage:8){nodes{name{full}}} relations{edges{relationType node{id type siteUrl title{romaji english}}}}}}}}`;
const STAFF_SEARCH=`query CreatorSearch($search:String,$page:Int,$perPage:Int){Page(page:$page,perPage:$perPage){staff(search:$search,sort:SEARCH_MATCH){id name{full} siteUrl image{large} description(asHtml:false) primaryOccupations yearsActive staffMedia(page:1,perPage:8,sort:POPULARITY_DESC){edges{staffRole node{id type siteUrl title{romaji english native}}}}}}}}`;
const USER=`query User($name:String){User(name:$name){id name siteUrl avatar{large} bannerImage about(asHtml:false) statistics{anime{count meanScore episodesWatched minutesWatched statuses{status count} formats{format count} genres{genre count}} manga{count meanScore chaptersRead volumesRead statuses{status count} formats{format count} genres{genre count}}} favourites{anime(page:1,perPage:5){nodes{id siteUrl title{romaji english native} coverImage{large}}} manga(page:1,perPage:5){nodes{id siteUrl title{romaji english native} coverImage{large}}} characters(page:1,perPage:5){nodes{id siteUrl name{full} image{large}}}}}}`;
const TASTE=`query UserTaste($name:String){anime:MediaListCollection(userName:$name,type:ANIME){lists{entries{media{genres tags{name rank isMediaSpoiler}}}}} manga:MediaListCollection(userName:$name,type:MANGA){lists{entries{media{genres tags{name rank isMediaSpoiler}}}}}}}`;
const AIRING=`query Airing($from:Int,$to:Int){Page(page:1,perPage:50){airingSchedules(airingAt_greater:$from,airingAt_lesser:$to,sort:TIME){airingAt episode media{id title{romaji english} siteUrl coverImage{large} isAdult}}}}`;
export class AniListError extends Error {constructor(message:string,readonly statusCode?:number){super(message);this.name="AniListError";}}
export class AniListClient {
 constructor(private readonly endpoint="https://graphql.anilist.co",private readonly timeoutMs=10000,private readonly fetcher:typeof fetch=globalThis.fetch){}
 async search(query:string,type:AniListMediaType,lightNovelOnly=false,filters:AniListSearchFilters={}):Promise<AniListMedia[]>{return this.searchQuery({search:query.trim(),type,...filterVariables(filters),...(lightNovelOnly?{format:"NOVEL"}:{}),sort:"SEARCH_MATCH"});} async random(type:AniListMediaType,lightNovelOnly=false,filters:AniListSearchFilters={}):Promise<AniListMedia[]>{return this.searchQuery({type,...filterVariables(filters),...(lightNovelOnly?{format:"NOVEL"}:{}),sort:"POPULARITY_DESC",page:randomInt(1,201),perPage:10});}
 async trending(type:AniListMediaType,filters:AniListSearchFilters={}):Promise<AniListMedia[]>{return this.searchQuery({type,...filterVariables(filters),sort:"TRENDING_DESC"});}
 async searchCreators(query:string):Promise<AniListCreator[]>{
  const term=query.trim();if(term.length<2)return[];
  const data=await this.graphql(STAFF_SEARCH,{search:term,page:1,perPage:10});
  const page=isObj(data.Page)?data.Page:{};
  return(Array.isArray(page.staff)?page.staff:[]).flatMap(item=>{const creator=parseCreator(item);return creator?[creator]:[];});
 }
 async recommendations(id:number,type:AniListMediaType):Promise<AniListMedia[]>{
  const data=await this.graphql(`query Recs($id:Int,$type:MediaType!){Media(id:$id,type:$type){recommendations(sort:RATING,perPage:10){nodes{mediaRecommendation{id type title{romaji english native} description(asHtml:false) siteUrl coverImage{large} bannerImage averageScore status format startDate{year month day} episodes chapters volumes genres}}}}}}`,{id,type});
  const m=isObj(data.Media)?data.Media:{};const rec=isObj(m.recommendations)&&Array.isArray(m.recommendations.nodes)?m.recommendations.nodes:[];
  return rec.flatMap(x=>isObj(x)&&parseMedia(x.mediaRecommendation)?[parseMedia(x.mediaRecommendation)!]:[]);
 }
 async recentlyFinished(type:AniListMediaType, after:Date, before:Date):Promise<AniListRecentlyFinishedMedia[]>{
  const dateKey=(value:Date)=>value.getUTCFullYear()*10000+(value.getUTCMonth()+1)*100+value.getUTCDate();
  const query=`query RecentlyFinished($type:MediaType!,$after:Int!,$before:Int!){
   Page(page:1,perPage:25){
    media(type:$type,status_in:[FINISHED,CANCELLED],sort:END_DATE_DESC,endDate_greater:$after,endDate_lesser:$before){
     id type title{romaji english native} description(asHtml:false) siteUrl coverImage{large}
     status format episodes chapters averageScore genres endDate{year month day}
    }
   }
  }`;
  const data=await this.graphql(query,{type,after:dateKey(after),before:dateKey(before)});
  const page=isObj(data.Page)?data.Page:{};
  const rows=Array.isArray(page.media)?page.media:[];
  return rows.flatMap((value)=>{
   if(!isObj(value))return[];
   const id=num(value.id),url=str(value.siteUrl),status=str(value.status),title=titleOf(value.title);
   const date=isObj(value.endDate)?value.endDate:{};
   const year=num(date.year),month=num(date.month),day=num(date.day);
   if(!id||!url?.startsWith("https://anilist.co/")||!title
     ||(status!=="FINISHED"&&status!=="CANCELLED")||year===null||month===null||day===null
     ||month<1||month>12||day<1||day>31)return[];
   const genres=Array.isArray(value.genres)?value.genres.filter((item):item is string=>typeof item==="string").slice(0,12):[];
   return[{
    id,type,title,description:str(value.description),url,cover:imageOf(value.coverImage),
    status,format:str(value.format),episodes:num(value.episodes),chapters:num(value.chapters),
    averageScore:num(value.averageScore),genres,endDate:{year,month,day},
   } satisfies AniListRecentlyFinishedMedia];
  });
 }
 async getUser(username:string):Promise<AniListUserProfile|null>{
  const data=await this.graphql(USER,{name:username.trim()});if(!isObj(data.User))return null;const u=data.User;
  const id=num(u.id),name=str(u.name),url=str(u.siteUrl);if(!id||!name||!url||!url.startsWith("https://anilist.co/"))return null;
  const s=isObj(u.statistics)?u.statistics:{},f=isObj(u.favourites)?u.favourites:{};return{id,name,url,avatar:imageOf(u.avatar),banner:str(u.bannerImage),about:str(u.about),anime:stats(s.anime),manga:stats(s.manga),favorites:{anime:favoriteMedia(f.anime),manga:favoriteMedia(f.manga),characters:favoriteCharacters(f.characters)}};
 }
 async getUserInterests(username:string):Promise<AniListUserInterests|null>{
  const data=await this.graphql(TASTE,{name:username.trim()});
  if(!isObj(data.anime)||!isObj(data.manga))return null;
  return{anime:parseInterestSection(data.anime),manga:parseInterestSection(data.manga)};
 }
 async upcomingAirings(from:Date,to:Date):Promise<AniListAiring[]>{
  const data=await this.graphql(AIRING,{from:Math.floor(from.getTime()/1000),to:Math.floor(to.getTime()/1000)});
  const p=isObj(data.Page)?data.Page:{};const rows=Array.isArray(p.airingSchedules)?p.airingSchedules:[];
  return rows.flatMap(x=>{if(!isObj(x)||!isObj(x.media)||x.media.isAdult===true)return[];const m=x.media;const id=num(m.id),at=num(x.airingAt),ep=num(x.episode),url=str(m.siteUrl);if(!id||!at||ep===null||!url?.startsWith("https://anilist.co/"))return[];return[{mediaId:id,title:titleOf(m.title),episode:ep,airingAt:at,url,image:imageOf(m.coverImage)}];});
 }
 private async searchQuery(vars:Record<string,unknown>):Promise<AniListMedia[]>{const d=await this.graphql(SEARCH,{page:1,perPage:10,...vars});const p=isObj(d.Page)?d.Page:{};return(Array.isArray(p.media)?p.media:[]).flatMap(x=>{const m=parseMedia(x);return m?[m]:[];});}
 private async graphql(query:string,variables:Record<string,unknown>):Promise<Obj>{
  let response:Response;try{response=await this.fetcher(this.endpoint,{method:"POST",headers:{"Content-Type":"application/json",Accept:"application/json"},body:JSON.stringify({query,variables}),signal:AbortSignal.timeout(this.timeoutMs)});}catch(e){throw new AniListError(e instanceof Error&&["TimeoutError","AbortError"].includes(e.name)?"AniList request timed out.":"AniList could not be reached.");}
  if(!response.ok)throw new AniListError(`AniList returned HTTP ${response.status}.`,response.status);const payload:unknown=await response.json();if(!isObj(payload)||Array.isArray(payload.errors)||!isObj(payload.data))throw new AniListError("AniList returned no usable data.");return payload.data;
 }
}
